"""Estoque valorizado (relatório 02.05.02) — saldo inicial e saldo final do mês — e DRE.

Leitura do 02.05.02 (A = 0):
  A armazém · B depósito · D produto · E descrição · F unidade · W tipo · X fator (unidades por unidade de venda)
  · Y custo médio · AB quantidade em UNIDADES · AD valor do estoque a custo médio (Estoque CM) · AE valor a última
  reposição.
  Unidade de venda = AB ÷ X; HL = unidade de venda × fator HL da 01.11 (produtos em litros: litros ÷ 100).

Lucro bruto "de verdade" (pelo estoque):
  CMV = estoque inicial + compras − estoque final   ·   Lucro bruto = faturamento − CMV
"""
import calendar
import datetime as dt

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services.erros import RegraNegocioError

TIPOS_SALDO = {"inicial": "Saldo inicial do mês", "final": "Saldo final do mês"}
_POS = {0: "armazem", 1: "deposito", 3: "produto", 4: "descricao", 5: "unidade", 22: "tipo", 23: "fator",
        24: "custo_medio", 27: "qtd_unid", 29: "valor", 30: "valor_ur"}


def _num(s: pd.Series) -> pd.Series:
    t = s.astype(str).str.strip()
    neg = t.str.endswith("-") | t.str.startswith("-")
    t = t.str.strip("-").str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    v = pd.to_numeric(t, errors="coerce")
    return v.where(~neg, -v)


def mes_anterior(mes: str) -> str:
    a, m = map(int, mes.split("-"))
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


def mes_seguinte(mes: str) -> str:
    a, m = map(int, mes.split("-"))
    return f"{a + 1}-01" if m == 12 else f"{a}-{m + 1:02d}"


