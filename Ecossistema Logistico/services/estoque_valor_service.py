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
def ler_020502(conteudo, nome: str) -> pd.DataFrame:
    """Lê o 02.05.02 (armazém, depósito, produto, quantidades e valores). qtd_venda = caixas (unidades ÷ fator)."""
    from services.produtividade_entrega_service import _abrir, _ler_csv, _n

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
    return df


def importar(conteudo: bytes, nome: str, operacao_id: int, mes: str, tipo_saldo: str, usuario: str = "") -> dict:
    from services.produtividade_entrega_service import _log, _py

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir o 02.05.02.")
    if tipo_saldo not in TIPOS_SALDO:
        raise RegraNegocioError("Escolha se é o saldo inicial ou o saldo final.")
    df = ler_020502(conteudo, nome)
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


def _tipos_produto() -> pd.DataFrame:
    pr = query_df("SELECT cod, tipo AS tipo_prod, categoria FROM produtos")
    pr["produto"] = pr["cod"].astype(str).str.replace(r"\.0$", "", regex=True)
    return pr.drop(columns="cod").drop_duplicates("produto")


def _bruto(operacao_id: int, mes: str, tipo_saldo: str) -> pd.DataFrame:
    # o JOIN com CAST(cod AS TEXT) não usa índice e ficava lento (segundos) — junta aqui no pandas
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT * FROM estoque_saldos WHERE {trecho} AND mes = ? AND tipo_saldo = ?", (*p, mes, tipo_saldo))
    df = df.merge(_tipos_produto(), on="produto", how="left") if not df.empty else \
        df.assign(tipo_prod=None, categoria=None)
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
    receita = receita_bruta - abs(man["icms"]) - abs(man["pis_cofins"])  # impostos sempre abatem, com ou sem sinal
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


# --- DRE editado ------------------------------------------------------------------------------------------------
# Linhas que podem ser editadas (os totais são recalculados): chave → rótulo
EDITAVEIS_FIXAS = {"receita_bruta": "Receita bruta de vendas", "icms": "ICMS", "pis_cofins": "PIS/COFINS",
                   "ei": "Estoque inicial", "compras": "Compras", "ef": "Estoque final",
                   "conta_corrente": "Conta corrente"}


def pode_editar_dre(usuario: dict) -> bool:
    from core.auth import e_master
    from services import obz_service

    return e_master(usuario) or usuario.get("id") in obz_service.usuarios_papel("dre_editar")


def valores_dre(r: dict) -> dict:
    """Valores-base (editáveis) de um DRE calculado."""
    v = {"receita_bruta": r["receita_bruta"], "icms": abs(r["icms"]), "pis_cofins": abs(r["pis_cofins"]),
         "ei": r["ei"] if r["ok"] else None, "compras": r["compras"], "ef": r["ef"] if r["ok"] else None,
         "conta_corrente": r["conta_corrente"]}
    if r["despesas"] is not None and not r["obz"].empty:
        for p, x in zip(r["obz"]["pacote"], r["obz"]["realizado"]):
            v[f"dep:{p}"] = float(x)
    return v


def rotulo_chave(chave: str) -> str:
    return chave[4:] if chave.startswith("dep:") else EDITAVEIS_FIXAS.get(chave, chave)


def edicoes(operacao_id: int, mes: str) -> pd.DataFrame:
    return query_df("SELECT chave, valor, editado_por, editado_em FROM dre_editado WHERE operacao_id = ? AND mes = ?",
                    (operacao_id, mes))


def _aplicar(r: dict, v: dict) -> dict:
    """Monta o DRE (mesmas chaves do dre_periodo) a partir dos valores-base, recalculando os totais."""
    r = dict(r)
    r["receita_bruta"] = v.get("receita_bruta") or 0.0
    r["icms"], r["pis_cofins"] = v.get("icms") or 0.0, v.get("pis_cofins") or 0.0
    r["conta_corrente"] = v.get("conta_corrente") or 0.0
    r["receita"] = r["receita_bruta"] - abs(r["icms"]) - abs(r["pis_cofins"])
    r["compras"] = v.get("compras") or 0.0
    ok = v.get("ei") is not None and v.get("ef") is not None
    r["ok"], r["ei"], r["ef"] = ok, v.get("ei") or 0.0, v.get("ef") or 0.0
    r["cmv"] = r["ei"] + r["compras"] - r["ef"] if ok else None
    deps = {k[4:]: x for k, x in v.items() if k.startswith("dep:")}
    orc = dict(zip(r["obz"]["pacote"], r["obz"]["orcado"])) if not r["obz"].empty else {}
    if deps:
        ob = pd.DataFrame({"pacote": list(deps), "realizado": [float(x or 0) for x in deps.values()],
                           "orcado": [float(orc.get(p, 0.0)) for p in deps]})
        r["obz"] = ob.sort_values("realizado", ascending=False).reset_index(drop=True)
        r["despesas"] = float(r["obz"]["realizado"].sum())
    r["lucro_bruto"] = r["receita"] - r["cmv"] if r["cmv"] is not None else None
    r["resultado"] = (r["lucro_bruto"] - r["despesas"] + r["conta_corrente"]
                      if r["lucro_bruto"] is not None and r["despesas"] is not None else None)
    return r


