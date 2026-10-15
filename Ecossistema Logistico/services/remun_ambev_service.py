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


def importar(conteudo: bytes, nome: str, operacao_id: int, mes: str, usuario: str = "") -> dict:
    """Grava a tabela da Ambev de uma unidade como a tabela do MÊS escolhido (substitui a desse mês)."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir a tabela da Ambev.")
    if not re.fullmatch(r"\d{4}-\d{2}", str(mes or "")):
        raise RegraNegocioError("Escolha o mês da tabela.")
    t = ler_tabela(conteudo, nome)
    df = t["df"]
    agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("DELETE FROM remun_tabela WHERE operacao_id = ? AND unidade_cod = ? AND mes = ?",
                     (operacao_id, t["unidade_cod"], mes))
        conn.executemany(
            "INSERT INTO remun_tabela (operacao_id, unidade_cod, unidade_nome, mes, produto, descricao, ini, fim, "
            "carreto, frete, arquivo, importado_por, importado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(operacao_id, t["unidade_cod"], t["unidade_nome"], mes, r.produto, r.descricao, r.ini,
              None if pd.isna(r.fim) else r.fim, None if pd.isna(r.carreto) else float(r.carreto),
              None if pd.isna(r.frete) else float(r.frete), str(nome)[:200], usuario, agora)
             for r in df.itertuples(index=False)])
    # sugere a fábrica do 03.02.37 se ainda não tem de-para
    if not fornecedor_de(operacao_id, t["unidade_cod"]):
        sug = sugerir_fornecedor(operacao_id, t["unidade_nome"])
        if sug:
            salvar_mapa(operacao_id, t["unidade_cod"], sug)
    meses_arq = sorted(set(df["ini"].str[:7]))
    return {"unidade": f"{t['unidade_cod']} · {t['unidade_nome']}", "produtos": int(df["produto"].nunique()),
            "vigencias": len(df), "mes": mes, "de": df["ini"].min(), "ate": df["ini"].max(),
            "outro_mes": mes not in meses_arq, "fornecedor": fornecedor_de(operacao_id, t["unidade_cod"])}


def tabelas_mes(operacao_id: int) -> pd.DataFrame:
    """Uma linha por unidade × mês de tabela subida."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"""SELECT operacao_id, unidade_cod, mes, MAX(unidade_nome) AS unidade_nome,
                        COUNT(DISTINCT produto) AS produtos, MIN(ini) AS de, MAX(ini) AS ate,
                        MAX(importado_em) AS importado_em, MAX(importado_por) AS importado_por, MAX(arquivo) AS arquivo
                        FROM remun_tabela WHERE {trecho} GROUP BY operacao_id, unidade_cod, mes
                        ORDER BY unidade_cod, mes DESC""", p)


def unidades(operacao_id: int) -> pd.DataFrame:
    t = tabelas_mes(operacao_id)
    if t.empty:
        return pd.DataFrame(columns=["operacao_id", "unidade_cod", "unidade_nome", "meses", "produtos",
                                     "importado_em", "importado_por"])
    return (t.groupby(["operacao_id", "unidade_cod"], as_index=False)
             .agg(unidade_nome=("unidade_nome", "first"), meses=("mes", lambda s: sorted(set(s), reverse=True)),
                  produtos=("produtos", "max"), importado_em=("importado_em", "max"),
                  importado_por=("importado_por", "last")))


def tabela(operacao_id: int, unidade_cod: str | None = None, mes: str | None = None) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    extra, pe = "", []
    if unidade_cod:
        extra, pe = extra + " AND unidade_cod = ?", pe + [unidade_cod]
    if mes:
        extra, pe = extra + " AND mes = ?", pe + [mes]
    return query_df(f"SELECT operacao_id, unidade_cod, unidade_nome, mes, produto, descricao, ini, fim, carreto, frete, "
                    f"importado_em FROM remun_tabela WHERE {trecho}{extra} ORDER BY unidade_cod, mes, produto, ini", (*p, *pe))


def excluir_tabela(operacao_id: int, unidade_cod: str, mes: str) -> None:
    execute("DELETE FROM remun_tabela WHERE operacao_id = ? AND unidade_cod = ? AND mes = ?",
            (operacao_id, unidade_cod, mes))
    if query_df("SELECT 1 AS x FROM remun_tabela WHERE operacao_id = ? AND unidade_cod = ?",
                (operacao_id, unidade_cod)).empty:
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
    n = query_df(f"SELECT cliente AS fornecedor, MAX(nome) AS nome, SUM(hl) AS hl FROM notas_cliente_mes WHERE {trecho} AND "
                 f"origem = 'compra' AND operacao_cod IN ({', '.join('?' * len(ops))}) GROUP BY cliente", (*p, *ops))
    if not n.empty:
        n["fornecedor"] = n["fornecedor"].map(_cod)
        n["hl"] = pd.to_numeric(n["hl"], errors="coerce").fillna(0.0)
        n = n.groupby("fornecedor", as_index=False).agg(nome=("nome", "first"), hl=("hl", "sum"))
    if q.empty and n.empty:
        return pd.DataFrame(columns=["fornecedor", "nome", "qtde"])
    out = (q.merge(n, on="fornecedor", how="outer") if not q.empty else n.assign(qtde=0.0))
    out["qtde"] = pd.to_numeric(out.get("qtde"), errors="coerce").fillna(0.0)
    out["nome"] = out["nome"].fillna("").astype(str).str.strip()
    out["hl"] = pd.to_numeric(out.get("hl"), errors="coerce").fillna(0.0) if "hl" in out else 0.0
    return out.sort_values(["qtde", "hl"], ascending=False).reset_index(drop=True)


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


def meses_com_dia(operacao_id: int, origem: str, de: str, ate: str) -> set[str]:
    """Meses que têm o detalhe por dia/produto (03.02.37 subido depois da Remuneração Ambev)."""
    b = query_df("SELECT DISTINCT substr(data, 1, 7) AS m FROM notas_prod_dia WHERE operacao_id = ? AND origem = ? "
                 "AND data BETWEEN ? AND ?", (operacao_id, origem, de, ate))
    return set(b["m"])


def meses_resumo(operacao_id: int, origem: str, de: str, ate: str) -> list[str]:
    """Meses calculados pelo resumo mensal do 03.02.37 que já estava no sistema (sem o detalhe por dia)."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    a = query_df(f"SELECT DISTINCT mes AS m FROM notas_produto_mes WHERE {trecho} AND origem = ? AND mes BETWEEN ? "
                 f"AND ?", (*p, origem, de[:7], ate[:7]))
    feitos = set()
    for op in operacoes_repo.ids_efetivos(operacao_id):
        feitos |= meses_com_dia(op, origem, de, ate)
    return sorted(set(a["m"]) - feitos)


