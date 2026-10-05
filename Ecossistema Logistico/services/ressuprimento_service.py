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


# --- Real do mês ---------------------------------------------------------------------
# O relatório diário traz, para cada filial (A) + indicador (E) + data (F), o HL da coluna C.
# Esse número é o ACUMULADO do mês até a data — por isso o real do mês é o valor da última data
# (cruzamento indicador × data), e não a soma dos dias. Se a base trouxer volumes do dia
# (série que sobe e desce), o sistema percebe e soma, como antes.
def _mes(mes_ano: str) -> tuple[str, str]:
    return f"{mes_ano}-01", f"{mes_ano}-{_dias_mes(mes_ano):02d}"


def base_acumulada(operacao_id: int) -> bool:
    """True quando a coluna C é o acumulado do mês (série de cada indicador nunca diminui ao longo do mês)."""
    d = ressuprimento_repo.diario_ops_df(operacao_id)
    if d.empty:
        return True
    d = d.assign(mes=d["data"].str[:7])
    votos = []
    for _, g in d.groupby(["operacao_id", "cesta", "mes"]):
        v = pd.to_numeric(g.sort_values("data")["volume_real_hl"], errors="coerce").fillna(0).tolist()
        if len(v) >= 4 and max(v) > 0:
            votos.append(all(b >= a * 0.995 for a, b in zip(v, v[1:])))
    return True if not votos else sum(votos) >= 0.6 * len(votos)


def diario_normalizado(operacao_id: int, mes_ano: str, acumulado: bool | None = None) -> pd.DataFrame:
    """Por data e indicador: `dia` (HL do dia) e `acum` (acumulado do mês), somando as filiais."""
    de, ate = _mes(mes_ano)
    d = ressuprimento_repo.diario_ops_df(operacao_id, de, ate)
    if d.empty:
        return pd.DataFrame(columns=["data", "cesta", "dia", "acum", "dia_sellin", "acum_sellin"])
    acumulado = base_acumulada(operacao_id) if acumulado is None else acumulado
    partes = []
    for _, g in d.groupby(["operacao_id", "cesta"]):
        g = g.sort_values("data").copy()
        for col, dia, acum in (("volume_real_hl", "dia", "acum"), ("volume_sellin_hl", "dia_sellin", "acum_sellin")):
            v = pd.to_numeric(g[col], errors="coerce").fillna(0.0)
            if acumulado:
                g[acum] = v
                g[dia] = v.diff().fillna(v).clip(lower=0)
            else:
                g[dia] = v
                g[acum] = v.cumsum()
        partes.append(g)
    d = pd.concat(partes)
    return (d.groupby(["data", "cesta"], as_index=False)[["dia", "acum", "dia_sellin", "acum_sellin"]].sum()
            .sort_values(["data", "cesta"]).reset_index(drop=True))


def real_do_mes(operacao_id: int, mes_ano: str, acumulado: bool | None = None) -> tuple[pd.Series, pd.Series, str | None]:
    """(real por indicador, sell-in por indicador, última data com dado). Real = valor da última data de cada filial."""
    de, ate = _mes(mes_ano)
    d = ressuprimento_repo.diario_ops_df(operacao_id, de, ate)
    if d.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), None
    acumulado = base_acumulada(operacao_id) if acumulado is None else acumulado
    for c in ("volume_real_hl", "volume_sellin_hl"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d = d.sort_values("data")
    if acumulado:
        por_op = d.groupby(["operacao_id", "cesta"]).last()
    else:
        por_op = d.groupby(["operacao_id", "cesta"])[["volume_real_hl", "volume_sellin_hl"]].sum()
    real = por_op.groupby("cesta")["volume_real_hl"].sum()
    sellin = por_op.groupby("cesta")["volume_sellin_hl"].sum()
    return real, sellin, str(d["data"].max())


def dia_referencia(operacao_id: int, mes_ano: str) -> int:
    """Último dia com lançamento no mês (base da projeção)."""
    d = ressuprimento_repo.diario_df(operacao_id, mes_ano)
    if d.empty:
        return 0
    return dt.date.fromisoformat(d["data"].max()).day


def aderencia_mensal(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    real, sellin, _ = real_do_mes(operacao_id, mes_ano)
    metas = ressuprimento_repo.metas_df(operacao_id, mes_ano).rename(columns={"meta_volume_hl": "meta_hl"})
    colunas = ["cesta", "real_hl", "sellin_hl", "meta_hl", "projecao_hl", "aderencia_sellin", "atingimento",
               "atingimento_proj"]
    if real.empty and metas.empty:
        return pd.DataFrame(columns=colunas)
    agg = (pd.DataFrame({"cesta": real.index, "real_hl": real.values, "sellin_hl": sellin.reindex(real.index).values})
           if not real.empty else pd.DataFrame(columns=["cesta", "sellin_hl", "real_hl"]))
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
    d = diario_normalizado(operacao_id, mes_ano)
    d = d[d["cesta"] == cesta].sort_values("data").copy()
    d["volume_real_hl"], d["volume_sellin_hl"] = d["dia"], d["dia_sellin"]
    d["real_acum"] = d["acum"]
    d["sellin_acum"] = d["acum_sellin"]
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
    hoje = tempo.hoje()
    reais, tends, metas, dias_total, dias_com_dado = [], [], [], 0, set()
    acumulado = base_acumulada(operacao_id)
    for m in meses:
        mes_ano = f"{ano}-{m:02d}"
        r, _, ultima = real_do_mes(operacao_id, mes_ano, acumulado)
        if not r.empty:
            reais.append(r)
            # tendência: só no mês corrente — projeta o acumulado até o fim do mês pelo último dia com dado
            ref = dt.date.fromisoformat(ultima).day if ultima else 0
            corrente = (ano, m) == (hoje.year, hoje.month)
            tends.append(r * (_dias_mes(mes_ano) / ref if corrente and ref else 1.0))
            d = ressuprimento_repo.diario_df(operacao_id, mes_ano)
            dias_com_dado |= set(d["data"])
        metas.append(ressuprimento_repo.metas_df(operacao_id, mes_ano))
        dias_total += _dias_mes(mes_ano)
    real = pd.concat(reais).groupby(level=0).sum() if reais else pd.Series(dtype=float)
    tend = pd.concat(tends).groupby(level=0).sum() if tends else pd.Series(dtype=float)
    meta = (pd.concat(metas).groupby("cesta")["meta_volume_hl"].sum() if metas else pd.Series(dtype=float))

    cestas = list(CESTAS) + sorted((set(real.index) | set(meta.index)) - set(CESTAS))
    df = pd.DataFrame({"cesta": cestas})
    df["indicador"] = df["cesta"].map(nome_cesta)
    df["meta"] = df["cesta"].map(meta).fillna(0.0)
    df["real"] = df["cesta"].map(real).fillna(0.0)
    df = df[(df["meta"] > 0) | (df["real"] > 0) | df["cesta"].isin(CESTAS)]
    preenchidos = len(dias_com_dado)
    df["tendencia"] = df["cesta"].map(tend).fillna(0.0)
    fator = float(df["tendencia"].sum() / df["real"].sum()) if df["real"].sum() else 1.0
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
    d = diario_normalizado(operacao_id, mes_ano)
    if d.empty:
        return d
    d["indicador"] = d["cesta"].map(nome_cesta)
    piv = d.pivot_table(index="data", columns="indicador", values="dia", aggfunc="sum", fill_value=0)
    piv["Total do dia"] = piv.sum(axis=1)
    piv.index = [dt.date.fromisoformat(x).strftime("%d/%m/%Y") for x in piv.index]
    return piv.reset_index(names="Dia")