# --- Importação ----------------------------------------------------------------------------------------
def importar(conteudo: bytes, nome: str, operacao_id: int, mes: str, tipo_saldo: str, usuario: str = "") -> dict:
    from services.produtividade_entrega_service import _abrir, _ler_csv, _log, _n, _py

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir o 02.05.02.")
    if tipo_saldo not in TIPOS_SALDO:
        raise RegraNegocioError("Escolha se é o saldo inicial ou o saldo final.")
    bruto = _abrir(conteudo, nome)
    cab = _ler_csv(bruto, nrows=0)
    if len(cab.columns) < 31 or "qtd" not in _n(cab.columns[27]) or "estoque" not in _n(cab.columns[29]):
        raise RegraNegocioError("Este arquivo não parece o 02.05.02: esperava “Qtd Estoque” na coluna AB e "
                                "“Estoque CM” na coluna AD.")
    df = _ler_csv(bruto, usecols=list(_POS))
    df.columns = [_POS[i] for i in sorted(_POS)]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    for c in ("fator", "custo_medio", "qtd_unid", "valor", "valor_ur"):
        df[c] = _num(df[c])
    df = df[df["produto"].str.replace(r"\D", "", regex=True) != ""].copy()
    df["produto"] = df["produto"].str.replace(r"\D", "", regex=True).str.lstrip("0")
    df["fator"] = df["fator"].where(df["fator"] > 0, 1.0)
    df["qtd_venda"] = df["qtd_unid"] / df["fator"]
    fat = query_df("SELECT cod, fator_hl FROM produtos")
    fat["produto"] = pd.to_numeric(fat["cod"], errors="coerce").astype("Int64").astype(str)
    df = df.merge(fat[["produto", "fator_hl"]].drop_duplicates("produto"), on="produto", how="left")
    litros = df["unidade"].str.lower().isin(["l", "lt", "lts", "litro", "litros"])
    df["hl"] = (df["qtd_venda"] * pd.to_numeric(df["fator_hl"], errors="coerce").fillna(0.0)).where(
        ~litros, df["qtd_unid"] / 100)
    sem_fator = int((~litros & df["fator_hl"].isna()).sum())
    df = df.drop(columns=["fator_hl"])
    agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    df = df.assign(operacao_id=operacao_id, mes=mes, tipo_saldo=tipo_saldo, importado_em=agora)
    cols = list(df.columns)
    with get_conn() as conn:
        conn.execute("DELETE FROM estoque_saldos WHERE operacao_id = ? AND mes = ? AND tipo_saldo = ?",
                     (operacao_id, mes, tipo_saldo))
        conn.executemany(f"INSERT INTO estoque_saldos ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         [tuple(_py(v) for v in r) for r in df.itertuples(index=False)])
    _log(operacao_id, f"estoque_{tipo_saldo}", len(df), nome, usuario)
    return {"itens": len(df), "valor": float(df["valor"].sum()), "hl": float(df["hl"].sum()),
            "depositos": int(df["deposito"].nunique()), "sem_fator": sem_fator}


# --- Depósitos ---------------------------------------------------------------------------------------
def nomes_depositos() -> dict[tuple[str, str], str]:
    df = query_df("SELECT armazem, deposito, nome FROM depositos_nomes")
    return {(a, d): n for a, d, n in zip(df["armazem"], df["deposito"], df["nome"]) if n}


def rotulo_deposito(armazem: str, deposito: str, nomes: dict | None = None) -> str:
    nomes = nomes if nomes is not None else nomes_depositos()
    n = nomes.get((str(armazem), str(deposito)))
    return f"Arm. {armazem} · Dep. {deposito}" + (f" — {n}" if n else "")


def salvar_nome_deposito(armazem: str, deposito: str, nome: str) -> None:
    execute("""INSERT INTO depositos_nomes (armazem, deposito, nome) VALUES (?, ?, ?)
               ON CONFLICT(armazem, deposito) DO UPDATE SET nome = excluded.nome""",
            (str(armazem), str(deposito), (nome or "").strip()))


def depositos_cmv() -> list[str] | None:
    """Depósitos ("AA-DD") que entram no estoque do CMV/DRE. None = todos."""
    from services import faturamento_service as fs

    df = query_df("SELECT codigo FROM setor_operacoes WHERE setor = 'estoque_deposito'")
    return df["codigo"].tolist() if not df.empty else None


def salvar_depositos_cmv(codigos: list[str]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM setor_operacoes WHERE setor = 'estoque_deposito'")
        conn.executemany("INSERT INTO setor_operacoes (setor, codigo) VALUES ('estoque_deposito', ?)",
                         [(c,) for c in codigos])


# --- Consulta -----------------------------------------------------------------------------------------
def meses(operacao_id: int) -> list[str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_df(f"SELECT DISTINCT mes FROM estoque_saldos WHERE {trecho} ORDER BY mes DESC", p)
    return r["mes"].tolist()


def _bruto(operacao_id: int, mes: str, tipo_saldo: str) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("s.operacao_id", operacao_id)
    df = query_df(f"""SELECT s.*, pr.tipo AS tipo_prod, pr.categoria FROM estoque_saldos s
                      LEFT JOIN produtos pr ON CAST(pr.cod AS TEXT) = s.produto
                      WHERE {trecho} AND s.mes = ? AND s.tipo_saldo = ?""", (*p, mes, tipo_saldo))
    for c in ("fator", "qtd_unid", "qtd_venda", "custo_medio", "valor", "valor_ur", "hl"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


def saldo(operacao_id: int, mes: str, tipo_saldo: str, so_cmv: bool = False) -> tuple[pd.DataFrame, str]:
    """Saldo do mês. Sem o inicial, usa o final do mês anterior (e vice-versa). Devolve (dados, de onde veio)."""
    df = _bruto(operacao_id, mes, tipo_saldo)
    origem = f"{TIPOS_SALDO[tipo_saldo].lower()} de {mes[5:]}/{mes[:4]}"
    if df.empty:
        alt_mes, alt_tipo = (mes_anterior(mes), "final") if tipo_saldo == "inicial" else (mes_seguinte(mes), "inicial")
        df = _bruto(operacao_id, alt_mes, alt_tipo)
        origem = f"{TIPOS_SALDO[alt_tipo].lower()} de {alt_mes[5:]}/{alt_mes[:4]}" if not df.empty else "sem saldo"
    if so_cmv and not df.empty:
        deps = depositos_cmv()
        if deps:
            df = df[(df["armazem"] + "-" + df["deposito"]).isin(deps)]
    return df, origem


def enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    from services import produtos_service as ps

    if df.empty:
        return df
    df = df.copy()
    df["tipo_prod"] = df["tipo_prod"].fillna("").map(
        lambda t: {"CERVEJA": "Cerveja", "NAB": "NAB", "MKTPLACE": "Marketplace"}.get(str(t).upper().strip(),
                                                                                      "Sem tipo"))
    df["embalagem"] = [ps.categoria_detalhada(d, c) for d, c in zip(df["descricao"], df["categoria"])]
    df["marca"] = df["descricao"].map(ps.marca)
    nomes = nomes_depositos()
    df["deposito_nome"] = [rotulo_deposito(a, d, nomes) for a, d in zip(df["armazem"], df["deposito"])]
    return df


def comparativo(operacao_id: int, mes: str, so_cmv: bool = False) -> tuple[pd.DataFrame, dict]:
    """Por produto (somando depósitos): inicial × final em quantidade, R$ e HL."""
    ini, o_ini = saldo(operacao_id, mes, "inicial", so_cmv)
    fim, o_fim = saldo(operacao_id, mes, "final", so_cmv)
    chaves = ["produto"]
    agg = {"qtd_venda": "sum", "valor": "sum", "hl": "sum"}
    a = ini.groupby(chaves).agg(agg) if not ini.empty else pd.DataFrame(columns=list(agg))
    b = fim.groupby(chaves).agg(agg) if not fim.empty else pd.DataFrame(columns=list(agg))
    out = a.add_suffix("_ini").join(b.add_suffix("_fim"), how="outer").fillna(0.0).reset_index()
    info = enriquecer(pd.concat([fim, ini]).drop_duplicates("produto")) if not (ini.empty and fim.empty) else None
    if info is not None:
        out = out.merge(info[["produto", "descricao", "unidade", "tipo_prod", "embalagem", "marca"]], on="produto",
                        how="left")
    out["var_valor"] = out["valor_fim"] - out["valor_ini"]
    out["var_qtd"] = out["qtd_venda_fim"] - out["qtd_venda_ini"]
    out["var_hl"] = out["hl_fim"] - out["hl_ini"]
    return out, {"inicial": o_ini, "final": o_fim}


def cmv_periodo(operacao_id: int, meses_: list[str]) -> dict:
    """CMV = estoque inicial do 1º mês + compras do período − estoque final do último mês (R$ e HL), com os
    depósitos marcados para o CMV. É o mesmo número no 📊 Resumo & Lucro Bruto e no 📑 DRE."""
    from services import faturamento_service as fs

    ms = sorted(meses_)
    ini, o_ini = saldo(operacao_id, ms[0], "inicial", True)
    fim, o_fim = saldo(operacao_id, ms[-1], "final", True)
    de, ate = fs.periodo_mes(ms[0])[0], fs.periodo_mes(ms[-1])[1]
    dc = fs.dia_df(operacao_id, "compra", de, ate, fs.STATUS_PADRAO["compra"])
    comp = fs.combinar(dc, fs.operacoes_do_setor("compra"), fs.operacoes_do_setor("hl_compra"))
    ok = not ini.empty and not fim.empty
    ei, ef = float(ini["valor"].sum()), float(fim["valor"].sum())
    ei_hl, ef_hl = float(ini["hl"].sum()), float(fim["hl"].sum())
    return {"ok": ok, "origem_ini": o_ini, "origem_fim": o_fim, "ei": ei, "ef": ef, "ei_hl": ei_hl, "ef_hl": ef_hl,
            "compras": comp["valor"], "compras_hl": comp["hl"],
            "cmv": ei + comp["valor"] - ef if ok else None, "cmv_hl": ei_hl + comp["hl"] - ef_hl if ok else None}


def cmv_real(operacao_id: int, mes: str) -> dict:
    return cmv_periodo(operacao_id, [mes])


# --- DRE ---------------------------------------------------------------------------------------------
def obz(operacao_id: int, mes: str) -> pd.DataFrame | None:
    """Despesas do mês por departamento do OBZ (16.03.01 / Base OBZ); sem ele, o OBZ manual antigo.
    None = nenhum dos dois tem o mês."""
    from services import obz_service

    novo = obz_service.despesas_dre(operacao_id, mes)
    if novo is not None:
        return novo
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT pacote, SUM(orcado) AS orcado, SUM(realizado) AS realizado FROM financeiro_obz "
                  f"WHERE {trecho} AND mes_ano = ? GROUP BY pacote ORDER BY pacote", (*p, mes))
    if df.empty:
        return None
    for c in ("orcado", "realizado"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


CAMPOS_MANUAIS = {"icms": "ICMS", "pis_cofins": "PIS/COFINS", "conta_corrente": "Conta corrente"}


def manual(operacao_id: int, meses_: list[str]) -> dict:
    """Valores digitados no DRE (somados nos meses e, na visão consolidada, nas revendas)."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    ph = ", ".join("?" * len(meses_))
    r = query_one(f"SELECT SUM(icms) AS icms, SUM(pis_cofins) AS pis_cofins, SUM(conta_corrente) AS conta_corrente, "
                  f"COUNT(*) AS n FROM dre_manual WHERE {trecho} AND mes IN ({ph})", (*p, *meses_))
    out = {k: float(r[k] or 0.0) if r else 0.0 for k in CAMPOS_MANUAIS}
    out["preenchido"] = bool(r and r["n"])
    return out


def salvar_manual(operacao_id: int, mes: str, valores: dict, usuario: str = "") -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para lançar os valores do DRE.")
    v = {k: float(valores.get(k) or 0.0) for k in CAMPOS_MANUAIS}
    execute("""INSERT INTO dre_manual (operacao_id, mes, conta_corrente, pis_cofins, icms, atualizado_por, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(operacao_id, mes) DO UPDATE SET conta_corrente = excluded.conta_corrente,
                 pis_cofins = excluded.pis_cofins, icms = excluded.icms, atualizado_por = excluded.atualizado_por,
                 atualizado_em = excluded.atualizado_em""",
            (operacao_id, mes, v["conta_corrente"], v["pis_cofins"], v["icms"], usuario,
             tempo.agora().strftime("%Y-%m-%d %H:%M")))


def dre_periodo(operacao_id: int, meses_: list[str]) -> dict:
    """DRE de um mês ou de vários (o total do ano). Receita = só as operações de R$ de venda (⚙️ Cadastros);
    CMV = cmv_periodo (o mesmo do Resumo & Lucro Bruto); despesas = OBZ por departamento."""
    from services import faturamento_service as fs

    ms = sorted(meses_)
    de, ate = fs.periodo_mes(ms[0])[0], fs.periodo_mes(ms[-1])[1]
    dv = fs.dia_df(operacao_id, "venda", de, ate, fs.STATUS_PADRAO["venda"])
    ops_venda = fs.operacoes_do_setor("fat_venda")
    v = fs.combinar(dv, ops_venda, fs.operacoes_do_setor("hl_venda"))
    b = fs.totais(fs.separar(dv, {"b": fs.operacoes_do_setor("fat_bonif")})["b"])
    c = cmv_periodo(operacao_id, ms)
    obs = [obz(operacao_id, m) for m in ms]
    tem = [o for o in obs if o is not None]
    ob = (pd.concat(tem).groupby("pacote", as_index=False)[["orcado", "realizado"]].sum()
          .sort_values("realizado", ascending=False).reset_index(drop=True)) if tem else \
        pd.DataFrame(columns=["pacote", "orcado", "realizado"])
    desp = float(ob["realizado"].sum()) if tem else None
    man = manual(operacao_id, ms)
    receita_bruta = v["valor"]  # total das notas (coluna Z) das operações de venda filtradas
    receita = receita_bruta - man["icms"] - man["pis_cofins"]
    lucro = receita - c["cmv"] if c["cmv"] is not None else None
    resultado = lucro - desp + man["conta_corrente"] if lucro is not None and desp is not None else None
    return {"mes": ms[-1], "meses": ms, "ops_venda": ops_venda, "receita_bruta": receita_bruta,
            "descontos": v["desconto"], "receita": receita, "hl": v["hl"], "bonif": b["valor"], "bonif_hl": b["hl"],
            **c, **man, "lucro_bruto": lucro, "despesas": desp, "obz_meses": len(tem), "obz": ob,
            "orcado": float(ob["orcado"].sum()) if tem else None, "resultado": resultado}


def dre_mes(operacao_id: int, mes: str) -> dict:
    return dre_periodo(operacao_id, [mes])


def ultimo_saldo(operacao_id: int) -> dict:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    out = {}
    for t in TIPOS_SALDO:
        r = query_one(f"SELECT MAX(dt) AS dt FROM bases_log WHERE base = ? AND {trecho}", (f"estoque_{t}", *p))
        out[t] = r["dt"] if r else None
    return out


def dias_mes(mes: str) -> int:
    a, m = map(int, mes.split("-"))
    return calendar.monthrange(a, m)[1]


def mes_atual() -> str:
    return tempo.hoje().strftime("%Y-%m")


def hoje() -> dt.date:
    return tempo.hoje()