def dre_editado_mes(operacao_id: int, mes: str) -> tuple[dict, dict, pd.DataFrame]:
    """(DRE gerado, DRE editado, edições). Na visão consolidada soma o efeito das edições de cada revenda."""
    gerado = dre_mes(operacao_id, mes)
    base = valores_dre(gerado)
    if operacoes_repo.e_consolidada(operacao_id):
        todas = []
        for oid in operacoes_repo.ids_efetivos(operacao_id):
            e = edicoes(oid, mes)
            if e.empty:
                continue
            g_op = valores_dre(dre_mes(oid, mes))
            for k, x in zip(e["chave"], e["valor"]):
                base[k] = (base.get(k) or 0.0) + float(x or 0) - float(g_op.get(k) or 0.0)
            todas.append(e)
        ed = pd.concat(todas, ignore_index=True) if todas else edicoes(operacao_id, mes)
    else:
        ed = edicoes(operacao_id, mes)
        for k, x in zip(ed["chave"], ed["valor"]):
            base[k] = float(x) if x is not None else None
    return gerado, _aplicar(gerado, base), ed


def dre_editado_periodo(operacao_id: int, meses_: list[str]) -> dict:
    """Total de vários meses do DRE editado: soma os meses; estoque inicial do 1º e final do último."""
    rs = [dre_editado_mes(operacao_id, m)[1] for m in sorted(meses_)]
    if len(rs) == 1:
        return rs[0]
    tot = dict(rs[-1])
    v = {k: sum((r[k] or 0.0) for r in rs) for k in ("receita_bruta", "icms", "pis_cofins", "compras",
                                                      "conta_corrente")}
    v["ei"] = rs[0]["ei"] if rs[0]["ok"] else None
    v["ef"] = rs[-1]["ef"] if rs[-1]["ok"] else None
    deps: dict = {}
    for r in rs:
        if not r["obz"].empty:
            for p, x in zip(r["obz"]["pacote"], r["obz"]["realizado"]):
                deps[p] = deps.get(p, 0.0) + float(x)
    v.update({f"dep:{p}": x for p, x in deps.items()})
    ob = [r["obz"] for r in rs if not r["obz"].empty]
    tot["obz"] = (pd.concat(ob).groupby("pacote", as_index=False)[["orcado", "realizado"]].sum()
                  if ob else pd.DataFrame(columns=["pacote", "orcado", "realizado"]))
    tot["despesas"] = sum(r["despesas"] for r in rs if r["despesas"] is not None) if any(
        r["despesas"] is not None for r in rs) else None
    tot["orcado"] = sum(r["orcado"] or 0 for r in rs) if tot["despesas"] is not None else None
    tot["hl"] = sum(r["hl"] for r in rs)
    tot["meses"] = sorted(meses_)
    return _aplicar(tot, v)


def salvar_edicao(operacao_id: int, mes: str, novos: dict, usuario: dict) -> int:
    """Grava os valores editados (só os que mudaram). Valor igual ao gerado volta a ser 'gerado'.
    Devolve quantas linhas mudaram."""
    if not pode_editar_dre(usuario):
        raise RegraNegocioError("Editar o DRE precisa ser liberado pelo Master (⚙️ Cadastros OBZ › Papéis).")
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para editar o DRE.")
    gerado = valores_dre(dre_mes(operacao_id, mes))
    atuais = {k: v for k, v in zip(*[edicoes(operacao_id, mes)[c] for c in ("chave", "valor")])}
    quem = usuario.get("nome") or usuario.get("login") or ""
    quando = tempo.agora().strftime("%Y-%m-%d %H:%M")
    mudou = 0
    with get_conn() as conn:
        for k, novo in novos.items():
            novo = None if novo is None or (isinstance(novo, float) and pd.isna(novo)) else round(float(novo), 2)
            antes = atuais.get(k, gerado.get(k))
            antes = None if antes is None else round(float(antes), 2)
            if novo == antes:
                continue
            ger = gerado.get(k)
            if novo is not None and ger is not None and abs(novo - float(ger)) < 0.005:
                conn.execute("DELETE FROM dre_editado WHERE operacao_id = ? AND mes = ? AND chave = ?",
                             (operacao_id, mes, k))
            else:
                conn.execute("""INSERT INTO dre_editado (operacao_id, mes, chave, valor, editado_por, editado_em)
                                VALUES (?, ?, ?, ?, ?, ?)
                                ON CONFLICT(operacao_id, mes, chave) DO UPDATE SET valor = excluded.valor,
                                  editado_por = excluded.editado_por, editado_em = excluded.editado_em""",
                             (operacao_id, mes, k, novo, quem, quando))
            conn.execute("""INSERT INTO dre_editado_log (operacao_id, mes, chave, rotulo, de, para, usuario, em)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (operacao_id, mes, k, rotulo_chave(k), antes, novo,
                                                                  quem, quando))
            mudou += 1
    return mudou


def voltar_ao_gerado(operacao_id: int, mes: str, usuario: dict) -> None:
    if not pode_editar_dre(usuario):
        raise RegraNegocioError("Editar o DRE precisa ser liberado pelo Master.")
    quem = usuario.get("nome") or usuario.get("login") or ""
    quando = tempo.agora().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        conn.execute("DELETE FROM dre_editado WHERE operacao_id = ? AND mes = ?", (operacao_id, mes))
        conn.execute("""INSERT INTO dre_editado_log (operacao_id, mes, chave, rotulo, de, para, usuario, em)
                        VALUES (?, ?, '*', 'Tudo voltou ao gerado', NULL, NULL, ?, ?)""",
                     (operacao_id, mes, quem, quando))


def log_edicoes(operacao_id: int, mes: str | None = None) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, params = f"SELECT * FROM dre_editado_log WHERE {trecho}", list(p)
    if mes:
        sql += " AND mes = ?"
        params.append(mes)
    return query_df(sql + " ORDER BY id DESC LIMIT 300", params)
