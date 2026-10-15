"""Remuneração Ambev — quanto a Ambev paga à revenda pela logística.

• Tabela Ambev (um arquivo por unidade fornecedora/fábrica): coluna N = Frete Puxada (R$/caixa) e coluna P = Carreto
  (R$/caixa), por produto e vigência (início/fim; fim em branco = vigente).
• Carreto = caixas entregues (03.02.37 vendas, data de emissão) × carreto vigente no dia.
• Frete  = caixas compradas de cada fábrica (03.02.37 compra, coluna M = fábrica, data da operação) × frete da fábrica.
• Comparação com o OBZ: remuneração × gasto real dos departamentos ligados a cada uma (entrega / puxada).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df
from repositories import operacoes_repo
from services.erros import RegraNegocioError

TIPOS = {"carreto": "🚚 Carreto (entrega)", "frete": "🏭 Frete (puxada)"}
_COL_FRETE, _COL_CARRETO = 13, 15  # N e P (A = 0)


# --- utilitários ------------------------------------------------------------------------------------------------------
def _norm(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper().strip()


def _cod(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0") or "0"


def _num(v) -> float | None:
    t = str(v or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _data(v) -> str | None:
    t = str(v or "").strip()[:10]
    d = pd.to_datetime(t, format="%d/%m/%Y", errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def _texto(conteudo: bytes, nome: str) -> str:
    import zipfile

    if str(nome).lower().endswith(".zip") or conteudo[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(conteudo))
        except zipfile.BadZipFile as e:
            raise RegraNegocioError("O .zip está corrompido — compacte de novo e suba outra vez.") from e
        csvs = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
        if not csvs:
            raise RegraNegocioError("O .zip não tem nenhum arquivo .csv dentro.")
        conteudo = z.read(csvs[0])
    for enc in ("utf-8-sig", "latin1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin1", errors="ignore")


# --- leitura do arquivo da Ambev ---------------------------------------------------------------------------------------
def ler_tabela(conteudo: bytes, nome: str) -> dict:
    """Lê o relatório de preços/remuneração da Ambev de UMA unidade fornecedora.
    Devolve {unidade_cod, unidade_nome, revenda, gerado, df[produto, descricao, ini, fim, carreto, frete]}."""
    txt = _texto(conteudo, nome)
    linhas = list(csv.reader(io.StringIO(txt), delimiter=";"))
    unidade_cod = unidade_nome = revenda = gerado = None
    for ln in linhas[:12]:
        cel = ";".join(ln)
        n = _norm(cel)
        if n.startswith("UNIDADE FORNECEDORA"):
            m = re.search(r":\s*(\d+)\s*-\s*(.+)", cel)
            if m:
                unidade_cod, unidade_nome = _cod(m.group(1)), m.group(2).strip(" ;")
        elif n.startswith("REVENDA"):
            revenda = cel.split(":", 1)[-1].strip(" ;")
        elif n.startswith("DATA DE GERA"):
            m = re.search(r"(\d{2}/\d{2}/\d{4})", cel)
            gerado = _data(m.group(1)) if m else None
    if not unidade_cod:
        # sem cabeçalho: tenta o nome do arquivo ("185 - F. Rio Janeiro.csv")
        m = re.search(r"(\d+)\s*-\s*([^.]+(?:\.[^.]+)*)\.\w+$", str(nome))
        if m:
            unidade_cod, unidade_nome = _cod(m.group(1)), m.group(2).strip()
    if not unidade_cod:
        raise RegraNegocioError("Não achei a 'Unidade Fornecedora' no arquivo — suba o relatório da Ambev do jeito "
                                "que ele sai (com o cabeçalho).")
    reg = []
    for ln in linhas:
        if len(ln) <= _COL_CARRETO or not re.fullmatch(r"\s*\d+\s*", ln[0] or ""):
            continue
        ini = _data(ln[4])
        if not ini:
            continue
        reg.append({"produto": _cod(ln[0]), "descricao": re.sub(r"\s+", " ", ln[1]).strip(), "ini": ini,
                    "fim": _data(ln[5]), "carreto": _num(ln[_COL_CARRETO]), "frete": _num(ln[_COL_FRETE])})
    if not reg:
        raise RegraNegocioError("Nenhum produto com vigência encontrado. Confira se é o relatório de remuneração da "
                                "Ambev (coluna N = Frete Puxada, coluna P = Carreto).")
    df = pd.DataFrame(reg)
    # Cheia × Pratic trazem o mesmo frete/carreto: fica uma linha por produto × vigência
    df = (df.groupby(["produto", "ini"], as_index=False, dropna=False)
            .agg(descricao=("descricao", "first"), fim=("fim", "first"), carreto=("carreto", "mean"),
                 frete=("frete", "mean")))
    return {"unidade_cod": unidade_cod, "unidade_nome": unidade_nome or f"Unidade {unidade_cod}",
            "revenda": revenda, "gerado": gerado, "df": df.sort_values(["produto", "ini"]).reset_index(drop=True)}


def importar(conteudo: bytes, nome: str, operacao_id: int, usuario: str = "") -> dict:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir a tabela da Ambev.")
    t = ler_tabela(conteudo, nome)
    df = t["df"]
    agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    de, ate = df["ini"].min(), df["ini"].max()
    with get_conn() as conn:
        # o arquivo substitui as vigências que começam no período dele (para esta unidade)
        conn.execute("DELETE FROM remun_tabela WHERE operacao_id = ? AND unidade_cod = ? AND ini BETWEEN ? AND ?",
                     (operacao_id, t["unidade_cod"], de, ate))
        conn.executemany(
            "INSERT INTO remun_tabela (operacao_id, unidade_cod, unidade_nome, produto, descricao, ini, fim, carreto, "
            "frete, arquivo, importado_por, importado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(operacao_id, t["unidade_cod"], t["unidade_nome"], r.produto, r.descricao, r.ini,
              None if pd.isna(r.fim) else r.fim, None if pd.isna(r.carreto) else float(r.carreto),
              None if pd.isna(r.frete) else float(r.frete), str(nome)[:200], usuario, agora)
             for r in df.itertuples(index=False)])
    # sugere a fábrica do 03.02.37 se ainda não tem de-para
    if not fornecedor_de(operacao_id, t["unidade_cod"]):
        sug = sugerir_fornecedor(operacao_id, t["unidade_nome"])
        if sug:
            salvar_mapa(operacao_id, t["unidade_cod"], sug)
    return {"unidade": f"{t['unidade_cod']} · {t['unidade_nome']}", "produtos": int(df["produto"].nunique()),
            "vigencias": len(df), "de": de, "ate": ate, "fornecedor": fornecedor_de(operacao_id, t["unidade_cod"])}


def unidades(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"""SELECT operacao_id, unidade_cod, MAX(unidade_nome) AS unidade_nome, COUNT(DISTINCT produto)
                        AS produtos, MIN(ini) AS de, MAX(ini) AS ate, MAX(importado_em) AS importado_em,
                        MAX(importado_por) AS importado_por FROM remun_tabela WHERE {trecho}
                        GROUP BY operacao_id, unidade_cod ORDER BY unidade_cod""", p)


def tabela(operacao_id: int, unidade_cod: str | None = None) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    extra, pe = (" AND unidade_cod = ?", [unidade_cod]) if unidade_cod else ("", [])
    return query_df(f"SELECT operacao_id, unidade_cod, unidade_nome, produto, descricao, ini, fim, carreto, frete "
                    f"FROM remun_tabela WHERE {trecho}{extra} ORDER BY unidade_cod, produto, ini", (*p, *pe))


def excluir_unidade(operacao_id: int, unidade_cod: str) -> None:
    execute("DELETE FROM remun_tabela WHERE operacao_id = ? AND unidade_cod = ?", (operacao_id, unidade_cod))
    execute("DELETE FROM remun_fabrica_map WHERE operacao_id = ? AND unidade_cod = ?", (operacao_id, unidade_cod))


# --- de-para unidade Ambev × fábrica do 03.02.37 (coluna M) -----------------------------------------------------------
def mapas(operacao_id: int) -> dict[tuple[int, str], str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    m = query_df(f"SELECT operacao_id, unidade_cod, fornecedor FROM remun_fabrica_map WHERE {trecho}", p)
    return {(int(o), str(u)): str(f) for o, u, f in zip(m["operacao_id"], m["unidade_cod"], m["fornecedor"]) if f}


def fornecedor_de(operacao_id: int, unidade_cod: str) -> str | None:
    return mapas(operacao_id).get((int(operacao_id), str(unidade_cod)))


def salvar_mapa(operacao_id: int, unidade_cod: str, fornecedor: str | None) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM remun_fabrica_map WHERE operacao_id = ? AND unidade_cod = ?",
                     (operacao_id, str(unidade_cod)))
        if fornecedor:
            conn.execute("INSERT INTO remun_fabrica_map (operacao_id, unidade_cod, fornecedor) VALUES (?, ?, ?)",
                         (operacao_id, str(unidade_cod), _cod(fornecedor)))


def fornecedores(operacao_id: int) -> pd.DataFrame:
    """Fábricas (coluna M do 03.02.37 compra) nas operações de compra, com nome e caixas compradas."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    ops = _ops(operacao_id, "frete")
    if not ops:
        return pd.DataFrame(columns=["fornecedor", "nome", "qtde"])
    q = query_df(f"SELECT cliente AS fornecedor, SUM(qtde) AS qtde FROM notas_prod_dia WHERE {trecho} AND "
                 f"origem = 'compra' AND operacao_cod IN ({', '.join('?' * len(ops))}) GROUP BY cliente",
                 (*p, *ops))
    n = query_df(f"SELECT cliente AS fornecedor, MAX(nome) AS nome FROM notas_cliente_mes WHERE {trecho} AND "
                 f"origem = 'compra' AND operacao_cod IN ({', '.join('?' * len(ops))}) GROUP BY cliente", (*p, *ops))
    if not n.empty:
        n["fornecedor"] = n["fornecedor"].map(_cod)
        n = n.groupby("fornecedor", as_index=False)["nome"].first()
    if q.empty and n.empty:
        return pd.DataFrame(columns=["fornecedor", "nome", "qtde"])
    out = (q.merge(n, on="fornecedor", how="outer") if not q.empty else n.assign(qtde=0.0))
    out["qtde"] = pd.to_numeric(out.get("qtde"), errors="coerce").fillna(0.0)
    out["nome"] = out["nome"].fillna("").astype(str).str.strip()
    return out.sort_values("qtde", ascending=False).reset_index(drop=True)