def _tab_mes(tab: pd.DataFrame, mes: str) -> tuple[pd.DataFrame, bool]:
    """Tabela do mês (ou do último mês anterior subido; sem anterior, a primeira). Devolve (tabela, é_do_mês)."""
    if tab.empty:
        return tab, False
    meses_tab = sorted(tab["mes"].fillna(tab["ini"].str[:7]).unique())
    ant = [v for v in meses_tab if v <= mes]
    usar = ant[-1] if ant else meses_tab[0]
    return tab[tab["mes"].fillna(tab["ini"].str[:7]) == usar], usar == mes


def _carreto_unico(tab: pd.DataFrame) -> pd.DataFrame:
    """O carreto NÃO muda por fábrica: junta as tabelas de todas as unidades numa só (produto × vigência)."""
    if tab.empty:
        return tab
    t = tab.dropna(subset=["carreto"]).sort_values("importado_em" if "importado_em" in tab else "ini")
    return t.drop_duplicates(["mes", "produto", "ini"], keep="last")


def _tarifa_media_mes(produtos: list[str], tab_mes: pd.DataFrame, campo: str, mes: str) -> pd.Series:
    """Tarifa do período (mês): média dos dias do mês, cada dia com a vigência dele."""
    if not produtos or tab_mes.empty:
        return pd.Series(dtype=float)
    dias = pd.date_range(f"{mes}-01", pd.Period(mes).end_time.normalize()).strftime("%Y-%m-%d")
    grade = pd.DataFrame([(d, p_) for p_ in produtos for d in dias], columns=["data", "produto"])
    r = _tarifa(grade, tab_mes.assign(mes=mes), campo)
    return r.groupby("produto")["tarifa"].mean()


