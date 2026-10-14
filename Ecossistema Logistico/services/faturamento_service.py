"""Gestão Corporativa — Faturamento (03.02.37 vendas), Compras de mercadoria (03.02.37 compra) e cadastro
de operações por setor.

• Coluna C = código da operação (1 venda, 2 bonificação…), coluna Z = total faturado (R$), coluna T = quantidade
  → HL = quantidade × fator HL da 01.11 (produtos em litros: litros ÷ 100).
• Cada setor (Faturamento venda, Faturamento bonificação, Produtividade Entrega, Compras) conta só as operações
  marcadas em ⚙️ Cadastros. Sem marcação, vale o padrão (venda 1, bonificação 2, entrega 1, compra 251).
• As notas ficam resumidas por dia × operação × status (notas_dia) e por mês × produto (notas_produto_mes):
  leve para o banco e para o backup, e suficiente para a gestão diária, mensal e anual.
"""
import calendar
import datetime as dt
import io

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df
from repositories import operacoes_repo
from services.erros import RegraNegocioError

SETORES = {
    "fat_venda": ("💵 Faturamento — Venda", ["1"]),
    "fat_bonif": ("🎁 Faturamento — Bonificação", ["2"]),
    "entrega": ("🚚 Produtividade Entrega", ["1"]),
    "compra": ("🛒 Compras de mercadoria", ["251"]),
}
STATUS_PADRAO = {"venda": ["A"], "compra": ["A", "E"]}
_STATUS_NOME = {"A": "A · Ativa", "C": "C · Cancelada", "D": "D · Devolvida", "E": "E · Entrada/Estorno"}


# --- Leitura comum --------------------------------------------------------------------------------
def num_br(s: pd.Series) -> pd.Series:
    """Números do Promax: ponto = milhar, vírgula = decimal ('1.602' = 1602; '29.959,64' = 29959,64)."""
    t = s.astype(str).str.strip().str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


def cod(v) -> str:
    import re

    return re.sub(r"\D", "", str(v or "")).lstrip("0") or "0"


# posições (A = 0): C operação, D tipo movto, F dt. operação, G emissão, H nota, J status, M cliente, P produto,
# N nome do cliente, Q unidade, R descrição, T quantidade, U valor bruto, Y desconto, Z total, AA mapa
POS = {2: "operacao_cod", 3: "tipo_movto", 5: "dt_operacao", 6: "emissao", 7: "nota", 9: "status", 12: "cliente",
       13: "nome_cliente", 15: "produto", 16: "unidade", 17: "descricao", 19: "qtde", 20: "valor_bruto", 24: "desconto", 25: "valor",
       26: "mapa"}


def ler_0302037(bruto: bytes) -> pd.DataFrame:
    """Lê o 03.02.37 (vendas ou compra) só com as colunas usadas e já calcula o HL de cada item."""
    from services.produtividade_entrega_service import _ler_csv, _n

    cab = _ler_csv(bruto, nrows=0)
    if len(cab.columns) < 27 or "qtde" not in _n(cab.columns[19]) or "total" not in _n(cab.columns[25]):
        raise RegraNegocioError("Este arquivo não parece o 03.02.37: esperava “Qtde” na coluna T e “Total” na "
                                "coluna Z.")
    df = _ler_csv(bruto, usecols=list(POS))
    df.columns = [POS[i] for i in sorted(POS)]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    for c in ("operacao_cod", "tipo_movto"):
        df[c] = df[c].map(cod)
    df["status"] = df["status"].str.upper().replace({"": "?", "NAN": "?"})
    for c in ("qtde", "valor_bruto", "desconto", "valor"):
        df[c] = num_br(df[c]).fillna(0.0)
    for c in ("dt_operacao", "emissao"):
        df[c] = pd.to_datetime(df[c], format="%d/%m/%Y", errors="coerce").dt.strftime("%Y-%m-%d")
    df["cod"] = pd.to_numeric(df["produto"].str.replace(r"\D", "", regex=True), errors="coerce")
    fat = query_df("SELECT cod, fator_hl FROM produtos")
    fat["cod"] = pd.to_numeric(fat["cod"], errors="coerce")
    df = df.merge(fat.dropna().drop_duplicates("cod"), on="cod", how="left")
    litros = df["unidade"].str.lower().isin(["l", "lt", "lts", "litro", "litros"])
    df["hl"] = (df["qtde"] * df["fator_hl"].fillna(0.0)).where(~litros, df["qtde"] / 100)
    df["sem_fator"] = ~litros & df["fator_hl"].isna()
    return df


