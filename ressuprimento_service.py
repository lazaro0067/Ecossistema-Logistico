"""Regras de negócio: aderência do ressuprimento (real x sell-in x meta) e projeção do mês."""
import calendar
import datetime as dt

import pandas as pd

from core import tempo
from database.connection import execute
from repositories import ressuprimento_repo


def _dias_mes(mes_ano: str) -> int:
    a, m = (int(x) for x in mes_ano.split("-"))
    return calendar.monthrange(a, m)[1]


def dia_referencia(operacao_id: int, mes_ano: str) -> int:
    """Último dia com lançamento no mês (base da projeção)."""
    d = ressuprimento_repo.diario_df(operacao_id, mes_ano)
    if d.empty:
        return 0
    return dt.date.fromisoformat(d["data"].max()).day


def aderencia_mensal(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    diario = ressuprimento_repo.diario_df(operacao_id, mes_ano)
    metas = ressuprimento_repo.metas_df(operacao_id, mes_ano).rename(columns={"meta_volume_hl": "meta_hl"})
    colunas = ["cesta", "real_hl", "sellin_hl", "meta_hl", "projecao_hl", "aderencia_sellin", "atingimento",
               "atingimento_proj"]
    if diario.empty and metas.empty:
        return pd.DataFrame(columns=colunas)
    agg = (diario.groupby("cesta", as_index=False)
                 .agg(sellin_hl=("volume_sellin_hl", "sum"), real_hl=("volume_real_hl", "sum"))
           if not diario.empty else pd.DataFrame(columns=["cesta", "sellin_hl", "real_hl"]))
    df = agg.merge(metas, on="cesta", how="outer")
    for c in ("sellin_hl", "real_hl", "meta_hl"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    dias, ref = _dias_mes(mes_ano), dia_referencia(operacao_id, mes_ano)
    mes_corrente = mes_ano == tempo.mes_atual()
    fator = (dias / ref) if (mes_corrente and ref) else 1.0
    df["projecao_hl"] = df["real_hl"] * fator
    df["aderencia_sellin"] = (df["real_hl"] / df["sellin_hl"].where(df["sellin_hl"] > 0) * 100).round(1)
    df["atingimento"] = (df["real_hl"] / df["meta_hl"].where(df["meta_hl"] > 0) * 100).round(1)
    df["atingimento_proj"] = (df["projecao_hl"] / df["meta_hl"].where(df["meta_hl"] > 0) * 100).round(1)
    return df[colunas].sort_values("real_hl", ascending=False).reset_index(drop=True)


def evolucao_diaria(operacao_id: int, mes_ano: str, cesta: str) -> pd.DataFrame:
    d = ressuprimento_repo.diario_df(operacao_id, mes_ano)
    d = d[d["cesta"] == cesta].sort_values("data").copy()
    d["real_acum"] = d["volume_real_hl"].cumsum()
    d["sellin_acum"] = d["volume_sellin_hl"].cumsum()
    metas = ressuprimento_repo.metas_df(operacao_id, mes_ano)
    meta = metas.loc[metas["cesta"] == cesta, "meta_volume_hl"]
    meta = float(meta.iloc[0]) if not meta.empty else 0.0
    dias = _dias_mes(mes_ano)
    d["meta_acum"] = d["data"].map(lambda x: meta * dt.date.fromisoformat(x).day / dias)
    return d


def cestas_para_metas(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    """Todas as cestas conhecidas (do mês, de metas e do histórico) com a meta do mês."""
    from database.connection import query_df

    cestas = query_df(
        """SELECT DISTINCT cesta FROM ressuprimento_diario WHERE operacao_id = ?
           UNION SELECT DISTINCT cesta FROM metas_ressuprimento WHERE operacao_id = ?""",
        (operacao_id, operacao_id))
    metas = ressuprimento_repo.metas_df(operacao_id, mes_ano)
    df = cestas.merge(metas, on="cesta", how="left")
    df["meta_volume_hl"] = pd.to_numeric(df["meta_volume_hl"], errors="coerce").fillna(0.0)
    return df.sort_values("cesta").reset_index(drop=True)


def salvar_meta(operacao_id: int, mes_ano: str, cesta: str, meta: float) -> None:
    cesta = (cesta or "").strip()
    if cesta:
        ressuprimento_repo.salvar_meta(operacao_id, mes_ano, cesta, float(meta or 0))


def excluir_meta(operacao_id: int, mes_ano: str, cesta: str) -> None:
    execute("DELETE FROM metas_ressuprimento WHERE operacao_id = ? AND mes_ano = ? AND cesta = ?",
            (operacao_id, mes_ano, cesta))


def copiar_metas(operacao_id: int, de_mes: str, para_mes: str) -> int:
    origem = ressuprimento_repo.metas_df(operacao_id, de_mes)
    for r in origem.itertuples():
        ressuprimento_repo.salvar_meta(operacao_id, para_mes, r.cesta, r.meta_volume_hl)
    return len(origem)


def mes_anterior(mes_ano: str) -> str:
    a, m = (int(x) for x in mes_ano.split("-"))
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


# --- Acompanhamento no formato do sistema original -------------------------
def nome_cesta(cesta: str) -> str:
    from config.settings import CESTAS
    return CESTAS.get(cesta, cesta.split(" - ")[-1].title() if " - " in cesta else cesta)


def acompanhamento(operacao_id: int, ano: int, meses: list[int]) -> pd.DataFrame:
    """META x REAL x TENDÊNCIA por cesta nos meses escolhidos + linha Total (Cerveja + Nab)."""
    from config.settings import CESTAS, CESTAS_TOTAL

    meses = meses or list(range(1, 13))
    partes, metas, dias_total, dias_com_dado = [], [], 0, set()
    for m in meses:
        mes_ano = f"{ano}-{m:02d}"
        d = ressuprimento_repo.diario_df(operacao_id, mes_ano)
        if not d.empty:
            partes.append(d)
            dias_com_dado |= set(d["data"])
        metas.append(ressuprimento_repo.metas_df(operacao_id, mes_ano))
        dias_total += _dias_mes(mes_ano)
    real = (pd.concat(partes).groupby("cesta")["volume_real_hl"].sum() if partes else pd.Series(dtype=float))
    meta = (pd.concat(metas).groupby("cesta")["meta_volume_hl"].sum() if metas else pd.Series(dtype=float))

    cestas = list(CESTAS) + sorted((set(real.index) | set(meta.index)) - set(CESTAS))
    df = pd.DataFrame({"cesta": cestas})
    df["indicador"] = df["cesta"].map(nome_cesta)
    df["meta"] = df["cesta"].map(meta).fillna(0.0)
    df["real"] = df["cesta"].map(real).fillna(0.0)
    df = df[(df["meta"] > 0) | (df["real"] > 0) | df["cesta"].isin(CESTAS)]
    preenchidos = len(dias_com_dado)
    hoje = tempo.hoje()
    # tendência só faz sentido enquanto o período não terminou
    periodo_fechado = all((ano, m) < (hoje.year, hoje.month) for m in meses)
    fator = 1.0 if periodo_fechado or not preenchidos else dias_total / preenchidos
    df["tendencia"] = df["real"] * fator
    df["ating_real"] = (df["real"] / df["meta"].where(df["meta"] > 0) * 100)
    df["ating_tend"] = (df["tendencia"] / df["meta"].where(df["meta"] > 0) * 100)
    df["pendencia"] = df["real"] - df["meta"]

    tot = df[df["cesta"].isin(CESTAS_TOTAL)][["meta", "real", "tendencia"]].sum()
    total = {"cesta": "TOTAL", "indicador": "Total (Cerveja + Nab)", "meta": tot["meta"], "real": tot["real"],
             "tendencia": tot["tendencia"],
             "ating_real": tot["real"] / tot["meta"] * 100 if tot["meta"] else None,
             "ating_tend": tot["tendencia"] / tot["meta"] * 100 if tot["meta"] else None,
             "pendencia": tot["real"] - tot["meta"]}
    df = pd.concat([df, pd.DataFrame([total])], ignore_index=True)
    df.attrs.update(dias_preenchidos=preenchidos, dias_periodo=dias_total, fator=fator)
    return df


def dia_a_dia(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    d = ressuprimento_repo.diario_df(operacao_id, mes_ano)
    if d.empty:
        return d
    d["indicador"] = d["cesta"].map(nome_cesta)
    piv = d.pivot_table(index="data", columns="indicador", values="volume_real_hl", aggfunc="sum", fill_value=0)
    piv["Total do dia"] = piv.sum(axis=1)
    piv.index = [dt.date.fromisoformat(x).strftime("%d/%m/%Y") for x in piv.index]
    return piv.reset_index(names="Dia")
