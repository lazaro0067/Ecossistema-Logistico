"""Gestão Corporativa › Logística › Produtividade › 🚚 Produtividade Entrega.

Duas bases, que vão se acumulando (subir de novo um período substitui só as datas do arquivo):

• PCD (relatório de mapas/roteirização): uma linha por mapa — data de entrega, placa, veículo, entregas,
  total de caixas, % ocupação caixas, total peso, % ocupação peso, KM previsto, classificação…
• 03.02.37 (notas por item): coluna T = quantidade (caixas/unidades) de cada produto, coluna AA = mapa.
  HL = quantidade × fator HL do produto (base 01.11); produtos em litros (chopp, bag in box) = litros ÷ 100.
  Filtro padrão: operação 1, tipo de movimento 51, status A (venda ativa) — dá para mudar na tela.

O HL de cada mapa vem da 03.02.37 e é ligado ao PCD pelo número do mapa.
"""
import datetime as dt
import io
import re
import unicodedata
import zipfile

import pandas as pd

from config.settings import FILTRO_PADRAO_NOTAS, MODAIS
from core import tempo
from database.connection import get_conn, query_df
from repositories import operacoes_repo
from services.erros import RegraNegocioError

ORDEM_MODAIS = list(MODAIS)


# --- utilidades --------------------------------------------------------------------------------
def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()