def gravar_resumo(df: pd.DataFrame, operacao_id: int, origem: str, coluna_data: str) -> dict:
    """Grava notas_dia e notas_produto_mes de um 03.02.37 (substitui as datas/meses do arquivo)."""
    from services.produtividade_entrega_service import _py

    d = df[df[coluna_data].notna()].copy()
    if d.empty:
        raise RegraNegocioError("Nenhuma nota com data válida no arquivo.")
    d["data"] = d[coluna_data]
    d["mes"] = d["data"].str[:7]
    dia = (d.groupby(["data", "operacao_cod", "tipo_movto", "status"], as_index=False)
             .agg(valor=("valor", "sum"), valor_bruto=("valor_bruto", "sum"), desconto=("desconto", "sum"),
                  hl=("hl", "sum"), qtde=("qtde", "sum"), notas=("nota", "nunique"), clientes=("cliente", "nunique"),
                  itens=("produto", "size")))
    prod = (d.groupby(["mes", "operacao_cod", "status", "produto"], as_index=False)
              .agg(descricao=("descricao", "first"), valor=("valor", "sum"), hl=("hl", "sum"), qtde=("qtde", "sum"),
                   clientes=("cliente", "nunique")))
    cli = (d.groupby(["mes", "operacao_cod", "status", "cliente"], as_index=False)
             .agg(nome=("nome_cliente", "first"),
                  valor=("valor", "sum"), hl=("hl", "sum"), notas=("nota", "nunique")))
    agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for data in dia["data"].unique():
            conn.execute("DELETE FROM notas_dia WHERE operacao_id = ? AND origem = ? AND data = ?",
                         (operacao_id, origem, data))
        for mes in prod["mes"].unique():
            # o mês do produto é regravado com o que veio no arquivo (o arquivo traz o mês inteiro ou o parcial)
            conn.execute("DELETE FROM notas_produto_mes WHERE operacao_id = ? AND origem = ? AND mes = ?",
                         (operacao_id, origem, mes))
            conn.execute("DELETE FROM notas_cliente_mes WHERE operacao_id = ? AND origem = ? AND mes = ?",
                         (operacao_id, origem, mes))
        for tabela, tab in (("notas_dia", dia), ("notas_produto_mes", prod), ("notas_cliente_mes", cli)):
            tab = tab.assign(operacao_id=operacao_id, origem=origem, importado_em=agora)
            cols = list(tab.columns)
            conn.executemany(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                             [tuple(_py(v) for v in r) for r in tab.itertuples(index=False)])
    return {"de": d["data"].min(), "ate": d["data"].max(), "valor": float(d["valor"].sum()),
            "hl": float(d["hl"].sum()), "itens": len(d), "sem_fator": int(d.loc[d["sem_fator"], "produto"].nunique())}


def importar_compra(conteudo: bytes, nome: str, operacao_id: int, usuario: str = "") -> dict:
    from services.produtividade_entrega_service import _abrir, _log

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir a 03.02.37 compra.")
    df = ler_0302037(_abrir(conteudo, nome))
    r = gravar_resumo(df, operacao_id, "compra", "dt_operacao")
    _log(operacao_id, "notas_compra", len(df), nome, usuario)
    return r


# --- Relatório de operações e cadastro por setor ------------------------------------------------------
def importar_operacoes(conteudo: bytes, nome: str) -> int:
    from services.produtividade_entrega_service import _abrir, _ler_csv, _n

    df = _ler_csv(_abrir(conteudo, nome))
    cols = {_n(c): c for c in df.columns}
    c_cod = next((cols[k] for k in cols if k.startswith("cod")), df.columns[0])
    c_tipo = next((cols[k] for k in cols if "tipo" in k), df.columns[1] if len(df.columns) > 2 else None)
    c_nome = next((cols[k] for k in cols if "nome" in k or "descr" in k), df.columns[-1])
    linhas = []
    for _, r in df.iterrows():
        c = cod(r[c_cod])
        if c == "0":
            continue
        linhas.append((c, cod(r[c_tipo]) if c_tipo else None, str(r[c_nome] or "").strip()))
    if not linhas:
        raise RegraNegocioError("Nenhuma operação no arquivo (esperava Código; Tipo Movimento; Nome da Operação).")
    with get_conn() as conn:
        for c, t, n in linhas:
            conn.execute("""INSERT INTO operacoes_fiscais (codigo, tipo_movto, nome) VALUES (?, ?, ?)
                            ON CONFLICT(codigo) DO UPDATE SET tipo_movto = excluded.tipo_movto,
                            nome = excluded.nome""", (c, t, n))
    return len(linhas)