def sugerir_fornecedor(operacao_id: int, unidade_nome: str) -> str | None:
    """Acha a fábrica do 03.02.37 pelo nome da unidade Ambev (ex.: 'F. Rio Janeiro' × 'RIO DE JANEIRO')."""
    f = fornecedores(operacao_id)
    if f.empty:
        return None
    ign = {"F", "FAB", "FABRICA", "CERV", "CERVEJARIA", "AMBEV", "SA", "S", "A", "DE", "DA", "DO", "LTDA", "IND",
           "COM", "FILIAL", "E"}
    alvo = {w for w in re.split(r"[^A-Z0-9]+", _norm(unidade_nome)) if len(w) > 1 and w not in ign}
    if not alvo:
        return None
    melhor, nota = None, 0.0
    for c, n in zip(f["fornecedor"], f["nome"]):
        ws = {w for w in re.split(r"[^A-Z0-9]+", _norm(n)) if len(w) > 1 and w not in ign}
        if not ws:
            continue
        s = len(alvo & ws) / len(alvo)
        if s > nota:
            melhor, nota = c, s
    return melhor if nota >= 0.5 else None


# --- configuração (operações e departamentos do OBZ) -------------------------------------------------------------------
def _cfg(operacao_id: int) -> dict:
    ids = operacoes_repo.ids_efetivos(operacao_id)
    r = query_df(f"SELECT operacao_id, chave, valor FROM remun_config WHERE operacao_id IN "
                 f"({', '.join('?' * len(ids))})", ids)
    out: dict = {}
    for _, x in r.iterrows():
        out.setdefault(x["chave"], [])
        out[x["chave"]] += [v for v in str(x["valor"] or "").split(",") if v and v not in out[x["chave"]]]
    return out