def _resumo_mes(operacao_id: int, origem: str, ops: list[str], mes: str) -> pd.DataFrame:
    from services import faturamento_service as fs

    st_ = fs.STATUS_PADRAO[origem]
    if not ops:
        return pd.DataFrame(columns=["produto", "descricao", "qtde", "hl"])
    df = query_df(f"""SELECT produto, MAX(descricao) AS descricao, SUM(qtde) AS qtde, SUM(hl) AS hl
                      FROM notas_produto_mes WHERE operacao_id = ? AND origem = ? AND mes = ?
                      AND operacao_cod IN ({', '.join('?' * len(ops))}) AND status IN ({', '.join('?' * len(st_))})
                      GROUP BY produto""", (operacao_id, origem, mes, *ops, *st_))
    if df.empty:
        return df
    df["produto"] = df["produto"].map(_cod)
    for c in ("qtde", "hl"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df.groupby("produto", as_index=False).agg(descricao=("descricao", "first"), qtde=("qtde", "sum"),
                                                     hl=("hl", "sum"))


def _meses(de: str, ate: str) -> list[str]:
    return [str(p) for p in pd.period_range(de[:7], ate[:7], freq="M")]


def _tarifa(q: pd.DataFrame, tab: pd.DataFrame, campo: str) -> pd.DataFrame:
    """Põe em cada linha (data × produto) a tarifa do dia: usa a tabela do MÊS da data (a subida para aquele mês) e,
    dentro dela, a vigência de maior início ≤ data. Mês sem tabela usa a do último mês anterior e marca fora_vig."""
    if q.empty or tab.empty:
        return q.assign(tarifa=float("nan"), fora_vig=False)
    t = tab[["mes", "produto", "ini", campo]].dropna(subset=[campo]).copy()
    if t.empty:
        return q.assign(tarifa=float("nan"), fora_vig=False)
    t["mes"] = t["mes"].fillna(t["ini"].str[:7])
    t["ini_d"] = pd.to_datetime(t["ini"])
    t = t.drop_duplicates(["mes", "produto", "ini_d"], keep="last")
    meses_tab = sorted(t["mes"].unique())
    x = q.copy()
    x["_ord"] = range(len(x))
    x["_mes"] = x["data"].str[:7]
    partes = []
    for m, xm in x.groupby("_mes"):
        ant = [v for v in meses_tab if v <= m]
        usar = ant[-1] if ant else meses_tab[0]
        tm = t[t["mes"] == usar].sort_values("ini_d")
        xm = xm.assign(data_d=pd.to_datetime(xm["data"])).sort_values("data_d")
        r = pd.merge_asof(xm, tm[["produto", "ini_d", campo]], left_on="data_d", right_on="ini_d", by="produto",
                          direction="backward")
        falta = r[campo].isna() & r["produto"].isin(set(tm["produto"]))
        if falta.any():  # dia antes da primeira vigência do mês: usa a primeira
            prim = tm.groupby("produto")[campo].first()
            r.loc[falta, campo] = r.loc[falta, "produto"].map(prim)
        r["fora_vig"] = r[campo].notna() & (usar != m)
        partes.append(r)
    m_ = pd.concat(partes, ignore_index=True).rename(columns={campo: "tarifa"}).sort_values("_ord")
    return m_.drop(columns=["_ord", "_mes", "data_d", "ini_d"]).reset_index(drop=True)


_COLS_CARRETO = ["operacao_id", "data", "produto", "descricao", "qtde", "hl", "tarifa", "valor", "fora_vig", "base"]
_COLS_FRETE = ["operacao_id", "data", "fornecedor", "unidade_cod", "unidade_nome", "produto", "descricao", "qtde", "hl",
               "tarifa", "valor", "fora_vig", "base"]


def carreto(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    """Caixas entregues × carreto (coluna P). O carreto é o mesmo em qualquer fábrica: vale a tabela do mês (todas
    as unidades juntas), com a vigência de cada dia. Mês sem o detalhe por dia usa o resumo mensal do 03.02.37 que
    já está no sistema × carreto do período (média dos dias do mês)."""
    partes = []
    for op in operacoes_repo.ids_efetivos(operacao_id):
        ops = _ops(op, "carreto")
        tab = _carreto_unico(tabela(op))
        com_dia = meses_com_dia(op, "venda", de, ate)
        q = _qtd_dia(op, "venda", ops, de, ate) if com_dia else pd.DataFrame()
        if not q.empty:
            q = q.groupby(["operacao_id", "data", "produto"], as_index=False).agg(
                descricao=("descricao", "first"), qtde=("qtde", "sum"), hl=("hl", "sum"))
            r = _tarifa(q, tab, "carreto")
            partes.append(r.assign(valor=(r["qtde"] * r["tarifa"]).fillna(0.0), base="dia"))
        for mes in _meses(de, ate):
            if mes in com_dia:
                continue
            rm = _resumo_mes(op, "venda", ops, mes)
            if rm.empty:
                continue
            tm, do_mes = _tab_mes(tab, mes)
            tar = _tarifa_media_mes(rm["produto"].tolist(), tm, "carreto", mes)
            rm["tarifa"] = rm["produto"].map(tar)
            partes.append(rm.assign(operacao_id=op, data=f"{mes}-01", valor=(rm["qtde"] * rm["tarifa"]).fillna(0.0),
                                    fora_vig=rm["tarifa"].notna() & (not do_mes), base="mês"))
    if not partes:
        return pd.DataFrame(columns=_COLS_CARRETO)
    return pd.concat(partes, ignore_index=True)[_COLS_CARRETO]


def _frete_mes_resumo(op: int, mes: str, ops: list[str], tab: pd.DataFrame, mp: dict) -> pd.DataFrame:
    """Mês sem detalhe por dia: caixas compradas por produto (resumo mensal) repartidas entre as fábricas ligadas
    que têm o produto na tabela, na proporção do HL comprado de cada fábrica no mês (resumo por fornecedor)."""
    from services import faturamento_service as fs

    rm = _resumo_mes(op, "compra", ops, mes)
    if rm.empty:
        return pd.DataFrame(columns=_COLS_FRETE)
    st_ = fs.STATUS_PADRAO["compra"]
    cli = query_df(f"""SELECT cliente, MAX(nome) AS nome, SUM(hl) AS hl FROM notas_cliente_mes WHERE operacao_id = ?
                       AND origem = 'compra' AND mes = ? AND operacao_cod IN ({', '.join('?' * len(ops))})
                       AND status IN ({', '.join('?' * len(st_))}) GROUP BY cliente""", (op, mes, *ops, *st_))
    cli["cliente"] = cli["cliente"].map(_cod)
    cli["hl"] = pd.to_numeric(cli["hl"], errors="coerce").fillna(0.0)
    hl_forn = cli.groupby("cliente")["hl"].sum()
    forn_unid = {f: u for (o, u), f in mp.items() if o == op}
    tm, do_mes = _tab_mes(tab, mes)
    nomes_u = dict(zip(tab["unidade_cod"], tab["unidade_nome"])) if not tab.empty else {}
    # tarifa de frete do período por unidade × produto
    tarifas = {}
    for u, tu in (tm.groupby("unidade_cod") if not tm.empty else []):
        tarifas[u] = _tarifa_media_mes(rm["produto"].tolist(), tu, "frete", mes)
    linhas = []
    for r in rm.itertuples(index=False):
        cand = [(f, u) for f, u in forn_unid.items() if u in tarifas and pd.notna(tarifas[u].get(r.produto))
                and hl_forn.get(f, 0) > 0]
        tot = sum(hl_forn.get(f, 0) for f, _ in cand)
        if not cand or not tot:
            linhas.append((op, f"{mes}-01", "", "", "", r.produto, r.descricao, r.qtde, r.hl, float("nan"), 0.0,
                           False, "mês"))
            continue
        for f, u in cand:
            k = hl_forn[f] / tot
            t = float(tarifas[u][r.produto])
            linhas.append((op, f"{mes}-01", f, u, nomes_u.get(u, ""), r.produto, r.descricao, r.qtde * k, r.hl * k, t,
                           r.qtde * k * t, not do_mes, "mês"))
    return pd.DataFrame(linhas, columns=_COLS_FRETE)


def frete(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    """Caixas puxadas de cada fábrica × frete puxada (coluna N) da tabela daquela fábrica (o frete muda por fábrica).
    Mês sem o detalhe por dia usa o resumo mensal do 03.02.37 compra que já está no sistema."""
    partes = []
    for op in operacoes_repo.ids_efetivos(operacao_id):
        ops = _ops(op, "frete")
        tab = tabela(op)
        mp = mapas(op)
        com_dia = meses_com_dia(op, "compra", de, ate)
        q = _qtd_dia(op, "compra", ops, de, ate) if com_dia else pd.DataFrame()
        if not q.empty:
            q = q.rename(columns={"cliente": "fornecedor"})
            forn_unid = {f: u for (o, u), f in mp.items() if o == op}
            nomes_u = dict(zip(tab["unidade_cod"], tab["unidade_nome"])) if not tab.empty else {}
            q["unidade_cod"] = q["fornecedor"].map(forn_unid).fillna("")
            q["unidade_nome"] = q["unidade_cod"].map(nomes_u).fillna("")
            saida = []
            for u, qu in q.groupby("unidade_cod"):
                if u and not tab.empty:
                    saida.append(_tarifa(qu.reset_index(drop=True), tab[tab["unidade_cod"] == u], "frete"))
                else:
                    saida.append(qu.assign(tarifa=float("nan"), fora_vig=False))
            q = pd.concat(saida, ignore_index=True)
            partes.append(q.assign(valor=(q["qtde"] * q["tarifa"]).fillna(0.0), base="dia"))
        for mes in _meses(de, ate):
            if mes not in com_dia:
                fm = _frete_mes_resumo(op, mes, ops, tab, mp)
                if not fm.empty:
                    partes.append(fm)
    if not partes:
        return pd.DataFrame(columns=_COLS_FRETE)
    return pd.concat(partes, ignore_index=True)[_COLS_FRETE]


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