def nomes_operacoes() -> dict[str, str]:
    df = query_df("SELECT codigo, nome FROM operacoes_fiscais")
    return dict(zip(df["codigo"].astype(str), df["nome"].fillna("")))


def rotulo_op(codigo: str, nomes: dict | None = None) -> str:
    nomes = nomes if nomes is not None else nomes_operacoes()
    n = (nomes.get(str(codigo)) or "").strip()
    return f"{codigo} · {n}" if n else f"{codigo}"


def salvar_nome_operacao(codigo: str, nome: str) -> None:
    execute("""INSERT INTO operacoes_fiscais (codigo, nome) VALUES (?, ?)
               ON CONFLICT(codigo) DO UPDATE SET nome = excluded.nome""", (cod(codigo), nome.strip()))


def operacoes_do_setor(setor: str) -> list[str]:
    df = query_df("SELECT codigo FROM setor_operacoes WHERE setor = ?", (setor,))
    return sorted(df["codigo"].astype(str).tolist(), key=lambda x: (len(x), x)) if not df.empty \
        else list(SETORES[setor][1])


def salvar_setor(setor: str, codigos: list[str]) -> None:
    if setor not in SETORES:
        raise RegraNegocioError("Setor desconhecido.")
    with get_conn() as conn:
        conn.execute("DELETE FROM setor_operacoes WHERE setor = ?", (setor,))
        conn.executemany("INSERT INTO setor_operacoes (setor, codigo) VALUES (?, ?)",
                         [(setor, cod(c)) for c in codigos])


def operacoes_nas_bases() -> pd.DataFrame:
    """Operações que aparecem nos 03.02.37 já carregados (venda e compra), com valores — para o cadastro."""
    df = query_df("""SELECT origem, operacao_cod AS codigo, MIN(tipo_movto) AS tipo_movto, SUM(valor) AS valor,
                            SUM(hl) AS hl, SUM(notas) AS notas FROM notas_dia GROUP BY origem, operacao_cod""")
    return df