def _ops(operacao_id: int, tipo: str) -> list[str]:
    from services import faturamento_service as fs

    c = _cfg(operacao_id).get(f"ops_{tipo}")
    if c:
        return c
    return fs.operacoes_do_setor("hl_venda" if tipo == "carreto" else "hl_compra")


def _deptos_padrao(tipo: str) -> list[str]:
    from services import obz_service as obz

    d = obz.departamentos()
    if d.empty:
        return []
    chaves = ("ENTREG", "DISTRIB") if tipo == "carreto" else ("PUXAD", "FRETE", "TRANSF")
    return [c for c, n in zip(d["codigo"], d["nome"]) if any(k in _norm(n) for k in chaves)]


def config(operacao_id: int) -> dict:
    c = _cfg(operacao_id)
    return {"ops_carreto": _ops(operacao_id, "carreto"), "ops_frete": _ops(operacao_id, "frete"),
            "deptos_carreto": c.get("deptos_carreto") or _deptos_padrao("carreto"),
            "deptos_frete": c.get("deptos_frete") or _deptos_padrao("frete")}


def salvar_config(operacao_id: int, dados: dict) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para configurar.")
    with get_conn() as conn:
        for k, v in dados.items():
            conn.execute("DELETE FROM remun_config WHERE operacao_id = ? AND chave = ?", (operacao_id, k))
            conn.execute("INSERT INTO remun_config (operacao_id, chave, valor) VALUES (?, ?, ?)",
                         (operacao_id, k, ",".join(str(x) for x in v)))


