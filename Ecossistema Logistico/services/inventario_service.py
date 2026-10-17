"""Armazém › 🎯 Acuracidade de Estoque › 📦 Inventário mensal.

Base do sistema: 02.05.02 "especial" — coluna L (Disponível, "cx/un") por produto e depósito.
Contagens: relatório de contagens do WMS — C = área (tarefa), D = endereço, E = usuário, K = quantidade, L = unidade.
Cada área é contada por dois usuários (1ª e 2ª contagem, pela ordem em que terminaram). Endereço × produto com as duas
contagens diferentes vai para recontagem (app), e a recontagem é conciliada com uma das contagens.
Tudo é apurado em QUANTIDADE (unidades), com as conversões da 01.11 (caixas/palete, caixas/lastro, unidades/caixa).
"""
from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services.erros import RegraNegocioError

STATUS = {
    "ok": "✅ Bateu",
    "divergente": "⚠️ Divergente",
    "aguardando": "⏳ Falta 2ª contagem",
    "pendente": "📨 Em recontagem",
    "recontado": "📥 Recontado — conciliar",
    "conciliado": "✔️ Conciliado",
    "sem_conversao": "❔ Sem conversão",
}
REC_STATUS = {"pendente": "📨 Aguardando recontagem", "contado": "✍️ Contado (falta descarga)",
              "recontado": "📥 Descarga feita — conciliar", "conciliado": "✔️ Conciliado"}
ESCOLHAS = {"c1": "1ª contagem", "c2": "2ª contagem", "rec": "Recontagem"}
_UN = {"UN", "UND", "UNID", "UNIDADE", "U", "GF", "GFA"}
_PL = {"PL", "PLT", "PALETE", "PALLET", "PAL"}
_LST = {"LST", "LASTRO", "CAMADA"}
TOLERANCIA_UN = 0.5


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M:%S")