# --- Consultas ---------------------------------------------------------------------------------------
def meses(operacao_id: int, origem: str) -> list[str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_df(f"SELECT DISTINCT substr(data, 1, 7) AS m FROM notas_dia WHERE {trecho} AND origem = ? "
                 "ORDER BY m DESC", (*p, origem))
    return r["m"].tolist()


def status_disponiveis(operacao_id: int, origem: str) -> list[str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_df(f"SELECT DISTINCT status FROM notas_dia WHERE {trecho} AND origem = ?", (*p, origem))
    return sorted(r["status"].dropna().tolist())


def dia_df(operacao_id: int, origem: str, de: str, ate: str, status: list[str] | None) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    sql = (f"SELECT data, operacao_cod, tipo_movto, status, SUM(valor) AS valor, SUM(valor_bruto) AS valor_bruto, "
           f"SUM(desconto) AS desconto, SUM(hl) AS hl, SUM(qtde) AS qtde, SUM(notas) AS notas, "
           f"SUM(clientes) AS clientes FROM notas_dia WHERE {trecho} AND origem = ? AND data BETWEEN ? AND ?")
    params = [*p, origem, de, ate]
    if status:
        sql += f" AND status IN ({', '.join('?' * len(status))})"
        params += list(status)
    df = query_df(sql + " GROUP BY data, operacao_cod, tipo_movto, status", params)
    for c in ("valor", "valor_bruto", "desconto", "hl", "qtde", "notas", "clientes"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


def produto_df(operacao_id: int, origem: str, mes_de: str, mes_ate: str, status: list[str] | None,
               ops: list[str]) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    sql = (f"SELECT produto, MAX(descricao) AS descricao, SUM(valor) AS valor, SUM(hl) AS hl, SUM(qtde) AS qtde "
           f"FROM notas_produto_mes WHERE {trecho} AND origem = ? AND mes BETWEEN ? AND ?")
    params = [*p, origem, mes_de, mes_ate]
    if status:
        sql += f" AND status IN ({', '.join('?' * len(status))})"
        params += list(status)
    if ops:
        sql += f" AND operacao_cod IN ({', '.join('?' * len(ops))})"
        params += list(ops)
    df = query_df(sql + " GROUP BY produto", params)
    for c in ("valor", "hl", "qtde"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["rs_hl"] = df["valor"] / df["hl"].where(df["hl"] > 0)
    return df.sort_values("valor", ascending=False).reset_index(drop=True)


def cliente_df(operacao_id: int, origem: str, mes_de: str, mes_ate: str, status: list[str] | None,
               ops: list[str]) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    sql = (f"SELECT cliente, MAX(nome) AS nome, SUM(valor) AS valor, SUM(hl) AS hl, SUM(notas) AS notas "
           f"FROM notas_cliente_mes WHERE {trecho} AND origem = ? AND mes BETWEEN ? AND ?")
    params = [*p, origem, mes_de, mes_ate]
    if status:
        sql += f" AND status IN ({', '.join('?' * len(status))})"
        params += list(status)
    if ops:
        sql += f" AND operacao_cod IN ({', '.join('?' * len(ops))})"
        params += list(ops)
    df = query_df(sql + " GROUP BY cliente", params)
    for c in ("valor", "hl", "notas"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["rs_hl"] = df["valor"] / df["hl"].where(df["hl"] > 0)
    return df.sort_values("valor", ascending=False).reset_index(drop=True)


def periodo_mes(mes: str) -> tuple[str, str]:
    a, m = map(int, mes.split("-"))
    return f"{mes}-01", f"{mes}-{calendar.monthrange(a, m)[1]:02d}"


def separar(df: pd.DataFrame, grupos: dict[str, list[str]]) -> dict[str, pd.DataFrame]:
    """{"venda": linhas das operações de venda, "bonif": …}"""
    return {k: df[df["operacao_cod"].astype(str).isin(v)] for k, v in grupos.items()}


def totais(df: pd.DataFrame) -> dict:
    v, h = float(df["valor"].sum()), float(df["hl"].sum())
    return {"valor": v, "hl": h, "rs_hl": v / h if h else None, "notas": float(df["notas"].sum()),
            "qtde": float(df["qtde"].sum()), "desconto": float(df["desconto"].sum()) if "desconto" in df else 0.0,
            "valor_bruto": float(df["valor_bruto"].sum()) if "valor_bruto" in df else 0.0,
            "dias": int(df["data"].nunique()) if "data" in df else 0}


def serie(df: pd.DataFrame, chave: str) -> pd.DataFrame:
    """Agrupa por `data` ou `mes`: valor, hl, R$/HL, notas, qtde."""
    if df.empty:
        return pd.DataFrame(columns=[chave, "valor", "hl", "rs_hl", "notas", "qtde"])
    d = df.assign(mes=df["data"].str[:7]) if chave == "mes" else df
    g = d.groupby(chave, as_index=False)[["valor", "hl", "notas", "qtde", "desconto"]].sum()
    g["rs_hl"] = g["valor"] / g["hl"].where(g["hl"] > 0)
    return g.sort_values(chave).reset_index(drop=True)


def por_operacao(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    g = df.groupby(["operacao_cod", "tipo_movto"], as_index=False)[["valor", "hl", "notas", "qtde"]].sum()
    g["rs_hl"] = g["valor"] / g["hl"].where(g["hl"] > 0)
    nomes = nomes_operacoes()
    g["operacao"] = g["operacao_cod"].map(lambda c: rotulo_op(c, nomes))
    return g.sort_values("valor", ascending=False).reset_index(drop=True)


def ultimas(operacao_id: int) -> dict:
    from database.connection import query_one

    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    out = {}
    for b in ("entregas_pcd", "entregas_notas", "notas_compra"):
        x = query_one(f"SELECT MAX(dt) AS dt FROM bases_log WHERE base = ? AND {trecho}", (b, *p))
        out[b] = x["dt"] if x else None
    x = query_one("SELECT COUNT(*) AS n FROM operacoes_fiscais")
    out["operacoes"] = int(x["n"]) if x else 0
    return out


def hoje() -> dt.date:
    return tempo.hoje()


def ler_bytes(arquivo) -> bytes:
    return arquivo.getvalue() if hasattr(arquivo, "getvalue") else io.BytesIO(arquivo).getvalue()