# --- cálculo ------------------------------------------------------------------------------------------------------------
def _qtd_dia(operacao_id: int, origem: str, ops: list[str], de: str, ate: str) -> pd.DataFrame:
    from services import faturamento_service as fs

    if not ops:
        return pd.DataFrame(columns=["operacao_id", "data", "cliente", "produto", "descricao", "qtde", "hl"])
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    st_ = fs.STATUS_PADRAO[origem]
    df = query_df(f"""SELECT operacao_id, data, cliente, produto, MAX(descricao) AS descricao, SUM(qtde) AS qtde,
                             SUM(hl) AS hl FROM notas_prod_dia WHERE {trecho} AND origem = ? AND data BETWEEN ? AND ?
                             AND operacao_cod IN ({', '.join('?' * len(ops))})
                             AND status IN ({', '.join('?' * len(st_))})
                      GROUP BY operacao_id, data, cliente, produto""", (*p, origem, de, ate, *ops, *st_))
    for c in ("qtde", "hl"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


def sem_base_dia(operacao_id: int, origem: str, de: str, ate: str) -> list[str]:
    """Meses que têm 03.02.37 carregado mas sem o detalhe por dia/produto (subidos antes desta tela)."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    a = query_df(f"SELECT DISTINCT substr(data, 1, 7) AS m FROM notas_dia WHERE {trecho} AND origem = ? AND data "
                 f"BETWEEN ? AND ?", (*p, origem, de, ate))
    b = query_df(f"SELECT DISTINCT substr(data, 1, 7) AS m FROM notas_prod_dia WHERE {trecho} AND origem = ? AND "
                 f"data BETWEEN ? AND ?", (*p, origem, de, ate))
    return sorted(set(a["m"]) - set(b["m"]))


def _tarifa(q: pd.DataFrame, tab: pd.DataFrame, campo: str) -> pd.DataFrame:
    """Põe em cada linha (data × produto) a tarifa vigente no dia: maior início ≤ data; se o fim já passou, usa a
    última conhecida e marca fora_vig."""
    if q.empty or tab.empty:
        return q.assign(tarifa=float("nan"), fora_vig=False)
    t = tab[["produto", "ini", "fim", campo]].dropna(subset=[campo]).copy()
    t["ini_d"] = pd.to_datetime(t["ini"])
    t = t.sort_values("ini_d")
    x = q.copy()
    x["_ord"] = range(len(x))
    x["data_d"] = pd.to_datetime(x["data"])
    x = x.sort_values("data_d")
    m = pd.merge_asof(x, t[["produto", "ini_d", "fim", campo]], left_on="data_d", right_on="ini_d", by="produto",
                      direction="backward")
    # produto sem vigência anterior: usa a primeira vigência da tabela
    falta = m[campo].isna() & m["produto"].isin(set(t["produto"]))
    if falta.any():
        prim = t.groupby("produto")[campo].first()
        m.loc[falta, campo] = m.loc[falta, "produto"].map(prim)
        m.loc[falta, "fim"] = None
    fim = pd.to_datetime(m["fim"], errors="coerce")
    m["fora_vig"] = m[campo].notna() & fim.notna() & (fim < m["data_d"])
    m = m.rename(columns={campo: "tarifa"}).sort_values("_ord")
    return m.drop(columns=["_ord", "data_d", "ini_d", "fim"]).reset_index(drop=True)


def carreto(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    """Linhas (operacao_id, data, produto, descricao, qtde, hl, tarifa, valor, fora_vig, unidades).
    Carreto do produto: média das unidades que têm o produto, ponderada pelo que se comprou de cada fábrica no mês
    (sem compra: média simples)."""
    partes = []
    for op in operacoes_repo.ids_efetivos(operacao_id):
        q = _qtd_dia(op, "venda", _ops(op, "carreto"), de, ate)
        if q.empty:
            continue
        q = q.groupby(["operacao_id", "data", "produto"], as_index=False).agg(
            descricao=("descricao", "first"), qtde=("qtde", "sum"), hl=("hl", "sum"))
        tab = tabela(op)
        if tab.empty:
            partes.append(q.assign(tarifa=float("nan"), valor=0.0, fora_vig=False, unidades=""))
            continue
        mp = mapas(op)
        comp = _qtd_dia(op, "compra", _ops(op, "frete"), de, ate)
        comp["mes"] = comp["data"].str[:7]
        pesos = comp.groupby(["mes", "cliente", "produto"])["qtde"].sum()
        tarifas = []
        for u, tu in tab.groupby("unidade_cod"):
            r = _tarifa(q[["data", "produto"]], tu, "carreto")
            forn = mp.get((op, str(u)))
            mes = r["data"].str[:7]
            r["peso"] = [float(pesos.get((m_, forn, p_), 0.0)) if forn else 0.0 for m_, p_ in zip(mes, r["produto"])]
            r["unidade"] = str(u)
            tarifas.append(r.dropna(subset=["tarifa"]))
        tf = pd.concat(tarifas, ignore_index=True) if tarifas else pd.DataFrame()
        if tf.empty:
            partes.append(q.assign(tarifa=float("nan"), valor=0.0, fora_vig=False, unidades=""))
            continue
        tf["tp"] = tf["tarifa"] * tf["peso"]
        g = tf.groupby(["data", "produto"]).agg(media=("tarifa", "mean"), tp=("tp", "sum"), peso=("peso", "sum"),
                                                fora_vig=("fora_vig", "all"),
                                                unidades=("unidade", lambda s: ", ".join(sorted(set(s)))))
        g["tarifa"] = (g["tp"] / g["peso"]).where(g["peso"] > 0, g["media"])
        q = q.merge(g[["tarifa", "fora_vig", "unidades"]].reset_index(), on=["data", "produto"], how="left")
        q["fora_vig"] = q["fora_vig"].fillna(False).astype(bool)
        q["unidades"] = q["unidades"].fillna("")
        q["valor"] = (q["qtde"] * q["tarifa"]).fillna(0.0)
        partes.append(q)
    if not partes:
        return pd.DataFrame(columns=["operacao_id", "data", "produto", "descricao", "qtde", "hl", "tarifa", "valor",
                                     "fora_vig", "unidades"])
    return pd.concat(partes, ignore_index=True)


def frete(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    """Linhas (operacao_id, data, fornecedor, unidade_cod, unidade_nome, produto, descricao, qtde, hl, tarifa, valor,
    fora_vig). Fábrica sem tabela da Ambev (ou sem de-para) fica com unidade vazia e valor 0."""
    partes = []
    for op in operacoes_repo.ids_efetivos(operacao_id):
        q = _qtd_dia(op, "compra", _ops(op, "frete"), de, ate)
        if q.empty:
            continue
        q = q.rename(columns={"cliente": "fornecedor"})
        tab = tabela(op)
        mp = {f: u for (o, u), f in mapas(op).items() if o == op}
        nomes_u = dict(zip(tab["unidade_cod"], tab["unidade_nome"])) if not tab.empty else {}
        q["unidade_cod"] = q["fornecedor"].map(mp).fillna("")
        q["unidade_nome"] = q["unidade_cod"].map(nomes_u).fillna("")
        saida = []
        for u, qu in q.groupby("unidade_cod"):
            if u and not tab.empty:
                saida.append(_tarifa(qu.reset_index(drop=True), tab[tab["unidade_cod"] == u], "frete"))
            else:
                saida.append(qu.assign(tarifa=float("nan"), fora_vig=False))
        q = pd.concat(saida, ignore_index=True)
        q["valor"] = (q["qtde"] * q["tarifa"]).fillna(0.0)
        partes.append(q)
    if not partes:
        return pd.DataFrame(columns=["operacao_id", "data", "fornecedor", "unidade_cod", "unidade_nome", "produto",
                                     "descricao", "qtde", "hl", "tarifa", "valor", "fora_vig"])
    return pd.concat(partes, ignore_index=True)


def nomes_fornecedores(operacao_id: int) -> dict[str, str]:
    f = fornecedores(operacao_id)
    return {c: (n or "") for c, n in zip(f["fornecedor"], f["nome"])}


def meses_disponiveis(operacao_id: int) -> list[str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_df(f"SELECT DISTINCT substr(data, 1, 7) AS m FROM notas_dia WHERE {trecho} ORDER BY m DESC", p)
    return r["m"].tolist()


# --- comparação com o OBZ ----------------------------------------------------------------------------------------------
def comparar_obz(operacao_id: int, meses: list[str]) -> dict:
    """Remuneração (carreto/frete) × gasto real e plan do OBZ por departamento, mês a mês."""
    from services import obz_service as obz

    if not meses:
        return {"mensal": pd.DataFrame(), "deptos": pd.DataFrame()}
    de, ate = min(meses), max(meses)
    ini, fim = f"{de}-01", (pd.Period(ate).end_time.strftime("%Y-%m-%d"))
    c, f = carreto(operacao_id, ini, fim), frete(operacao_id, ini, fim)
    cfg = config(operacao_id)
    g = pd.concat([obz.gastos_ano(operacao_id, a) for a in sorted({m[:4] for m in meses})], ignore_index=True)
    if not g.empty:
        g = g[g["mes"].isin(meses)]
    nomes = obz.nomes_deptos()
    linhas = []
    for m in sorted(meses):
        cm = c[c["data"].str[:7] == m] if not c.empty else c
        fm = f[f["data"].str[:7] == m] if not f.empty else f
        gm = g[g["mes"] == m] if not g.empty else g
        for tipo, base, deps in (("carreto", cm, cfg["deptos_carreto"]), ("frete", fm, cfg["deptos_frete"])):
            gd = gm[gm["depto"].isin(deps)] if not gm.empty else gm
            ok = base[base["tarifa"].notna()] if len(base) else base
            linhas.append({"mes": m, "tipo": tipo, "remuneracao": float(base["valor"].sum()) if len(base) else 0.0,
                           "caixas": float(ok["qtde"].sum()) if len(ok) else 0.0,
                           "hl": float(ok["hl"].sum()) if len(ok) else 0.0,
                           "real": float(gd["real"].sum()) if len(gd) else 0.0,
                           "plan": float(gd["plan"].sum()) if len(gd) else 0.0})
    mensal = pd.DataFrame(linhas)
    mensal["resultado"] = mensal["remuneracao"] - mensal["real"]
    mensal["cobertura"] = (mensal["remuneracao"] / mensal["real"] * 100).where(mensal["real"] > 0)
    # por departamento (todos), com a remuneração ligada nos departamentos configurados
    if g.empty:
        dep = pd.DataFrame(columns=["depto", "nome", "ligado", "real", "plan", "remuneracao"])
    else:
        dep = g.groupby("depto", as_index=False)[["real", "plan"]].sum()
        dep["nome"] = dep["depto"].map(nomes).fillna("")
        rot = {d: "carreto" for d in cfg["deptos_carreto"]}
        rot.update({d: ("frete" if d not in rot else "carreto + frete") for d in cfg["deptos_frete"]})
        dep["ligado"] = dep["depto"].map(rot).fillna("")
        rem = {"carreto": float(c["valor"].sum()) if len(c) else 0.0, "frete": float(f["valor"].sum()) if len(f) else 0.0}
        # a remuneração de cada tipo é dividida entre os departamentos ligados a ele, na proporção do gasto real
        dep["remuneracao"] = 0.0
        for tipo in ("carreto", "frete"):
            msk = dep["ligado"].str.contains(tipo)
            tot = dep.loc[msk, "real"].sum()
            if msk.any():
                dep.loc[msk, "remuneracao"] += (dep.loc[msk, "real"] / tot * rem[tipo]) if tot else rem[tipo] / msk.sum()
        dep = dep.sort_values("real", ascending=False).reset_index(drop=True)
    return {"mensal": mensal, "deptos": dep, "carreto": c, "frete": f, "cfg": cfg}