def _norm(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()


def _cod(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0") or "0"


def cx_un(un, fator) -> str:
    """Quantidade em unidades no formato do Promax: caixas/unidades (ex.: 1.577/05)."""
    if un is None or pd.isna(un):
        return "—"
    f = float(fator or 1) or 1.0
    neg = un < 0
    un = abs(float(un))
    if f <= 1:
        txt = f"{un:,.0f}".replace(",", ".") if float(un).is_integer() else f"{un:,.2f}".replace(",", "X").replace(
            ".", ",").replace("X", ".")
        return ("-" if neg else "") + txt
    cx = int(un // f)
    resto = un - cx * f
    txt = f"{cx:,}".replace(",", ".") + f"/{int(round(resto)):02d}"
    return ("-" if neg and (cx or resto) else "") + txt


# --- cadastros: armazéns, áreas, conversões, responsáveis --------------------------------------------------------------
def armazens(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT id, operacao_id, nome, ativo FROM inv_armazens WHERE {trecho} ORDER BY nome", p)


def salvar_armazens(operacao_id: int, linhas: list[dict]) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para cadastrar armazéns.")
    with get_conn() as conn:
        for r in linhas:
            nome = str(r.get("nome") or "").strip()
            rid = r.get("id")
            if rid is not None and not pd.isna(rid):
                if not nome:
                    conn.execute("DELETE FROM inv_armazens WHERE id = ?", (int(rid),))
                    conn.execute("UPDATE inv_areas SET armazem_id = NULL WHERE armazem_id = ?", (int(rid),))
                else:
                    conn.execute("UPDATE inv_armazens SET nome = ?, ativo = ? WHERE id = ?",
                                 (nome, 1 if r.get("ativo", True) else 0, int(rid)))
            elif nome:
                conn.execute("INSERT INTO inv_armazens (operacao_id, nome, ativo) VALUES (?, ?, 1)",
                             (operacao_id, nome))


def areas(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("a.operacao_id", operacao_id)
    df = query_df(f"""SELECT a.id, a.operacao_id, a.codigo, a.nome, a.armazem_id, w.nome AS armazem, a.ativo, a.ordem
                      FROM inv_areas a LEFT JOIN inv_armazens w ON w.id = a.armazem_id WHERE {trecho}
                      ORDER BY a.ordem, a.codigo""", p)
    if not df.empty:
        df["nome"] = df["nome"].where(df["nome"].fillna("").astype(str).str.strip() != "", df["codigo"])
        df["armazem"] = df["armazem"].fillna("— sem armazém")
    return df


def _garantir_areas(conn, operacao_id: int, codigos: list[str]) -> None:
    exist = {r[0] for r in conn.execute("SELECT codigo FROM inv_areas WHERE operacao_id = ?",
                                        (operacao_id,)).fetchall()}
    for c in sorted(set(codigos) - exist):
        conn.execute("INSERT INTO inv_areas (operacao_id, codigo, nome, ativo, ordem) VALUES (?, ?, ?, 1, 0)",
                     (operacao_id, c, _nome_area(c)))


def _nome_area(codigo: str) -> str:
    return re.sub(r"^\s*\d+\s*\.\s*", "", str(codigo)).strip() or str(codigo)


def salvar_areas(operacao_id: int, linhas: list[dict]) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para cadastrar as áreas.")
    with get_conn() as conn:
        for r in linhas:
            rid = r.get("id")
            arm = r.get("armazem_id")
            arm = None if arm is None or pd.isna(arm) else int(arm)
            nome = str(r.get("nome") or "").strip() or None
            ordem = int(r.get("ordem") or 0) if not pd.isna(r.get("ordem") or 0) else 0
            if rid is not None and not pd.isna(rid):
                conn.execute("UPDATE inv_areas SET nome = ?, armazem_id = ?, ativo = ?, ordem = ? WHERE id = ?",
                             (nome, arm, 1 if r.get("ativo", True) else 0, ordem, int(rid)))
            elif str(r.get("codigo") or "").strip():
                conn.execute("INSERT INTO inv_areas (operacao_id, codigo, nome, armazem_id, ativo, ordem) "
                             "VALUES (?, ?, ?, ?, 1, ?)", (operacao_id, str(r["codigo"]).strip(), nome, arm, ordem))


def responsaveis(operacao_id: int) -> list[int]:
    r = query_one("SELECT valor FROM inv_config WHERE operacao_id = ? AND chave = 'responsaveis'", (operacao_id,))
    return [int(x) for x in str((r or {}).get("valor") or "").split(",") if x.strip().isdigit()]


def salvar_responsaveis(operacao_id: int, ids: list[int]) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda.")
    with get_conn() as conn:
        conn.execute("DELETE FROM inv_config WHERE operacao_id = ? AND chave = 'responsaveis'", (operacao_id,))
        conn.execute("INSERT INTO inv_config (operacao_id, chave, valor) VALUES (?, 'responsaveis', ?)",
                     (operacao_id, ",".join(str(int(i)) for i in ids)))


def conversoes(inv_id: int | None = None, produtos: list[str] | None = None) -> pd.DataFrame:
    """produto → un_cx (unidades por caixa), cx_pallet, cx_lastro. Ordem: ajuste manual → 02.05.02 do inventário
    (fator) → 01.11."""
    p = query_df("SELECT cod, descricao, fator_hl, cx_pallet, cx_lastro, un_cx FROM produtos")
    p["produto"] = pd.to_numeric(p["cod"], errors="coerce").astype("Int64").astype(str)
    p = p.drop(columns="cod").drop_duplicates("produto")
    o = query_df("SELECT produto, un_cx AS un_cx_m, cx_pallet AS cx_pallet_m, cx_lastro AS cx_lastro_m FROM "
                 "inv_conversao")
    df = p.merge(o, on="produto", how="outer")
    if inv_id:
        b = query_df("SELECT produto, MAX(fator) AS fator_b, MAX(descricao) AS desc_b FROM inv_base WHERE inv_id = ? "
                     "GROUP BY produto", (inv_id,))
        df = df.merge(b, on="produto", how="outer")
        df["descricao"] = df["descricao"].fillna(df.pop("desc_b"))
    else:
        df["fator_b"] = float("nan")
    for c in ("un_cx", "cx_pallet", "cx_lastro", "un_cx_m", "cx_pallet_m", "cx_lastro_m", "fator_b"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["un_cx_f"] = df["un_cx_m"].fillna(df["fator_b"]).fillna(df["un_cx"]).fillna(1.0)
    df["cx_pallet_f"] = df["cx_pallet_m"].fillna(df["cx_pallet"].where(df["cx_pallet"] > 0))
    df["cx_lastro_f"] = df["cx_lastro_m"].fillna(df["cx_lastro"].where(df["cx_lastro"] > 0))
    if produtos is not None:
        df = df[df["produto"].isin(set(produtos))]
    return df.reset_index(drop=True)


def salvar_conversoes(linhas: list[dict], usuario: str = "") -> int:
    n = 0
    with get_conn() as conn:
        for r in linhas:
            prod = _cod(r.get("produto"))
            if prod == "0":
                continue
            vals = [None if r.get(c) is None or pd.isna(r.get(c)) or float(r.get(c)) <= 0 else float(r.get(c))
                    for c in ("un_cx", "cx_pallet", "cx_lastro")]
            conn.execute("DELETE FROM inv_conversao WHERE produto = ?", (prod,))
            if any(v is not None for v in vals):
                conn.execute("INSERT INTO inv_conversao (produto, un_cx, cx_pallet, cx_lastro, atualizado_por, "
                             "atualizado_em) VALUES (?, ?, ?, ?, ?, ?)", (prod, *vals, usuario, agora()))
            n += 1
    return n


def _multiplicador(unidade: str, conv: dict) -> float | None:
    u = re.sub(r"[^A-Z]", "", str(unidade or "").upper())
    un_cx = conv.get("un_cx_f") or 1.0
    if u in _UN:
        return 1.0
    if u in _PL:
        cp = conv.get("cx_pallet_f")
        return None if cp is None or pd.isna(cp) else float(cp) * un_cx
    if u in _LST:
        cl = conv.get("cx_lastro_f")
        return None if cl is None or pd.isna(cl) else float(cl) * un_cx
    return float(un_cx)  # CX, L, DZ, FD, PC… = unidade de venda


# --- inventários --------------------------------------------------------------------------------------------------------
def inventarios(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT * FROM inv_inventarios WHERE {trecho} ORDER BY mes DESC, id DESC", p)


def inventario(inv_id: int) -> dict | None:
    return query_one("SELECT * FROM inv_inventarios WHERE id = ?", (int(inv_id),))


def criar(operacao_id: int, mes: str, nome: str, usuario: str = "") -> int:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para abrir o inventário.")
    if not re.fullmatch(r"\d{4}-\d{2}", str(mes or "")):
        raise RegraNegocioError("Escolha o mês do inventário.")
    nome = (nome or "").strip() or f"Inventário {mes[5:]}/{mes[:4]}"
    return execute("INSERT INTO inv_inventarios (operacao_id, mes, nome, status, criado_por, criado_em) "
                   "VALUES (?, ?, ?, 'aberto', ?, ?)", (operacao_id, mes, nome, usuario, agora()))


def mudar_status(inv_id: int, status: str) -> None:
    execute("UPDATE inv_inventarios SET status = ? WHERE id = ?", (status, int(inv_id)))


def excluir(inv_id: int) -> None:
    with get_conn() as conn:
        for t in ("inv_base", "inv_contagens", "inv_recontagem"):
            conn.execute(f"DELETE FROM {t} WHERE inv_id = ?", (int(inv_id),))
        conn.execute("DELETE FROM inv_inventarios WHERE id = ?", (int(inv_id),))


def _aberto(inv_id: int) -> dict:
    inv = inventario(inv_id)
    if not inv:
        raise RegraNegocioError("Inventário não encontrado.")
    if inv["status"] != "aberto":
        raise RegraNegocioError("Este inventário está fechado — reabra para alterar.")
    return inv


def _texto(conteudo: bytes) -> str:
    for enc in ("utf-8-sig", "latin1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin1", errors="ignore")


def _cx_barra_un(v: str, fator: float) -> float | None:
    """'1.577/05' → 1577 cx e 5 un → unidades. '0/05-' negativo."""
    t = str(v or "").strip()
    if not t:
        return None
    neg = t.endswith("-") or t.startswith("-")
    t = t.strip("-").strip()
    if "/" in t:
        cx, un = t.split("/", 1)
        cx = float(cx.replace(".", "").replace(",", ".") or 0)
        un = float(un.replace(".", "").replace(",", ".") or 0)
        tot = cx * (fator or 1) + un
    else:
        try:
            tot = float(t.replace(".", "").replace(",", ".")) * (fator or 1)
        except ValueError:
            return None
    return -tot if neg else tot


def ler_base(conteudo: bytes) -> pd.DataFrame:
    """02.05.02: depósito (B), produto (D), descrição (E), unidade (F), Disponível (L, cx/un), fator (X)."""
    df = pd.read_csv(io.StringIO(_texto(conteudo)), sep=";", dtype=str, header=0, keep_default_na=False,
                     on_bad_lines="skip")
    if len(df.columns) < 24 or "dispon" not in _norm(df.columns[11]):
        raise RegraNegocioError("Este arquivo não parece o 02.05.02: esperava “Disponível” na coluna L e o fator na "
                                "coluna X.")
    c = list(df.columns)
    out = pd.DataFrame({"deposito": df[c[1]].str.strip().str.lstrip("0").replace("", "0"),
                        "produto": df[c[3]].map(_cod), "descricao": df[c[4]].str.strip(),
                        "unidade": df[c[5]].str.strip(),
                        "fator": pd.to_numeric(df[c[23]].str.strip().str.replace(",", "."), errors="coerce")})
    out = out[out["produto"] != "0"].copy()
    out["fator"] = out["fator"].where(out["fator"] > 0, 1.0)
    out["disp_un"] = [_cx_barra_un(v, f) for v, f in zip(df.loc[out.index, c[11]], out["fator"])]
    out["disp_un"] = pd.to_numeric(out["disp_un"], errors="coerce").fillna(0.0)
    return out.groupby(["deposito", "produto"], as_index=False).agg(
        descricao=("descricao", "first"), unidade=("unidade", "first"), fator=("fator", "max"),
        disp_un=("disp_un", "sum"))


def importar_base(inv_id: int, conteudo: bytes, nome: str, usuario: str = "") -> dict:
    _aberto(inv_id)
    df = ler_base(conteudo)
    with get_conn() as conn:
        conn.execute("DELETE FROM inv_base WHERE inv_id = ?", (int(inv_id),))
        conn.executemany("INSERT INTO inv_base (inv_id, deposito, produto, descricao, unidade, fator, disp_un) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         [(int(inv_id), r.deposito, r.produto, r.descricao, r.unidade, float(r.fator),
                           float(r.disp_un)) for r in df.itertuples(index=False)])
        conn.execute("UPDATE inv_inventarios SET base_arquivo = ?, base_em = ? WHERE id = ?",
                     (str(nome)[:200], agora(), int(inv_id)))
    return {"produtos": int(df["produto"].nunique()), "depositos": sorted(df["deposito"].unique(), key=lambda x: (
        len(x), x))}


def depositos_base(inv_id: int) -> list[str]:
    d = query_df("SELECT DISTINCT deposito FROM inv_base WHERE inv_id = ?", (int(inv_id),))
    return sorted(d["deposito"].astype(str).tolist(), key=lambda x: (len(x), x))


def salvar_depositos(inv_id: int, deps: list[str]) -> None:
    execute("UPDATE inv_inventarios SET depositos = ? WHERE id = ?", (",".join(deps), int(inv_id)))


def base(inv_id: int) -> pd.DataFrame:
    inv = inventario(inv_id) or {}
    deps = [d for d in str(inv.get("depositos") or "").split(",") if d]
    b = query_df("SELECT deposito, produto, descricao, unidade, fator, disp_un FROM inv_base WHERE inv_id = ?",
                 (int(inv_id),))
    if deps:
        b = b[b["deposito"].astype(str).isin(deps)]
    if b.empty:
        return pd.DataFrame(columns=["produto", "descricao", "unidade", "fator", "sistema_un"])
    return b.groupby("produto", as_index=False).agg(descricao=("descricao", "first"), unidade=("unidade", "first"),
                                                    fator=("fator", "max"), sistema_un=("disp_un", "sum"))


_COLS_WMS = {"area": ["tarefa"], "endereco": ["endereco"], "usuario": ["usuario"], "inicio": ["data contagem"],
             "finalizacao": ["finalizacao"], "produto": ["codigo item"], "descricao": ["descricao item"],
             "qtd": ["quantidade contada"], "unidade": ["unidade contada"], "validade": ["validade aferida"],
             "tipo_estoque": ["tipo estoque"]}
_POS_WMS = {"area": 2, "endereco": 3, "usuario": 4, "inicio": 5, "finalizacao": 7, "produto": 8, "descricao": 9,
            "qtd": 10, "unidade": 11, "validade": 12, "tipo_estoque": 14}


def _dt(v) -> str | None:
    d = pd.to_datetime(str(v or "").strip(), format="%d/%m/%Y %H:%M", errors="coerce")
    if pd.isna(d):
        d = pd.to_datetime(str(v or "").strip(), dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d %H:%M")


def ler_contagem(conteudo: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(_texto(conteudo)), sep=";", dtype=str, keep_default_na=False, on_bad_lines="skip")
    nomes = {_norm(c): c for c in df.columns}
    cols = {}
    for k, alvos in _COLS_WMS.items():
        col = next((nomes[a] for a in alvos if a in nomes), None)
        if col is None and len(df.columns) > _POS_WMS[k]:
            col = df.columns[_POS_WMS[k]]
        cols[k] = col
    if not cols["area"] or not cols["produto"] or not cols["qtd"] or len(df.columns) < 12:
        raise RegraNegocioError("Este arquivo não parece o relatório de contagens do WMS (Tarefa na coluna C, Endereço "
                                "na D, Usuário na E, Código Item na I, Quantidade na K e Unidade na L).")
    out = pd.DataFrame({k: df[c].astype(str).str.strip() if c else "" for k, c in cols.items()})
    out["produto"] = out["produto"].map(_cod)
    out["qtd"] = pd.to_numeric(out["qtd"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                               errors="coerce").fillna(0.0)
    out["inicio"] = out["inicio"].map(_dt)
    out["finalizacao"] = out["finalizacao"].map(_dt)
    out = out[(out["produto"] != "0") & (out["area"] != "")]
    if "tipo_estoque" in out:
        out = out.drop(columns="tipo_estoque")
    return out.reset_index(drop=True)


def importar_contagem(inv_id: int, conteudo: bytes, nome: str, usuario: str = "") -> dict:
    """Grava as contagens do WMS. Sobe de novo a mesma contagem (área × usuário × finalização) → substitui."""
    inv = _aberto(inv_id)
    df = ler_contagem(conteudo)
    if df.empty:
        raise RegraNegocioError("Nenhuma contagem no arquivo.")
    df["finalizacao"] = df["finalizacao"].fillna(df["inicio"]).fillna("")
    with get_conn() as conn:
        _garantir_areas(conn, int(inv["operacao_id"]), df["area"].unique().tolist())
        for (a, u, f), _ in df.groupby(["area", "usuario", "finalizacao"]):
            conn.execute("DELETE FROM inv_contagens WHERE inv_id = ? AND area = ? AND usuario = ? AND "
                         "COALESCE(finalizacao, '') = ?", (int(inv_id), a, u, f))
        conn.executemany(
            "INSERT INTO inv_contagens (inv_id, area, endereco, usuario, inicio, finalizacao, produto, descricao, qtd, "
            "unidade, validade, arquivo, importado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(int(inv_id), r.area, r.endereco, r.usuario, r.inicio, r.finalizacao or None, r.produto, r.descricao,
              float(r.qtd), r.unidade, r.validade, str(nome)[:200], agora()) for r in df.itertuples(index=False)])
    return {"linhas": len(df), "areas": int(df["area"].nunique()), "usuarios": sorted(df["usuario"].unique()),
            "enderecos": int(df["endereco"].nunique()), "itens": int(df["produto"].nunique())}


def limpar_contagens(inv_id: int, area: str | None = None, usuario: str | None = None) -> None:
    _aberto(inv_id)
    sql, p = "DELETE FROM inv_contagens WHERE inv_id = ?", [int(inv_id)]
    if area:
        sql, p = sql + " AND area = ?", p + [area]
    if usuario:
        sql, p = sql + " AND usuario = ?", p + [usuario]
    execute(sql, p)


def resumo_contagens(inv_id: int) -> pd.DataFrame:
    """Área × usuário: ordem da contagem, endereços, itens, linhas, quando terminou."""
    c = query_df("SELECT area, usuario, MIN(inicio) AS inicio, MAX(finalizacao) AS fim, COUNT(*) AS linhas, "
                 "COUNT(DISTINCT endereco) AS enderecos, COUNT(DISTINCT produto) AS itens, MAX(arquivo) AS arquivo "
                 "FROM inv_contagens WHERE inv_id = ? GROUP BY area, usuario", (int(inv_id),))
    if c.empty:
        return c
    c = c.sort_values(["area", "fim"])
    c["contagem"] = c.groupby("area").cumcount() + 1
    return c.reset_index(drop=True)


# --- conciliação ------------------------------------------------------------------------------------------------------
def _contagens_un(inv_id: int) -> pd.DataFrame:
    c = query_df("SELECT area, endereco, usuario, inicio, finalizacao, produto, descricao, qtd, unidade "
                 "FROM inv_contagens WHERE inv_id = ?", (int(inv_id),))
    if c.empty:
        return c.assign(qtd_un=pd.Series(dtype=float))
    conv = conversoes(inv_id, c["produto"].unique().tolist()).set_index("produto").to_dict("index")
    mult = [_multiplicador(u, conv.get(p_, {"un_cx_f": 1.0})) for u, p_ in zip(c["unidade"], c["produto"])]
    c["mult"] = pd.to_numeric(pd.Series(mult, index=c.index), errors="coerce")
    c["qtd"] = pd.to_numeric(c["qtd"], errors="coerce").fillna(0.0)
    c["qtd_un"] = c["qtd"] * c["mult"]
    c["endereco"] = c["endereco"].fillna("")
    return c


def conciliacao(inv_id: int) -> pd.DataFrame:
    """Uma linha por área × endereço × produto com a 1ª e a 2ª contagem (em unidades), status e quantidade final."""
    c = _contagens_un(inv_id)
    cols = ["area", "endereco", "produto", "descricao", "u1", "c1_un", "u2", "c2_un", "status", "final_un", "fator",
            "rec_id", "rec_status", "rec_un", "escolha", "unidades", "sem_conv"]
    if c.empty:
        return pd.DataFrame(columns=cols)
    ordem = (c.groupby(["area", "usuario"])["finalizacao"].max().reset_index()
              .sort_values(["area", "finalizacao"]))
    ordem["n"] = ordem.groupby("area").cumcount() + 1
    c = c.merge(ordem[["area", "usuario", "n"]], on=["area", "usuario"], how="left")
    usuarios_area = ordem.groupby("area")["usuario"].apply(list).to_dict()
    g = (c.groupby(["area", "endereco", "produto", "n"], as_index=False)
          .agg(descricao=("descricao", "first"), qtd_un=("qtd_un", lambda s: s.sum(min_count=len(s))),
               unidades=("unidade", lambda s: ", ".join(sorted(set(s))))))
    chave = ["area", "endereco", "produto"]
    base_ = g.groupby(chave, as_index=False).agg(descricao=("descricao", "first"),
                                                 unidades=("unidades", lambda s: ", ".join(sorted(set(", ".join(
                                                     s).split(", "))))))
    for n in (1, 2):
        x = g[g["n"] == n][chave + ["qtd_un"]].rename(columns={"qtd_un": f"c{n}_un"})
        base_ = base_.merge(x, on=chave, how="left")
    base_["u1"] = base_["area"].map(lambda a: (usuarios_area.get(a) or [None])[0])
    base_["u2"] = base_["area"].map(lambda a: (usuarios_area.get(a) or [None, None])[1]
                                    if len(usuarios_area.get(a) or []) > 1 else None)
    # quem contou a área e não achou o produto no endereço contou ZERO
    tem2 = base_["u2"].notna()
    sem_c = c.groupby(chave + ["n"])["qtd_un"].apply(lambda s: s.isna().any())
    base_["sem_conv"] = [bool(sem_c.get((a, e, p_, 1), False) or sem_c.get((a, e, p_, 2), False))
                         for a, e, p_ in zip(base_["area"], base_["endereco"], base_["produto"])]
    base_["c1_un"] = base_["c1_un"].where(base_["c1_un"].notna() | base_["sem_conv"], 0.0)
    base_.loc[tem2, "c2_un"] = base_.loc[tem2, "c2_un"].where(base_.loc[tem2, "c2_un"].notna()
                                                              | base_.loc[tem2, "sem_conv"], 0.0)
    conv = conversoes(inv_id, base_["produto"].unique().tolist()).set_index("produto")["un_cx_f"]
    base_["fator"] = base_["produto"].map(conv).fillna(1.0)
    st_ = []
    for a, c1, c2, t2, sc in zip(base_["area"], base_["c1_un"], base_["c2_un"], tem2, base_["sem_conv"]):
        if sc:
            st_.append("sem_conversao")
        elif not t2:
            st_.append("aguardando")
        elif abs(float(c1) - float(c2)) <= TOLERANCIA_UN:
            st_.append("ok")
        else:
            st_.append("divergente")
    base_["status"] = st_
    base_["final_un"] = [c1 if s in ("ok", "aguardando") else None
                         for s, c1 in zip(base_["status"], base_["c1_un"])]
    rec = query_df("SELECT id AS rec_id, area, endereco, produto, status AS rec_status, qtd_un AS rec_un, escolha, "
                   "final_un AS rec_final FROM inv_recontagem WHERE inv_id = ?", (int(inv_id),))
    if not rec.empty:
        rec["endereco"] = rec["endereco"].fillna("")
        base_ = base_.merge(rec, on=chave, how="left")
        tem = base_["rec_id"].notna() & base_["status"].isin(["divergente", "ok", "aguardando"])
        novo = base_["rec_status"].map({"pendente": "pendente", "contado": "pendente", "recontado": "recontado",
                                        "conciliado": "conciliado"})
        base_.loc[tem, "status"] = novo[tem]
        conc = base_["status"] == "conciliado"
        base_.loc[conc, "final_un"] = base_.loc[conc, "rec_final"]
        base_ = base_.drop(columns="rec_final")
    else:
        for c_ in ("rec_id", "rec_status", "rec_un", "escolha"):
            base_[c_] = None
    return base_[cols].sort_values(chave).reset_index(drop=True)


def painel_areas(conc: pd.DataFrame, operacao_id: int) -> pd.DataFrame:
    """Uma linha por área: endereços, itens, bateu, divergentes, em recontagem, acerto 1ª × 2ª."""
    if conc.empty:
        return pd.DataFrame(columns=["area", "nome", "armazem", "enderecos", "itens", "ok", "divergente", "pendente",
                                     "recontado", "conciliado", "aguardando", "sem_conversao", "acerto"])
    p = pd.crosstab(conc["area"], conc["status"])
    for s in STATUS:
        if s not in p:
            p[s] = 0
    p = p.reset_index()
    e = conc.groupby("area").agg(enderecos=("endereco", "nunique"), itens=("produto", "size"))
    p = p.merge(e.reset_index(), on="area")
    a = areas(operacao_id)
    nomes = dict(zip(a["codigo"], a["nome"])) if not a.empty else {}
    arm = dict(zip(a["codigo"], a["armazem"])) if not a.empty else {}
    ordem = dict(zip(a["codigo"], a["ordem"])) if not a.empty else {}
    p["nome"] = p["area"].map(nomes).fillna(p["area"].map(_nome_area))
    p["armazem"] = p["area"].map(arm).fillna("— sem armazém")
    comparados = p["itens"] - p["aguardando"] - p["sem_conversao"]
    p["acerto"] = (p["ok"] / comparados * 100).where(comparados > 0)
    p["_o"] = p["area"].map(ordem).fillna(0)
    return p.sort_values(["armazem", "_o", "area"]).drop(columns="_o").reset_index(drop=True)


def resultado(inv_id: int, conc: pd.DataFrame | None = None) -> pd.DataFrame:
    """Por produto: sistema (02.05.02 disponível) × contado (soma das quantidades finais dos endereços)."""
    conc = conciliacao(inv_id) if conc is None else conc
    b = base(inv_id)
    if conc.empty:
        cont = pd.DataFrame(columns=["produto", "descricao_c", "contado_un", "pendentes", "enderecos"])
    else:
        x = conc.assign(pend=conc["final_un"].isna())
        cont = x.groupby("produto", as_index=False).agg(
            descricao_c=("descricao", "first"), contado_un=("final_un", "sum"), pendentes=("pend", "sum"),
            enderecos=("endereco", "nunique"))
    r = b.merge(cont, on="produto", how="outer")
    r["descricao"] = r["descricao"].fillna(r.pop("descricao_c")) if "descricao_c" in r else r["descricao"]
    conv = conversoes(inv_id, r["produto"].unique().tolist()).set_index("produto")["un_cx_f"]
    r["fator"] = r["fator"].fillna(r["produto"].map(conv)).fillna(1.0)
    for c in ("sistema_un", "contado_un", "pendentes", "enderecos"):
        r[c] = pd.to_numeric(r[c], errors="coerce").fillna(0.0)
    r["dif_un"] = r["contado_un"] - r["sistema_un"]
    r["dif_cx"] = r["dif_un"] / r["fator"]
    r["situacao"] = ["⏳ pendente" if p_ else ("✅ ok" if abs(d) <= TOLERANCIA_UN else ("🔺 sobra" if d > 0 else
                                                                                      "🔻 falta"))
                     for p_, d in zip(r["pendentes"], r["dif_un"])]
    r = r[(r["sistema_un"] != 0) | (r["contado_un"] != 0) | (r["pendentes"] > 0)]
    return r.sort_values("dif_cx", key=lambda s: -s.abs()).reset_index(drop=True)


# --- recontagem (gestão → app → gestão) ----------------------------------------------------------------------------
def enviar_recontagem(inv_id: int, itens: pd.DataFrame, usuario: str = "") -> int:
    inv = _aberto(inv_id)
    n = 0
    with get_conn() as conn:
        for r in itens.itertuples(index=False):
            end = r.endereco or ""
            conn.execute("DELETE FROM inv_recontagem WHERE inv_id = ? AND area = ? AND COALESCE(endereco, '') = ? AND "
                         "produto = ? AND status <> 'conciliado'", (int(inv_id), r.area, end, r.produto))
            if conn.execute("SELECT 1 FROM inv_recontagem WHERE inv_id = ? AND area = ? AND COALESCE(endereco, '') = ? "
                            "AND produto = ?", (int(inv_id), r.area, end, r.produto)).fetchone():
                continue
            conn.execute("INSERT INTO inv_recontagem (inv_id, operacao_id, area, endereco, produto, descricao, c1_un, "
                         "c2_un, fator, status, enviado_por, enviado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "
                         "'pendente', ?, ?)",
                         (int(inv_id), int(inv["operacao_id"]), r.area, end, r.produto, r.descricao,
                          None if pd.isna(r.c1_un) else float(r.c1_un), None if pd.isna(r.c2_un) else float(r.c2_un),
                          float(r.fator or 1), usuario, agora()))
            n += 1
    return n


def cancelar_recontagem(rec_ids: list[int]) -> None:
    with get_conn() as conn:
        for i in rec_ids:
            conn.execute("DELETE FROM inv_recontagem WHERE id = ? AND status <> 'conciliado'", (int(i),))


def recontagens(inv_id: int) -> pd.DataFrame:
    df = query_df("SELECT * FROM inv_recontagem WHERE inv_id = ? ORDER BY area, endereco, produto", (int(inv_id),))
    if not df.empty:
        df["endereco"] = df["endereco"].fillna("")
        df["sugestao"] = [_sugestao(q, c1, c2) for q, c1, c2 in zip(df["qtd_un"], df["c1_un"], df["c2_un"])]
    return df


def _sugestao(q, c1, c2) -> str:
    if q is None or pd.isna(q):
        return ""
    if c1 is not None and not pd.isna(c1) and abs(q - c1) <= TOLERANCIA_UN:
        return "c1"
    if c2 is not None and not pd.isna(c2) and abs(q - c2) <= TOLERANCIA_UN:
        return "c2"
    return "rec"


def conciliar(escolhas: dict[int, str], usuario: str = "") -> int:
    """escolhas: {rec_id: 'c1' | 'c2' | 'rec'} — a quantidade final do endereço passa a ser a escolhida."""
    n = 0
    with get_conn() as conn:
        for rid, esc in escolhas.items():
            r = conn.execute("SELECT c1_un, c2_un, qtd_un, status FROM inv_recontagem WHERE id = ?",
                             (int(rid),)).fetchone()
            if not r or esc not in ESCOLHAS:
                continue
            c1, c2, q, stt = r[0], r[1], r[2], r[3]
            if stt not in ("recontado", "contado", "conciliado"):
                continue
            final = {"c1": c1, "c2": c2, "rec": q}[esc]
            if final is None:
                continue
            conn.execute("UPDATE inv_recontagem SET escolha = ?, final_un = ?, status = 'conciliado', "
                         "conciliado_por = ?, conciliado_em = ? WHERE id = ?", (esc, float(final), usuario, agora(),
                                                                              int(rid)))
            n += 1
    return n


def desfazer_conciliacao(rec_id: int) -> None:
    execute("UPDATE inv_recontagem SET status = 'recontado', escolha = NULL, final_un = NULL, conciliado_por = NULL, "
            "conciliado_em = NULL WHERE id = ?", (int(rec_id),))


# --- app de recontagem -------------------------------------------------------------------------------------------------
def app_pendentes(operacao_id: int) -> pd.DataFrame:
    """Itens a recontar nos inventários abertos (pendente = falta contar; contado = falta a descarga)."""
    trecho, p = operacoes_repo.filtro("r.operacao_id", operacao_id)
    df = query_df(f"""SELECT r.*, i.nome AS inventario, i.mes FROM inv_recontagem r
                      JOIN inv_inventarios i ON i.id = r.inv_id
                      WHERE {trecho} AND i.status = 'aberto' AND r.status IN ('pendente', 'contado')
                      ORDER BY r.area, r.endereco, r.produto""", p)
    if not df.empty:
        df["endereco"] = df["endereco"].fillna("")
        a = areas(operacao_id)
        nomes = dict(zip(a["codigo"], a["nome"])) if not a.empty else {}
        arm = dict(zip(a["codigo"], a["armazem"])) if not a.empty else {}
        df["area_nome"] = df["area"].map(nomes).fillna(df["area"].map(_nome_area))
        df["armazem"] = df["area"].map(arm).fillna("")
    return df


def registrar_app(rec_id: int, caixas: float, unidades: float, usuario: str = "") -> None:
    r = query_one("SELECT fator, status FROM inv_recontagem WHERE id = ?", (int(rec_id),))
    if not r:
        raise RegraNegocioError("Item não encontrado.")
    if r["status"] not in ("pendente", "contado"):
        raise RegraNegocioError("Este item já foi descarregado.")
    if (caixas or 0) < 0 or (unidades or 0) < 0:
        raise RegraNegocioError("Quantidade não pode ser negativa.")
    total = float(caixas or 0) * float(r["fator"] or 1) + float(unidades or 0)
    execute("UPDATE inv_recontagem SET qtd_un = ?, status = 'contado', contado_por = ?, contado_em = ? WHERE id = ?",
            (total, usuario, agora(), int(rec_id)))


def descarga(operacao_id: int, area: str, usuario: dict) -> int:
    """Finaliza a recontagem da área: os itens contados vão para a gestão conciliar e os responsáveis são avisados."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    falta = query_df(f"SELECT COUNT(*) AS n FROM inv_recontagem WHERE {trecho} AND area = ? AND status = 'pendente'",
                     (*p, area))
    if int(falta["n"].iloc[0] or 0):
        raise RegraNegocioError("Ainda tem endereço sem contar nesta área.")
    ids = query_df(f"SELECT id, inv_id FROM inv_recontagem WHERE {trecho} AND area = ? AND status = 'contado'",
                   (*p, area))
    if ids.empty:
        raise RegraNegocioError("Nada para descarregar nesta área.")
    with get_conn() as conn:
        for i in ids["id"]:
            conn.execute("UPDATE inv_recontagem SET status = 'recontado', descarga_em = ? WHERE id = ?",
                         (agora(), int(i)))
    _avisar_descarga(operacao_id, area, len(ids), usuario)
    return len(ids)


def _avisar_descarga(operacao_id: int, area: str, n: int, usuario: dict) -> None:
    try:
        from repositories import motoristas_repo

        filial = (operacoes_repo.buscar(operacao_id) or {}).get("nome", "")
        nome = _nome_area(area)
        for uid in responsaveis(operacao_id):
            motoristas_repo.criar_notificacao(
                uid, "inventario", f"inv_desc:{operacao_id}:{area}:{agora()}:{uid}",
                f"📥 Descarga da recontagem — {nome}",
                f"{usuario.get('nome', '')} terminou a recontagem de {n} item(ns) da área {nome} ({filial}). "
                "Concilie em Armazém › 🎯 Acuracidade › Inventário mensal › 🔁 Recontagem.", "armazem",
                agora())
    except Exception:  # noqa: BLE001 — o aviso nunca impede a descarga
        pass