def _mapa(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0")


def _cod(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0") or "0"


def _num(s: pd.Series) -> pd.Series:
    """'1.234,56' / '91,20 ' / '383.04' → float."""
    t = s.astype(str).str.strip()
    br = t.str.contains(",", regex=False)
    t = t.where(~br, t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(t, errors="coerce")


def _data(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.strip(), format="%d/%m/%Y", errors="coerce").dt.strftime("%Y-%m-%d")


def _abrir(conteudo: bytes, nome: str) -> bytes:
    """Aceita .csv ou .zip (com o .csv dentro) — o 03.02.37 compactado sobe bem mais rápido."""
    if nome.lower().endswith(".zip") or conteudo[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            csvs = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
            if not csvs:
                raise RegraNegocioError("O .zip não tem nenhum .csv dentro.")
            return z.read(csvs[0])
    return conteudo


def _ler_csv(conteudo: bytes, **kw) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin1"):
        try:
            return pd.read_csv(io.BytesIO(conteudo), sep=";", dtype=str, encoding=enc, **kw)
        except UnicodeDecodeError:
            continue
    raise RegraNegocioError("Não consegui ler o arquivo (formato/codificação).")


def _log(operacao_id: int, base: str, linhas: int, arquivo: str, usuario: str) -> None:
    from database.connection import execute

    execute("INSERT INTO bases_log (operacao_id, base, linhas, arquivo, usuario, dt) VALUES (?, ?, ?, ?, ?, ?)",
            (operacao_id, base, linhas, arquivo, usuario, tempo.agora().strftime("%Y-%m-%d %H:%M:%S")))


def _py(v):
    """Valor pronto para o banco (sem tipos do numpy/pandas)."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def _gravar(tabela: str, operacao_id_por_linha: pd.Series, df: pd.DataFrame) -> None:
    """Substitui as datas do arquivo (por filial) e grava as linhas novas."""
    agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    df = df.assign(operacao_id=operacao_id_por_linha.values, importado_em=agora)
    cols = list(df.columns)
    with get_conn() as conn:
        for (op, data), _ in df.groupby(["operacao_id", "data"]):
            conn.execute(f"DELETE FROM {tabela} WHERE operacao_id = ? AND data = ?", (int(op), data))
        linhas = [tuple(_py(v) for v in r) for r in df.itertuples(index=False)]
        conn.executemany(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", linhas)


# --- Importação: PCD -----------------------------------------------------------------------------
_PCD = {  # coluna do relatório → campo
    "nome unb": "unb", "data entrega": "data", "nro do mapa": "mapa", "nro do roadshow": "roadshow",
    "placa": "placa", "veiculo": "veiculo", "nome transportadora": "transportadora", "motorista": "motorista",
    "carga": "carga", "classificacao": "classificacao", "km prev.": "km_prev", "tempo prev. (+almoco)": "tempo_prev",
    "entregas": "entregas", "total de caixas": "caixas", "% ocupacao caixas": "ocup_cx", "total peso": "peso",
    "% ocupacao peso": "ocup_peso", "% tempo": "pct_tempo", "% eficiencia": "eficiencia", "roteirizado": "roteirizado",
    "carga atual": "carga_atual", "cidades +entregas": "cidades", "regiao +entregas": "regiao",
}


def importar_pcd(conteudo: bytes, nome: str, operacao_padrao: int, usuario: str = "") -> dict:
    df = _ler_csv(_abrir(conteudo, nome))
    df.columns = [_n(c) for c in df.columns]
    falta = [c for c in ("data entrega", "nro do mapa", "placa", "entregas", "total de caixas", "total peso")
             if c not in df.columns]
    if falta:
        raise RegraNegocioError("Este arquivo não parece o relatório de mapas (PCD). Faltam as colunas: "
                                + ", ".join(falta))
    df = df[[c for c in _PCD if c in df.columns]].rename(columns=_PCD)
    df["data"] = _data(df["data"])
    df["mapa"] = df["mapa"].map(_mapa)
    df = df[df["data"].notna() & (df["mapa"] != "")]
    if df.empty:
        raise RegraNegocioError("Nenhum mapa com data válida no arquivo.")
    for c in ("km_prev", "caixas", "ocup_cx", "peso", "ocup_peso", "pct_tempo", "eficiencia"):
        if c in df:
            df[c] = _num(df[c])
    df["entregas"] = _num(df["entregas"]).fillna(0).astype(int)
    df["placa"] = df["placa"].fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    for c in ("veiculo", "classificacao", "transportadora", "carga"):
        if c in df:
            df[c] = df[c].fillna("").str.strip()
    if "classificacao" in df:  # "Padrao"/"PADRAO", "Longa Distancia"/"Longa Distância"…
        df["classificacao"] = df["classificacao"].map(_classificacao)
    # filial pela coluna "Nome UNB" (quando reconhecida); senão a revenda escolhida
    ops = (df.pop("unb").map(lambda t: operacoes_repo.resolver_por_texto(t) if t else None)
           if "unb" in df else pd.Series([None] * len(df)))
    ops = ops.fillna(operacao_padrao).astype(int)
    df = df.drop_duplicates(["data", "mapa"], keep="last")
    ops = ops.loc[df.index]
    _gravar("entregas_mapas", ops, df)
    for op in ops.unique():
        _log(int(op), "entregas_pcd", int((ops == op).sum()), nome, usuario)
    return {"linhas": len(df), "de": df["data"].min(), "ate": df["data"].max(),
            "revendas": [(operacoes_repo.buscar(int(o)) or {}).get("nome") for o in ops.unique()]}


def _classificacao(t: str) -> str:
    n = _n(t)
    if not n:
        return "Sem classificação"
    if "padr" in n:
        return "Padrão"
    if "longa" in n:
        return "Longa Distância"
    if "apoio" in n:
        return "Ponto de Apoio"
    if "integr" in n:
        return "Integração"
    return str(t).strip().title() if str(t).strip().isupper() else str(t).strip()


# --- Importação: 03.02.37 ---------------------------------------------------------------------------
# posições (A = 0): C operação, D tipo movto, G emissão, H nota, J status, M cliente, P produto,
# Q unidade, T quantidade, Z total (R$), AA mapa
_POS_NOTAS = {2: "operacao_cod", 3: "tipo_movto", 6: "data", 7: "nota", 9: "status", 12: "cliente", 15: "produto",
              16: "unidade", 19: "qtde", 25: "valor", 26: "mapa"}


def importar_notas(conteudo: bytes, nome: str, operacao_id: int, usuario: str = "") -> dict:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir a 03.02.37.")
    bruto = _abrir(conteudo, nome)
    cab = _ler_csv(bruto, nrows=0)
    if len(cab.columns) < 27 or "qtde" not in _n(cab.columns[19]) or "mapa" not in _n(cab.columns[26]):
        raise RegraNegocioError("Este arquivo não parece a 03.02.37: esperava “Qtde” na coluna T e “Mapa” na "
                                "coluna AA.")
    df = _ler_csv(bruto, usecols=list(_POS_NOTAS))
    df.columns = [_POS_NOTAS[i] for i in sorted(_POS_NOTAS)]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    df["data"] = _data(df["data"])
    df["mapa"] = df["mapa"].map(_mapa)
    df = df[df["data"].notna() & (df["mapa"] != "")].copy()
    if df.empty:
        raise RegraNegocioError("Nenhuma nota com mapa e data de emissão válidos.")
    for c in ("operacao_cod", "tipo_movto"):
        df[c] = df[c].map(_cod)
    df["status"] = df["status"].str.upper().replace("", "?")
    df["qtde"] = _num(df["qtde"]).fillna(0.0)
    df["valor"] = _num(df["valor"]).fillna(0.0)
    df["cod"] = pd.to_numeric(df["produto"].str.replace(r"\D", "", regex=True), errors="coerce")
    fat = query_df("SELECT cod, fator_hl FROM produtos")
    fat["cod"] = pd.to_numeric(fat["cod"], errors="coerce")
    df = df.merge(fat.dropna().drop_duplicates("cod"), on="cod", how="left")
    litros = df["unidade"].str.lower().isin(["l", "lt", "lts", "litro", "litros"])
    df["hl"] = (df["qtde"] * df["fator_hl"].fillna(0.0)).where(~litros, df["qtde"] / 100)
    sem_fator = df.loc[~litros & df["fator_hl"].isna(), "produto"].nunique()
    agg = (df.groupby(["data", "mapa", "operacao_cod", "tipo_movto", "status"], as_index=False)
             .agg(hl=("hl", "sum"), qtde=("qtde", "sum"), notas=("nota", "nunique"), clientes=("cliente", "nunique"),
                  valor=("valor", "sum")))
    _gravar("entregas_notas", pd.Series([operacao_id] * len(agg)), agg)
    _log(operacao_id, "entregas_notas", len(df), nome, usuario)
    return {"itens": len(df), "mapas": agg["mapa"].nunique(), "de": agg["data"].min(), "ate": agg["data"].max(),
            "hl": float(agg["hl"].sum()), "sem_fator": int(sem_fator), "sem_cadastro": fat.empty}


# --- Consulta --------------------------------------------------------------------------------------
def periodo_disponivel(operacao_id: int) -> tuple[str | None, str | None]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_df(f"SELECT MIN(data) AS de, MAX(data) AS ate FROM entregas_mapas WHERE {trecho}", p)
    return (r.iloc[0]["de"], r.iloc[0]["ate"]) if not r.empty else (None, None)


def meses_disponiveis(operacao_id: int) -> list[str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_df(f"SELECT DISTINCT substr(data, 1, 7) AS m FROM entregas_mapas WHERE {trecho} ORDER BY m DESC", p)
    return r["m"].tolist()


def opcoes_filtro(operacao_id: int) -> dict[str, list[str]]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT DISTINCT operacao_cod, tipo_movto, status FROM entregas_notas WHERE {trecho}", p)
    ordenar = lambda s: sorted(s.dropna().unique().tolist(), key=lambda x: (len(x), x))  # noqa: E731
    return {"operacao": ordenar(df["operacao_cod"]), "tipo_movto": ordenar(df["tipo_movto"]),
            "status": ordenar(df["status"])}


def filtro_padrao(opcoes: dict[str, list[str]]) -> dict[str, list[str]]:
    return {k: [v for v in FILTRO_PADRAO_NOTAS[k] if v in opcoes.get(k, [])] or opcoes.get(k, []) for k in opcoes}


def _placas() -> pd.DataFrame:
    from repositories import frota_repo

    p = frota_repo.placas_df()
    if p.empty:
        return pd.DataFrame(columns=["placa_k", "tipo_cad", "modelo", "proprietario", "aluguel", "locadora", "area",
                                     "revenda_cad", "status_cad"])
    p["placa_k"] = p["placa"].astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    return p.rename(columns={"tipo": "tipo_cad", "marca_modelo": "modelo", "revenda": "revenda_cad",
                             "status": "status_cad"})[["placa_k", "tipo_cad", "modelo", "proprietario", "aluguel",
                                                       "locadora", "area", "revenda_cad", "status_cad"]] \
        .drop_duplicates("placa_k")


def base(operacao_id: int, de: str, ate: str, filtro: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Uma linha por mapa (viagem) no período, com o HL da 03.02.37 (filtrado) e o cadastro da placa."""
    trecho, p = operacoes_repo.filtro("m.operacao_id", operacao_id)
    m = query_df(f"""SELECT m.*, o.nome AS revenda FROM entregas_mapas m JOIN operacoes o ON o.id = m.operacao_id
                     WHERE {trecho} AND m.data BETWEEN ? AND ? ORDER BY m.data, m.mapa""", [*p, de, ate])
    if m.empty:
        return m
    trecho_n, pn = operacoes_repo.filtro("operacao_id", operacao_id)
    sql = f"SELECT operacao_id, mapa, SUM(hl) AS hl, SUM(qtde) AS volumes, SUM(notas) AS notas, " \
          f"SUM(valor) AS valor FROM entregas_notas WHERE {trecho_n}"
    params = list(pn)
    for campo, col in (("operacao", "operacao_cod"), ("tipo_movto", "tipo_movto"), ("status", "status")):
        vals = (filtro or {}).get(campo)
        if vals:
            sql += f" AND {col} IN ({', '.join('?' * len(vals))})"
            params += list(vals)
    n = query_df(sql + " GROUP BY operacao_id, mapa", params)
    m = m.merge(n, on=["operacao_id", "mapa"], how="left")
    m["tem_hl"] = m["hl"].notna()
    for c in ("hl", "volumes", "notas", "valor"):
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0.0)
    for c in ("km_prev", "caixas", "ocup_cx", "peso", "ocup_peso", "pct_tempo", "eficiencia", "entregas"):
        m[c] = pd.to_numeric(m[c], errors="coerce")
    m["ocup_efetiva"] = m[["ocup_cx", "ocup_peso"]].max(axis=1)
    m["data"] = pd.to_datetime(m["data"])
    m["mes"] = m["data"].dt.strftime("%Y-%m")
    m["placa_k"] = m["placa"].fillna("").str.upper()
    m = m.merge(_placas(), on="placa_k", how="left")
    m["veiculo"] = m["veiculo"].replace("", None).fillna(m["tipo_cad"]).fillna("Não informado")
    return m


def resumo(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    v = len(df)
    return {"viagens": v, "placas": df["placa"].nunique(), "dias": df["data"].nunique(),
            "entregas": int(df["entregas"].sum()), "hl": float(df["hl"].sum()),
            "ocup_cx": float(df["ocup_cx"].mean()), "ocup_peso": float(df["ocup_peso"].mean()),
            "ocup_efetiva": float(df["ocup_efetiva"].mean()), "peso_medio": float(df["peso"].mean()),
            "km_total": float(df["km_prev"].sum()), "km_medio": float(df["km_prev"].mean()),
            "caixas_media": float(df["caixas"].mean()), "eficiencia": float(df["eficiencia"].mean()),
            "hl_viagem": float(df["hl"].sum() / v), "hl_entrega": float(df["hl"].sum() / max(df["entregas"].sum(), 1)),
            "entregas_viagem": float(df["entregas"].sum() / v), "sem_hl": int((~df["tem_hl"]).sum())}


def _agrupar(df: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    g = df.groupby(chaves, dropna=False).agg(
        viagens=("mapa", "count"), dias=("data", "nunique"), entregas=("entregas", "sum"), hl=("hl", "sum"),
        ocup_cx=("ocup_cx", "mean"), ocup_peso=("ocup_peso", "mean"), ocup_efetiva=("ocup_efetiva", "mean"),
        peso_medio=("peso", "mean"), km_total=("km_prev", "sum"), km_medio=("km_prev", "mean"),
        caixas_media=("caixas", "mean"), eficiencia=("eficiencia", "mean"),
    ).reset_index()
    g["hl_viagem"] = g["hl"] / g["viagens"]
    g["hl_entrega"] = g["hl"] / g["entregas"].where(g["entregas"] > 0)
    g["entregas_viagem"] = g["entregas"] / g["viagens"]
    return g


def por_placa(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    g = _agrupar(df, ["placa"])
    info = (df.sort_values("data").groupby("placa").agg(
        veiculo=("veiculo", "last"), revenda=("revenda", "last"), transportadora=("transportadora", "last"),
        modelo=("modelo", "last"), proprietario=("proprietario", "last"), aluguel=("aluguel", "last"),
        locadora=("locadora", "last"), area=("area", "last"), status_cad=("status_cad", "last")).reset_index())
    return info.merge(g, on="placa").sort_values("hl", ascending=False).reset_index(drop=True)


def por_veiculo(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    g = _agrupar(df, ["veiculo"])
    g["placas"] = g["veiculo"].map(df.groupby("veiculo")["placa"].nunique())
    ordem = {t: i for i, t in enumerate(ORDEM_MODAIS)}
    return g.sort_values("veiculo", key=lambda s: s.map(lambda x: ordem.get(x, 99))).reset_index(drop=True)


def por_classificacao(df: pd.DataFrame) -> pd.DataFrame:
    return _agrupar(df, ["classificacao"]).sort_values("viagens", ascending=False) if not df.empty else df


def diario(df: pd.DataFrame) -> pd.DataFrame:
    return _agrupar(df, ["data"]).assign(placas=lambda g: g["data"].map(df.groupby("data")["placa"].nunique())) \
        if not df.empty else df


def mensal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    g = _agrupar(df, ["mes"])
    g["placas"] = g["mes"].map(df.groupby("mes")["placa"].nunique())
    return g.sort_values("mes").reset_index(drop=True)


# --- Previsão de modais ------------------------------------------------------------------------------
def capacidades(df: pd.DataFrame) -> pd.DataFrame:
    """Capacidade de cada modal: mediana real da frota (caixas ÷ % ocupação), ou o padrão do sistema."""
    linhas = []
    for t, (cx_p, kg_p) in MODAIS.items():
        s = df[df["veiculo"] == t] if not df.empty else df
        cx = (s["caixas"] / s["ocup_cx"] * 100).replace([float("inf")], pd.NA).dropna() if not s.empty else []
        kg = (s["peso"] / s["ocup_peso"] * 100).replace([float("inf")], pd.NA).dropna() if not s.empty else []
        linhas.append({"modal": t, "cap_cx": float(pd.Series(cx).median()) if len(cx) >= 5 else float(cx_p),
                       "cap_kg": float(pd.Series(kg).median()) if len(kg) >= 5 else float(kg_p),
                       "origem": "frota real" if len(cx) >= 5 else "padrão"})
    return pd.DataFrame(linhas)


def modais(df: pd.DataFrame, limite: float = 100.0) -> dict:
    """Para cada viagem, o menor modal em que a carga (caixas e peso) cabe até `limite`% da capacidade."""
    if df.empty:
        return {}
    cap = capacidades(df).set_index("modal")
    lim = limite / 100

    def ideal(r) -> str:
        for t in ORDEM_MODAIS:
            if (pd.isna(r["caixas"]) or r["caixas"] <= cap.at[t, "cap_cx"] * lim) and \
               (pd.isna(r["peso"]) or r["peso"] <= cap.at[t, "cap_kg"] * lim):
                return t
        return ORDEM_MODAIS[-1]

    d = df.copy()
    d["ideal"] = d.apply(ideal, axis=1)
    pos = {t: i for i, t in enumerate(ORDEM_MODAIS)}
    # o veículo que rodou tem a própria capacidade (há Toco maior que o padrão): se a carga coube nele
    # (ocupação ≤ limite), ele não "precisava de maior"
    coube = d["ocup_efetiva"].le(limite) & d["veiculo"].isin(ORDEM_MODAIS)
    maior = d.apply(lambda r: r["veiculo"] in pos and pos[r["ideal"]] > pos[r["veiculo"]], axis=1)
    d.loc[coube & maior, "ideal"] = d.loc[coube & maior, "veiculo"]
    d["ajuste"] = [("—" if a not in pos else "✅ Modal certo" if pos[a] == pos[i] else
                    "⬇️ Cabe em menor" if pos[i] < pos[a] else "⬆️ Precisa maior")
                   for a, i in zip(d["veiculo"], d["ideal"])]
    matriz = pd.crosstab(d["veiculo"], d["ideal"]).reindex(columns=ORDEM_MODAIS, fill_value=0)
    por_dia_ideal = d.groupby([d["data"].dt.date, "ideal"]).size().unstack(fill_value=0) \
        .reindex(columns=ORDEM_MODAIS, fill_value=0)
    por_dia_atual = d.groupby([d["data"].dt.date, "veiculo"]).size().unstack(fill_value=0)
    prev = []
    for t in ORDEM_MODAIS:
        s_i = por_dia_ideal[t] if t in por_dia_ideal else pd.Series([0])
        s_a = por_dia_atual[t] if t in por_dia_atual else pd.Series([0] * max(len(por_dia_ideal), 1))
        prev.append({"modal": t, "cap_cx": cap.at[t, "cap_cx"], "cap_kg": cap.at[t, "cap_kg"],
                     "atual_media": float(s_a.mean()), "atual_max": int(s_a.max()),
                     "placas_atuais": int(d.loc[d["veiculo"] == t, "placa"].nunique()),
                     "ideal_media": float(s_i.mean()), "ideal_p80": float(s_i.quantile(.8)),
                     "ideal_p90": float(s_i.quantile(.9)), "ideal_max": int(s_i.max()),
                     "viagens_ideal": int((d["ideal"] == t).sum()), "viagens_atual": int((d["veiculo"] == t).sum())})
    prev = pd.DataFrame(prev)
    prev["sugerido"] = prev["ideal_p80"].apply(lambda v: int(-(-v // 1)))  # arredonda para cima
    semana = d.assign(dow=d["data"].dt.dayofweek).groupby(["dow", "ideal"]).size().unstack(fill_value=0) \
        .reindex(columns=ORDEM_MODAIS, fill_value=0)
    n_dias = d.assign(dow=d["data"].dt.dayofweek).groupby("dow")["data"].nunique()
    semana = semana.div(n_dias, axis=0).round(1)
    classif = pd.crosstab(d["classificacao"], d["ideal"]).reindex(columns=ORDEM_MODAIS, fill_value=0)
    return {"viagens": d, "matriz": matriz, "previsao": prev, "semana": semana, "classificacao": classif,
            "capacidades": cap.reset_index(),
            "certo": int((d["ajuste"] == "✅ Modal certo").sum()), "menor": int((d["ajuste"] == "⬇️ Cabe em menor").sum()),
            "maior": int((d["ajuste"] == "⬆️ Precisa maior").sum()), "total": len(d)}


def ultimas_cargas(operacao_id: int) -> dict:
    from database.connection import query_one

    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = {}
    for base_ in ("entregas_pcd", "entregas_notas"):
        x = query_one(f"SELECT MAX(dt) AS dt FROM bases_log WHERE base = ? AND {trecho}", (base_, *p))
        r[base_] = x["dt"] if x else None
    return r


def hoje_iso() -> str:
    return dt.date.today().isoformat()
