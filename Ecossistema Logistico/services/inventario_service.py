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
    "nao_bateu": "🔁 Não bateu — nova recontagem",
    "conciliado": "✔️ Conciliado",
    "sem_conversao": "❔ Sem conversão",
}
REC_STATUS = {"pendente": "📨 Aguardando recontagem", "contado": "✍️ Contado (falta descarga)",
              "recontado": "📥 Descarga feita — conciliar", "conciliado": "✔️ Conciliado",
              "superado": "↪️ Substituída por nova recontagem"}
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
    df["un_cx_f"] = df["un_cx_m"].fillna(df["un_cx"].where(df["un_cx"] > 0)).fillna(df["fator_b"]).fillna(1.0)
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


_CHAVES_0111 = {"cod": (["cod", "codigo", "cod_produto", "codigo_produto", "sku", "produto"], []),
                "un_cx": (["un_cx", "unid_cx", "unidades_cx", "unidades_caixa", "qtd_unidades", "qtde_unidades",
                           "unidades_por_caixa", "qtd_embalagem", "embalagem", "fator_conversao", "multiplo"],
                          ["unidades_por", "unid_por", "un_por", "qtd_unid", "qtde_unid", "unid_cx", "embalag",
                           "multiplo"]),
                "cx_pallet": (["cx_pallet", "caixas_pallet", "caixas_palete", "cx_palete", "qtd_pallet",
                               "qtde_pallet", "pallet", "palete", "palet"], ["pallet", "palete", "palet", "plt"]),
                "cx_lastro": (["cx_lastro", "caixas_lastro", "qtd_lastro", "qtde_lastro", "lastro", "camada"],
                              ["lastro", "camada"])}


def ler_0111(conteudo: bytes, nome: str) -> tuple[pd.DataFrame, dict]:
    """Lê a 01.11 e sugere as colunas de código, unidades/caixa, caixas/palete e caixas/lastro."""
    from services import importacao_service as imp

    try:
        df = imp.ler_arquivo(nome, conteudo, "produtos")
    except Exception as e:  # noqa: BLE001
        raise RegraNegocioError(f"Não consegui ler a 01.11: {e}") from e
    norm = {c: imp._norm(c) for c in df.columns}
    mapa, usadas = {}, set()
    for campo, (exatos, contem) in _CHAVES_0111.items():
        col = next((c for c, n in norm.items() if n in exatos and c not in usadas), None)
        if col is None:
            col = next((c for c, n in norm.items() if any(k in n for k in contem) and c not in usadas
                        and "desc" not in n), None)
        mapa[campo] = col
        if col:
            usadas.add(col)
    if not mapa["cod"] and len(df.columns):
        mapa["cod"] = df.columns[0]
    return df, mapa


def importar_conversoes_0111(df: pd.DataFrame, mapa: dict, usuario: str = "") -> dict:
    """Grava na base de produtos (01.11) as unidades/caixa, caixas/palete e caixas/lastro das colunas escolhidas."""
    from services import importacao_service as imp

    if not mapa.get("cod"):
        raise RegraNegocioError("Escolha a coluna do código do produto.")
    campos = [c for c in ("un_cx", "cx_pallet", "cx_lastro") if mapa.get(c)]
    if not campos:
        raise RegraNegocioError("Escolha pelo menos uma coluna: unidades por caixa, caixas por palete ou por lastro.")
    cod = imp._to_int(df[mapa["cod"]])
    vals = {c: pd.to_numeric(imp._to_float(df[mapa[c]]), errors="coerce") for c in campos}
    n = 0
    with get_conn() as conn:
        exist = {int(r[0]) for r in conn.execute("SELECT cod FROM produtos").fetchall()}
        for i in df.index:
            if pd.isna(cod[i]) or int(cod[i]) <= 0:
                continue
            c = int(cod[i])
            atual = {k: (float(vals[k][i]) if pd.notna(vals[k][i]) and vals[k][i] > 0 else None) for k in campos}
            if not any(v is not None for v in atual.values()):
                continue
            if c in exist:
                sets = [k for k, v in atual.items() if v is not None]
                conn.execute(f"UPDATE produtos SET {', '.join(k + ' = ?' for k in sets)} WHERE cod = ?",
                             (*[atual[k] for k in sets], c))
            else:
                conn.execute(f"INSERT INTO produtos (cod, {', '.join(campos)}) VALUES (?, {', '.join('?' * len(campos))})",
                             (c, *[atual[k] for k in campos]))
                exist.add(c)
            n += 1
    with get_conn() as conn:  # lembra o de/para para a próxima vez
        conn.execute("DELETE FROM inv_config WHERE operacao_id = 0 AND chave = 'map0111'")
        conn.execute("INSERT INTO inv_config (operacao_id, chave, valor) VALUES (0, 'map0111', ?)",
                     ("|".join(f"{k}={v or ''}" for k, v in mapa.items()),))
    return {"produtos": n, "campos": campos}


def mapa_0111_salvo() -> dict:
    r = query_one("SELECT valor FROM inv_config WHERE operacao_id = 0 AND chave = 'map0111'")
    return dict(x.split("=", 1) for x in str((r or {}).get("valor") or "").split("|") if "=" in x)


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
def inventarios(operacao_id: int, tipo: str = "mensal") -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT * FROM inv_inventarios WHERE {trecho} AND COALESCE(tipo, 'mensal') = ? "
                    f"ORDER BY COALESCE(data, mes) DESC, id DESC", (*p, tipo))


def inventario(inv_id: int) -> dict | None:
    return query_one("SELECT * FROM inv_inventarios WHERE id = ?", (int(inv_id),))


def criar(operacao_id: int, mes: str, nome: str, usuario: str = "", tipo: str = "mensal",
          data: str | None = None) -> int:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para abrir o inventário.")
    if tipo == "diario":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data or "")):
            raise RegraNegocioError("Escolha o dia da contagem.")
        mes = data[:7]
        nome = (nome or "").strip() or f"Contagem {data[8:10]}/{data[5:7]}/{data[:4]}"
    else:
        if not re.fullmatch(r"\d{4}-\d{2}", str(mes or "")):
            raise RegraNegocioError("Escolha o mês do inventário.")
        nome = (nome or "").strip() or f"Inventário {mes[5:]}/{mes[:4]}"
    return execute("INSERT INTO inv_inventarios (operacao_id, mes, nome, status, criado_por, criado_em, tipo, data) "
                   "VALUES (?, ?, ?, 'aberto', ?, ?, ?, ?)", (operacao_id, mes, nome, usuario, agora(), tipo, data))


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


def importar_contagem(inv_id: int, conteudo: bytes, nome: str, usuario: str = "", area: str | None = None) -> dict:
    """Grava as contagens do WMS. Sobe de novo a mesma contagem (área × usuário × finalização) → substitui.
    Com `area`, grava só as linhas dessa área (coluna C) — para subir área por área."""
    inv = _aberto(inv_id)
    df = ler_contagem(conteudo)
    if df.empty:
        raise RegraNegocioError("Nenhuma contagem no arquivo.")
    outras = 0
    if area:
        alvo = _norm(area)
        no_arq = sorted(df["area"].unique())
        df_a = df[df["area"].map(_norm) == alvo]
        if df_a.empty:
            raise RegraNegocioError(f"O arquivo não tem contagem da área “{_nome_area(area)}”. Áreas no arquivo: "
                                    + ", ".join(_nome_area(a) for a in no_arq[:8]) + ("…" if len(no_arq) > 8 else "")
                                    + ". Escolha a área certa ou suba como “Todas as áreas”.")
        outras = len(df) - len(df_a)
        df = df_a.assign(area=area)
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
            "enderecos": int(df["endereco"].nunique()), "itens": int(df["produto"].nunique()), "outras": outras}


def situacao_areas(inv_id: int, operacao_id: int) -> pd.DataFrame:
    """Áreas cadastradas + as que já têm contagem, com quantas contagens (usuários) cada uma já tem."""
    a = areas(operacao_id)
    rc = resumo_contagens(inv_id)
    cods = list(dict.fromkeys((a["codigo"].tolist() if not a.empty else []) +
                              (rc["area"].tolist() if not rc.empty else [])))
    nomes = dict(zip(a["codigo"], a["nome"])) if not a.empty else {}
    linhas = []
    for c in cods:
        x = rc[rc["area"] == c] if not rc.empty else rc
        linhas.append({"area": c, "nome": nomes.get(c) or _nome_area(c), "contagens": len(x),
                       "usuarios": ", ".join(x["usuario"]) if len(x) else ""})
    return pd.DataFrame(linhas, columns=["area", "nome", "contagens", "usuarios"])


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
            "rec_id", "rec_status", "rec_un", "escolha", "unidades", "sem_conv", "t1", "t2", "dif_txt", "orig",
            "rodadas"]
    if c.empty:
        return pd.DataFrame(columns=cols)
    # cada contagem = usuário × finalização (o mesmo usuário pode fazer a 1ª e a 2ª). A ordem é POR ENDEREÇO:
    # a 1ª contagem do endereço é a que terminou primeiro, a 2ª a seguinte.
    c["finalizacao"] = c["finalizacao"].fillna(c["inicio"]).fillna("")
    sess = (c.groupby(["area", "endereco", "usuario", "finalizacao"], as_index=False).size()
             .sort_values(["area", "endereco", "finalizacao", "usuario"]))
    sess["n"] = sess.groupby(["area", "endereco"]).cumcount() + 1
    c = c.merge(sess[["area", "endereco", "usuario", "finalizacao", "n"]],
                on=["area", "endereco", "usuario", "finalizacao"], how="left")
    c = c[c["n"] <= 2]
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
    # quantidade como foi contada (ex.: "2 PL + 5 CX") — compara direto quando as unidades são as mesmas
    cru = c.groupby(chave + ["n", "unidade"], as_index=False)["qtd"].sum()
    cru["unidade"] = cru["unidade"].fillna("").astype(str).str.upper().str.strip()
    cru = cru[cru["qtd"] != 0]
    txt = cru.groupby(chave + ["n"]).apply(
        lambda d: " + ".join(f"{_fmt_q(q)} {u}" for u, q in sorted(zip(d["unidade"], d["qtd"]))),
        include_groups=False)
    raw = cru.groupby(chave + ["n"]).apply(lambda d: dict(zip(d["unidade"], d["qtd"])), include_groups=False)
    base_["t1"] = [txt.get((a, e, p_, 1), "") for a, e, p_ in zip(base_["area"], base_["endereco"], base_["produto"])]
    base_["t2"] = [txt.get((a, e, p_, 2), "") for a, e, p_ in zip(base_["area"], base_["endereco"], base_["produto"])]
    base_["_r1"] = [raw.get((a, e, p_, 1), {}) for a, e, p_ in zip(base_["area"], base_["endereco"], base_["produto"])]
    base_["_r2"] = [raw.get((a, e, p_, 2), {}) for a, e, p_ in zip(base_["area"], base_["endereco"], base_["produto"])]
    quem = sess[sess["n"] <= 2].pivot_table(index=["area", "endereco"], columns="n", values="usuario",
                                            aggfunc="first")
    quem = quem.rename(columns={1: "u1", 2: "u2"}).reset_index()
    for col in ("u1", "u2"):
        if col not in quem:
            quem[col] = None
    base_ = base_.merge(quem[["area", "endereco", "u1", "u2"]], on=["area", "endereco"], how="left")
    # endereço contado pelas duas contagens: quem não achou o produto contou ZERO
    tem2 = base_["u2"].notna()
    sem_c = c.groupby(chave + ["n"])["qtd_un"].apply(lambda s: s.isna().any())
    base_["sem_conv"] = [bool(sem_c.get((a, e, p_, 1), False) or sem_c.get((a, e, p_, 2), False))
                         for a, e, p_ in zip(base_["area"], base_["endereco"], base_["produto"])]
    base_["t1"] = base_["t1"].replace("", "0")
    base_["t2"] = [("0" if t == "" else t) if t2_ else t for t, t2_ in zip(base_["t2"], tem2)]
    base_["dif_txt"] = [_dif_cru(r1, r2) if t2_ else "" for r1, r2, t2_ in zip(base_["_r1"], base_["_r2"], tem2)]
    base_["c1_un"] = base_["c1_un"].where(base_["c1_un"].notna() | base_["sem_conv"], 0.0)
    base_["c2_un"] = pd.to_numeric(base_["c2_un"], errors="coerce").astype(float)
    base_["c2_un"] = base_["c2_un"].where(~tem2 | base_["c2_un"].notna() | base_["sem_conv"], 0.0)
    conv = conversoes(inv_id, base_["produto"].unique().tolist()).set_index("produto")["un_cx_f"]
    base_["fator"] = base_["produto"].map(conv).fillna(1.0)
    st_ = []
    for a, c1, c2, t2, sc, r1, r2 in zip(base_["area"], base_["c1_un"], base_["c2_un"], tem2, base_["sem_conv"],
                                         base_["_r1"], base_["_r2"]):
        if not t2:
            st_.append("aguardando")
        elif sc:  # sem conversão: compara do jeito que foi contado (mesma unidade)
            st_.append("ok" if _iguais(r1, r2) else "divergente")
        elif abs(float(c1) - float(c2)) <= TOLERANCIA_UN:
            st_.append("ok")
        else:
            st_.append("divergente")
    base_["status"] = st_
    base_["final_un"] = [c1 if s in ("ok", "aguardando") and not sc else None
                         for s, c1, sc in zip(base_["status"], base_["c1_un"], base_["sem_conv"])]
    base_ = base_.drop(columns=["_r1", "_r2"])
    base_["orig"] = base_["status"]  # resultado da 1ª × 2ª contagem (fica como foi, mesmo depois da recontagem)
    rec = query_df("SELECT id AS rec_id, area, endereco, produto, status AS rec_status, qtd_un AS rec_un, escolha, "
                   "final_un AS rec_final, COALESCE(rodada, 1) AS rodada FROM inv_recontagem WHERE inv_id = ?",
                   (int(inv_id),))
    base_["rodadas"] = 0
    if not rec.empty:
        rec["endereco"] = rec["endereco"].fillna("")
        rec["rodada"] = pd.to_numeric(rec["rodada"], errors="coerce").fillna(1).astype(int)
        rec["rec_un"] = pd.to_numeric(rec["rec_un"], errors="coerce")
        # cada rodada de recontagem vira uma coluna (r1_un, r2_un…); o status vem da última rodada
        piv = rec.pivot_table(index=chave, columns="rodada", values="rec_un", aggfunc="last")
        piv.columns = [f"r{int(k)}_un" for k in piv.columns]
        rec = _marcar_bateu(rec).drop(columns=["c1_un", "c2_un", "bateu"], errors="ignore")
        ult = rec.sort_values("rodada").groupby(chave, as_index=False).tail(1)
        ult = ult.assign(rodadas=ult["rodada"]).drop(columns="rodada")
        base_ = base_.drop(columns="rodadas").merge(ult, on=chave, how="left").merge(
            piv.reset_index(), on=chave, how="left")
        base_["rodadas"] = pd.to_numeric(base_["rodadas"], errors="coerce").fillna(0).astype(int)
        tem = base_["rec_id"].notna() & base_["status"].isin(["divergente", "ok", "aguardando"])
        novo = base_["rec_status"].map({"pendente": "pendente", "contado": "pendente", "recontado": "recontado",
                                        "conciliado": "conciliado", "nao_bateu": "nao_bateu"})
        base_["status"] = novo.where(tem, base_["status"])
        conc = base_["status"] == "conciliado"
        # pandas 3 não aceita gravar coluna "object" (None) dentro de coluna numérica: converte antes
        base_["final_un"] = pd.to_numeric(base_["final_un"], errors="coerce").astype(float)
        rf = pd.to_numeric(base_["rec_final"], errors="coerce").astype(float)
        base_["final_un"] = rf.where(conc, base_["final_un"])
        for c_ in ("rec_un", "rec_id"):
            base_[c_] = pd.to_numeric(base_[c_], errors="coerce")
        base_ = base_.drop(columns="rec_final")
        cols = cols + sorted([c_ for c_ in base_.columns if re.fullmatch(r"r\d+_un", c_)],
                             key=lambda x: int(x[1:-3]))
    else:
        for c_ in ("rec_id", "rec_status", "rec_un", "escolha"):
            base_[c_] = None
    return base_[cols].sort_values(chave).reset_index(drop=True)


END_STATUS = {"validado": "✅ Validado", "divergente": "⚠️ Divergente", "recontagem": "📨 Em recontagem",
              "conciliar": "📥 Conciliar", "aguardando": "⏳ Só 1 contagem", "sem_conversao": "❔ Sem conversão"}


def por_endereco(conc: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por área × endereço: quem fez a 1ª e a 2ª contagem, itens, quantos bateram e a situação."""
    cols = ["area", "endereco", "u1", "u2", "itens", "ok", "divergente", "situacao"]
    if conc.empty:
        return pd.DataFrame(columns=cols)
    x = conc.assign(ok_=conc["status"].isin(["ok", "conciliado"]), div_=conc["status"] == "divergente",
                    pend_=conc["status"] == "pendente", rec_=conc["status"].isin(["recontado", "nao_bateu"]),
                    ag_=conc["status"] == "aguardando", sc_=conc["status"] == "sem_conversao")
    e = x.groupby(["area", "endereco"], as_index=False).agg(
        u1=("u1", "first"), u2=("u2", "first"), itens=("produto", "size"), ok=("ok_", "sum"),
        divergente=("div_", "sum"), pend=("pend_", "sum"), rec=("rec_", "sum"), ag=("ag_", "sum"), sc=("sc_", "sum"))
    e["situacao"] = ["divergente" if d else "conciliar" if r_ else "recontagem" if p_ else "aguardando" if a_
                     else "sem_conversao" if s_ else "validado"
                     for d, r_, p_, a_, s_ in zip(e["divergente"], e["rec"], e["pend"], e["ag"], e["sc"])]
    return e[cols]


def _fmt_q(q) -> str:
    q = float(q)
    return f"{q:,.0f}".replace(",", ".") if q.is_integer() else f"{q:,.2f}".replace(",", "X").replace(".", ",").replace(
        "X", ".")


def _iguais(r1: dict, r2: dict) -> bool:
    us = set(r1) | set(r2)
    return all(abs(float(r1.get(u, 0)) - float(r2.get(u, 0))) < 1e-9 for u in us)


def _dif_cru(r1: dict, r2: dict) -> str:
    """Diferença 2ª − 1ª do jeito que foi contado (por unidade): ex. "+2 CX", "−1 PL + 3 CX"."""
    partes = []
    for u in sorted(set(r1) | set(r2)):
        d = float(r2.get(u, 0)) - float(r1.get(u, 0))
        if abs(d) > 1e-9:
            partes.append(("+" if d > 0 else "−") + f"{_fmt_q(abs(d))} {u}")
    return " ".join(partes) if partes else "0"


def painel_areas(conc: pd.DataFrame, operacao_id: int) -> pd.DataFrame:
    """Uma linha por área: endereços, itens, bateu, divergentes, em recontagem, acerto 1ª × 2ª."""
    if conc.empty:
        return pd.DataFrame(columns=["area", "nome", "armazem", "enderecos", "itens", "ok", "divergente", "pendente",
                                     "recontado", "conciliado", "aguardando", "sem_conversao", "acerto", "end_validados"])
    p = pd.crosstab(conc["area"], conc["status"])
    for s in STATUS:
        if s not in p:
            p[s] = 0
    p = p.reset_index()
    e = conc.groupby("area").agg(enderecos=("endereco", "nunique"), itens=("produto", "size"))
    p = p.merge(e.reset_index(), on="area")
    pe = por_endereco(conc)
    ev = pe.assign(v=pe["situacao"] == "validado").groupby("area")["v"].sum()
    p["end_validados"] = p["area"].map(ev).fillna(0).astype(int)
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
        cont = pd.DataFrame(columns=["produto", "descricao_c", "contado_un", "pendentes", "enderecos", "sem_conv"])
    else:
        x = conc.assign(pend=conc["final_un"].isna() & ~conc["sem_conv"].fillna(False).astype(bool),
                        sc=conc["sem_conv"].fillna(False).astype(bool))
        cont = x.groupby("produto", as_index=False).agg(
            descricao_c=("descricao", "first"), contado_un=("final_un", "sum"), pendentes=("pend", "sum"),
            sem_conv=("sc", "sum"),
            enderecos=("endereco", "nunique"))
    r = b.merge(cont, on="produto", how="outer")
    r["descricao"] = r["descricao"].fillna(r.pop("descricao_c")) if "descricao_c" in r else r["descricao"]
    conv = conversoes(inv_id, r["produto"].unique().tolist()).set_index("produto")["un_cx_f"]
    r["fator"] = r["fator"].fillna(r["produto"].map(conv)).fillna(1.0)
    for c in ("sistema_un", "contado_un", "pendentes", "enderecos", "sem_conv"):
        r[c] = pd.to_numeric(r[c], errors="coerce").fillna(0.0)
    r["dif_un"] = r["contado_un"] - r["sistema_un"]
    r["dif_cx"] = r["dif_un"] / r["fator"]
    r["situacao"] = ["❔ sem conversão" if sc else "⏳ pendente" if p_ else ("✅ ok" if abs(d) <= TOLERANCIA_UN else ("🔺 sobra" if d > 0 else
                                                                                      "🔻 falta"))
                     for sc, p_, d in zip(r["sem_conv"], r["pendentes"], r["dif_un"])]
    r = r[(r["sistema_un"] != 0) | (r["contado_un"] != 0) | (r["pendentes"] > 0) | (r["sem_conv"] > 0)]
    return r.sort_values("dif_cx", key=lambda s: -s.abs()).reset_index(drop=True)


# --- recontagem (gestão → app → gestão) ----------------------------------------------------------------------------
def enviar_recontagem(inv_id: int, itens: pd.DataFrame, usuario: str = "") -> int:
    """Manda para o app. Item que já foi recontado (conciliado) ganha uma nova rodada (recontagem 2, 3…); item com
    rodada ainda aberta (no app ou esperando conciliar) não é enviado de novo."""
    inv = _aberto(inv_id)
    n = 0
    with get_conn() as conn:
        for r in itens.itertuples(index=False):
            end = r.endereco or ""
            linhas = conn.execute("SELECT status, COALESCE(rodada, 1) FROM inv_recontagem WHERE inv_id = ? AND "
                                  "area = ? AND COALESCE(endereco, '') = ? AND produto = ?",
                                  (int(inv_id), r.area, end, r.produto)).fetchall()
            if any(x[0] not in ("conciliado", "superado") for x in linhas):
                continue
            rodada = max([int(x[1] or 1) for x in linhas], default=0) + 1
            conn.execute("INSERT INTO inv_recontagem (inv_id, operacao_id, area, endereco, produto, descricao, c1_un, "
                         "c2_un, fator, status, enviado_por, enviado_em, rodada) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "
                         "'pendente', ?, ?, ?)",
                         (int(inv_id), int(inv["operacao_id"]), r.area, end, r.produto, r.descricao,
                          None if pd.isna(r.c1_un) else float(r.c1_un), None if pd.isna(r.c2_un) else float(r.c2_un),
                          float(r.fator or 1), usuario, agora(), rodada))
            n += 1
    return n


def cancelar_recontagem(rec_ids: list[int]) -> None:
    with get_conn() as conn:
        for i in rec_ids:
            conn.execute("DELETE FROM inv_recontagem WHERE id = ? AND status <> 'conciliado'", (int(i),))


def _marcar_bateu(rec: pd.DataFrame) -> pd.DataFrame:
    """Na última rodada descarregada: 'bateu' se a recontagem é igual a alguma contagem anterior (1ª, 2ª ou outra
    recontagem); senão vira 'nao_bateu' (o gestor cria uma nova recontagem)."""
    rec = rec.copy()
    if "c1_un" not in rec:
        extra = query_df("SELECT id AS rec_id, c1_un, c2_un FROM inv_recontagem WHERE id IN (" +
                         ",".join(str(int(i)) for i in rec["rec_id"]) + ")") if len(rec) else pd.DataFrame(
            columns=["rec_id", "c1_un", "c2_un"])
        rec = rec.merge(extra, on="rec_id", how="left")
    rec["bateu"] = None
    for _, g in rec.groupby(["area", "endereco", "produto"]):
        g = g.sort_values("rodada")
        anteriores = [v for v in (g["c1_un"].iloc[0], g["c2_un"].iloc[0]) if v is not None and pd.notna(v)]
        for idx, r in g.iterrows():
            q = r["rec_un"]
            if r["rec_status"] in ("recontado", "conciliado", "superado") and q is not None and pd.notna(q):
                rec.at[idx, "bateu"] = any(abs(float(q) - float(v)) <= TOLERANCIA_UN for v in anteriores)
                anteriores.append(float(q))
    nb = (rec["rec_status"] == "recontado") & (rec["bateu"] == False)  # noqa: E712
    rec.loc[nb, "rec_status"] = "nao_bateu"
    return rec


def recontagens(inv_id: int) -> pd.DataFrame:
    df = query_df("SELECT * FROM inv_recontagem WHERE inv_id = ? ORDER BY area, endereco, produto, rodada",
                  (int(inv_id),))
    if not df.empty:
        df["endereco"] = df["endereco"].fillna("")
        df["rodada"] = pd.to_numeric(df["rodada"], errors="coerce").fillna(1).astype(int)
        df["qtd_un"] = pd.to_numeric(df["qtd_un"], errors="coerce")
        m = _marcar_bateu(df.rename(columns={"id": "rec_id", "status": "rec_status", "qtd_un": "rec_un"}))
        df["bateu"] = m["bateu"].values
        df["sit"] = m["rec_status"].values  # recontado → nao_bateu quando não bateu com nenhuma contagem
        # contagens anteriores do item (para a gestão ver tudo na frente)
        df["anteriores"] = ""
        for _, g in df.groupby(["area", "endereco", "produto"]):
            g = g.sort_values("rodada")
            for k, (idx, r) in enumerate(g.iterrows()):
                df.at[idx, "anteriores"] = ",".join(str(x) for x in g["qtd_un"].iloc[:k].tolist())
        df["sugestao"] = [_sugestao(q, c1, c2, b) for q, c1, c2, b in
                          zip(df["qtd_un"], df["c1_un"], df["c2_un"], df["bateu"])]
    return df


def _sugestao(q, c1, c2, bateu=None) -> str:
    if q is None or pd.isna(q):
        return ""
    if c1 is not None and not pd.isna(c1) and abs(q - c1) <= TOLERANCIA_UN:
        return "c1"
    if c2 is not None and not pd.isna(c2) and abs(q - c2) <= TOLERANCIA_UN:
        return "c2"
    return "rec"


def nova_recontagem(inv_id: int, rec_ids: list[int], usuario: str = "") -> int:
    """Para os itens que não bateram: encerra a rodada atual (fica guardada) e cria a próxima rodada no app."""
    _aberto(inv_id)
    df = query_df("SELECT * FROM inv_recontagem WHERE inv_id = ?", (int(inv_id),))
    df = df[df["id"].isin([int(i) for i in rec_ids])]
    if df.empty:
        raise RegraNegocioError("Selecione os itens para recontar.")
    with get_conn() as conn:
        for i in df["id"]:
            conn.execute("UPDATE inv_recontagem SET status = 'superado' WHERE id = ? AND status IN ('recontado', "
                         "'conciliado')", (int(i),))
    itens = df.rename(columns={})[["area", "endereco", "produto", "descricao", "c1_un", "c2_un", "fator"]]
    return enviar_recontagem(inv_id, itens, usuario)


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
        cv = conversoes(None, df["produto"].astype(str).unique().tolist()).set_index("produto")["cx_pallet_f"]
        df["cx_pallet"] = df["produto"].astype(str).map(cv)
    return df


def registrar_app(rec_id: int, caixas: float, unidades: float, usuario: str = "", paletes: float = 0) -> None:
    """Recontagem do app em paletes, caixas e unidades soltas (vira unidades). Pode editar até a descarga."""
    r = query_one("SELECT fator, status, produto FROM inv_recontagem WHERE id = ?", (int(rec_id),))
    if not r:
        raise RegraNegocioError("Item não encontrado.")
    if r["status"] not in ("pendente", "contado"):
        raise RegraNegocioError("Este item já foi descarregado — não dá mais para editar.")
    if min(paletes or 0, caixas or 0, unidades or 0) < 0:
        raise RegraNegocioError("Quantidade não pode ser negativa.")
    fator = float(r["fator"] or 1)
    cxp = 0.0
    if paletes:
        cv = conversoes(None, [str(r["produto"])])
        cxp = float(cv["cx_pallet_f"].iloc[0]) if not cv.empty and pd.notna(cv["cx_pallet_f"].iloc[0]) else 0.0
        if not cxp:
            raise RegraNegocioError("Este produto não tem caixas por palete na 01.11 — informe em caixas.")
    total = float(paletes or 0) * cxp * fator + float(caixas or 0) * fator + float(unidades or 0)
    execute("UPDATE inv_recontagem SET qtd_un = ?, pl = ?, cx = ?, un_s = ?, status = 'contado', contado_por = ?, "
            "contado_em = ? WHERE id = ?", (total, float(paletes or 0), float(caixas or 0), float(unidades or 0),
                                            usuario, agora(), int(rec_id)))


def finalizar(inv_id: int, usuario: str = "") -> dict:
    """Fecha o inventário e grava a base final (o que ficou de cada endereço)."""
    conc = conciliacao(inv_id)
    pend = int(conc["final_un"].isna().sum()) if not conc.empty else 0
    execute("UPDATE inv_inventarios SET status = 'fechado', finalizado_em = ?, finalizado_por = ? WHERE id = ?",
            (agora(), usuario, int(inv_id)))
    return {"itens": len(conc), "pendentes": pend}


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


# --- link do app por revenda e login dos conferentes ------------------------------------------------------------------
TOKEN_DIAS = 30


def link_token(operacao_id: int, criar: bool = True) -> str | None:
    import secrets

    r = query_one("SELECT valor FROM inv_config WHERE operacao_id = ? AND chave = 'link_app'", (int(operacao_id),))
    if r and r.get("valor"):
        return r["valor"]
    if not criar or operacoes_repo.e_consolidada(operacao_id):
        return None
    tok = secrets.token_urlsafe(12)
    with get_conn() as conn:
        conn.execute("INSERT INTO inv_config (operacao_id, chave, valor) VALUES (?, 'link_app', ?)",
                     (int(operacao_id), tok))
    return tok


def novo_link(operacao_id: int) -> str:
    """Gera outro link (o anterior para de funcionar)."""
    execute("DELETE FROM inv_config WHERE operacao_id = ? AND chave = 'link_app'", (int(operacao_id),))
    return link_token(operacao_id)


def op_por_link(token: str) -> int | None:
    if not token:
        return None
    r = query_one("SELECT operacao_id FROM inv_config WHERE chave = 'link_app' AND valor = ?", (str(token),))
    return int(r["operacao_id"]) if r else None


def _login(v) -> str:
    return re.sub(r"\s+", "", str(v or "")).lower()


def conferentes(operacao_id: int) -> pd.DataFrame:
    return query_df("SELECT id, nome, login, ativo, senha_hash IS NOT NULL AS tem_senha, criado_por, criado_em, "
                    "ultimo_acesso FROM inv_conferentes WHERE operacao_id = ? ORDER BY nome", (int(operacao_id),))


def salvar_conferente(operacao_id: int, nome: str, login: str, usuario: str = "", conf_id: int | None = None,
                      ativo: bool = True) -> int:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para cadastrar os conferentes.")
    nome, lg = (nome or "").strip(), _login(login)
    if not nome:
        raise RegraNegocioError("Informe o nome do conferente.")
    if len(lg) < 3:
        raise RegraNegocioError("Informe o login (CPF, matrícula ou apelido — mínimo 3 caracteres).")
    outro = query_one("SELECT id FROM inv_conferentes WHERE operacao_id = ? AND login = ?", (int(operacao_id), lg))
    if outro and int(outro["id"]) != int(conf_id or 0):
        raise RegraNegocioError("Já existe um conferente com esse login nesta revenda.")
    if conf_id:
        execute("UPDATE inv_conferentes SET nome = ?, login = ?, ativo = ? WHERE id = ?",
                (nome, lg, 1 if ativo else 0, int(conf_id)))
        return int(conf_id)
    return execute("INSERT INTO inv_conferentes (operacao_id, nome, login, ativo, criado_por, criado_em) "
                   "VALUES (?, ?, ?, 1, ?, ?)", (int(operacao_id), nome, lg, usuario, agora()))


def excluir_conferente(conf_id: int) -> None:
    execute("DELETE FROM inv_conferentes WHERE id = ?", (int(conf_id),))


def zerar_senha_conferente(conf_id: int) -> None:
    execute("UPDATE inv_conferentes SET senha_hash = NULL WHERE id = ?", (int(conf_id),))


def _conf(operacao_id: int, login: str) -> dict | None:
    return query_one("SELECT * FROM inv_conferentes WHERE operacao_id = ? AND login = ?",
                     (int(operacao_id), _login(login)))


def situacao_conferente(operacao_id: int, login: str) -> str:
    """'sem_cadastro' | 'bloqueado' | 'criar_senha' | 'ok'"""
    r = _conf(operacao_id, login)
    if not r:
        return "sem_cadastro"
    if not int(r["ativo"] or 0):
        return "bloqueado"
    return "criar_senha" if not r["senha_hash"] else "ok"


def _sessao_conf(r: dict) -> dict:
    return {"id": int(r["id"]), "nome": r["nome"], "login": r["login"], "operacao_id": int(r["operacao_id"]),
            "conferente": True}


def criar_senha_conferente(operacao_id: int, login: str, senha: str, confirmacao: str) -> dict:
    from core.auth import hash_senha

    r = _conf(operacao_id, login)
    if not r or not int(r["ativo"] or 0):
        raise RegraNegocioError("Login não liberado. Peça o acesso à gestão do armazém.")
    if r["senha_hash"]:
        raise RegraNegocioError("Este login já tem senha. Entre com ela (ou peça para zerar).")
    if len(senha or "") < 4:
        raise RegraNegocioError("A senha precisa ter pelo menos 4 caracteres.")
    if senha != confirmacao:
        raise RegraNegocioError("As senhas não conferem.")
    execute("UPDATE inv_conferentes SET senha_hash = ? WHERE id = ?", (hash_senha(senha), int(r["id"])))
    return entrar_conferente(operacao_id, login, senha)


def entrar_conferente(operacao_id: int, login: str, senha: str) -> dict:
    from core.auth import verificar_senha

    r = _conf(operacao_id, login)
    if not r or not r["senha_hash"] or not int(r["ativo"] or 0) or not verificar_senha(senha or "", r["senha_hash"]):
        raise RegraNegocioError("Login ou senha inválidos.")
    execute("UPDATE inv_conferentes SET ultimo_acesso = ? WHERE id = ?", (agora(), int(r["id"])))
    return _sessao_conf(r)


def _assinar_conf(cid: int, expira: int, senha_hash: str) -> str:
    import hashlib
    import hmac

    return hmac.new(senha_hash.encode(), f"conf.{cid}.{expira}".encode(), hashlib.sha256).hexdigest()[:32]


def token_conferente(conf: dict) -> str | None:
    import time

    r = query_one("SELECT senha_hash FROM inv_conferentes WHERE id = ?", (int(conf["id"]),))
    if not r or not r["senha_hash"]:
        return None
    expira = int(time.time()) + TOKEN_DIAS * 86400
    return f"{conf['id']}.{expira}.{_assinar_conf(int(conf['id']), expira, r['senha_hash'])}"


def conferente_por_token(token: str, operacao_id: int) -> dict | None:
    import hmac
    import time

    try:
        cid, expira, ass = str(token).split(".")
        cid, expira = int(cid), int(expira)
    except (ValueError, AttributeError):
        return None
    if expira < time.time():
        return None
    r = query_one("SELECT * FROM inv_conferentes WHERE id = ?", (cid,))
    if not r or int(r["operacao_id"]) != int(operacao_id) or not r["senha_hash"] or not int(r["ativo"] or 0) or \
            not hmac.compare_digest(_assinar_conf(cid, expira, r["senha_hash"]), ass):
        return None
    return _sessao_conf(r)


# --- 🔄 Conciliação diária: uma contagem × estoque da 02.05.02 --------------------------------------------------------
DIA_STATUS = {"ok": "✅ Bateu com o estoque", "ok_rec": "✅ Bateu na recontagem", "divergente": "❌ Diferença",
              "pendente": "📨 Em recontagem", "confirmado": "⚠️ Diferença confirmada (2 contagens iguais)",
              "sem_conversao": "❔ Sem conversão"}


def _contagem_dia(inv_id: int) -> pd.DataFrame:
    """Uma contagem por endereço × produto (se contaram duas vezes, vale a última)."""
    c = _contagens_un(inv_id)
    if c.empty:
        return pd.DataFrame(columns=["area", "endereco", "produto", "descricao", "qtd_un", "usuario", "unidades"])
    c["finalizacao"] = c["finalizacao"].fillna(c["inicio"]).fillna("")
    ult = c.groupby(["area", "endereco"])["finalizacao"].transform("max")
    c = c[c["finalizacao"] == ult]
    return (c.groupby(["area", "endereco", "produto"], as_index=False)
             .agg(descricao=("descricao", "first"), qtd_un=("qtd_un", lambda s: s.sum(min_count=len(s))),
                  usuario=("usuario", "first"), unidades=("unidade", lambda s: ", ".join(sorted(set(s))))))


def conciliacao_diaria(inv_id: int) -> pd.DataFrame:
    """Por produto: estoque (02.05.02) × contagem do dia (soma dos endereços) × cada recontagem."""
    cols = ["produto", "descricao", "fator", "sistema_un", "contado_un", "final_un", "dif_un", "status", "rodadas",
            "enderecos", "sem_conv"]
    cd = _contagem_dia(inv_id)
    if cd.empty:
        return pd.DataFrame(columns=cols)
    g = cd.groupby("produto", as_index=False).agg(
        descricao=("descricao", "first"), contado_un=("qtd_un", lambda s: s.sum(min_count=len(s))),
        enderecos=("endereco", lambda s: ", ".join(sorted(set(s)))))
    g["sem_conv"] = g["contado_un"].isna()
    b = base(inv_id)
    g = g.merge(b[["produto", "sistema_un", "fator"]], on="produto", how="left")
    conv = conversoes(inv_id, g["produto"].tolist()).set_index("produto")["un_cx_f"]
    g["fator"] = pd.to_numeric(g["fator"], errors="coerce").fillna(g["produto"].map(conv)).fillna(1.0)
    g["sistema_un"] = pd.to_numeric(g["sistema_un"], errors="coerce").fillna(0.0)
    rec = query_df("SELECT produto, COALESCE(rodada, 1) AS rodada, status, qtd_un FROM inv_recontagem WHERE inv_id = ?",
                   (int(inv_id),))
    g["rodadas"] = 0
    abertos = set()
    if not rec.empty:
        rec["rodada"] = pd.to_numeric(rec["rodada"], errors="coerce").fillna(1).astype(int)
        rec["qtd_un"] = pd.to_numeric(rec["qtd_un"], errors="coerce")
        aberto = rec["status"].isin(["pendente", "contado"])
        abertos = set(rec.loc[aberto, "produto"])
        tot = (rec[~aberto].groupby(["produto", "rodada"])["qtd_un"].sum(min_count=1).unstack())
        tot.columns = [f"r{int(k)}_un" for k in tot.columns]
        g = g.merge(tot.reset_index(), on="produto", how="left")
        g["rodadas"] = g["produto"].map(rec.groupby("produto")["rodada"].max()).fillna(0).astype(int)
    rcols = sorted([c for c in g.columns if re.fullmatch(r"r\d+_un", c)], key=lambda x: int(x[1:-3]))
    st_, final = [], []
    for _, r in g.iterrows():
        seq = [r["contado_un"]] + [r[c] for c in rcols if pd.notna(r[c])]
        ult = seq[-1]
        final.append(ult)
        if r["produto"] in abertos:
            st_.append("pendente")
        elif ult is None or pd.isna(ult):
            st_.append("sem_conversao")
        elif abs(float(ult) - float(r["sistema_un"])) <= TOLERANCIA_UN:
            st_.append("ok" if len(seq) == 1 else "ok_rec")
        elif len(seq) > 1 and any(pd.notna(v) and abs(float(ult) - float(v)) <= TOLERANCIA_UN for v in seq[:-1]):
            st_.append("confirmado")
        else:
            st_.append("divergente")
    g["status"] = st_
    g["final_un"] = pd.to_numeric(pd.Series(final, index=g.index), errors="coerce")
    g["dif_un"] = g["final_un"] - g["sistema_un"]
    return g[cols + rcols].sort_values("produto").reset_index(drop=True)


def enviar_recontagem_diaria(inv_id: int, produtos: list[str], usuario: str = "") -> int:
    """Manda os produtos para o app: uma linha por endereço onde foram contados (nova rodada para cada produto)."""
    inv = _aberto(inv_id)
    cd = _contagem_dia(inv_id)
    cd = cd[cd["produto"].isin([str(p) for p in produtos])]
    conv = conversoes(inv_id, cd["produto"].unique().tolist()).set_index("produto")["un_cx_f"]
    n = 0
    with get_conn() as conn:
        for prod, linhas in cd.groupby("produto"):
            ant = conn.execute("SELECT status, COALESCE(rodada, 1) FROM inv_recontagem WHERE inv_id = ? AND produto = ?",
                               (int(inv_id), prod)).fetchall()
            if any(x[0] in ("pendente", "contado") for x in ant):
                continue
            rodada = max([int(x[1] or 1) for x in ant], default=0) + 1
            conn.execute("UPDATE inv_recontagem SET status = 'superado' WHERE inv_id = ? AND produto = ? AND "
                         "status IN ('recontado', 'conciliado')", (int(inv_id), prod))
            for r in linhas.itertuples(index=False):
                conn.execute("INSERT INTO inv_recontagem (inv_id, operacao_id, area, endereco, produto, descricao, "
                             "c1_un, c2_un, fator, status, enviado_por, enviado_em, rodada) VALUES (?, ?, ?, ?, ?, ?, ?, "
                             "NULL, ?, 'pendente', ?, ?, ?)",
                             (int(inv_id), int(inv["operacao_id"]), r.area, r.endereco or "", prod, r.descricao,
                              None if pd.isna(r.qtd_un) else float(r.qtd_un), float(conv.get(prod, 1.0) or 1.0),
                              usuario, agora(), rodada))
            n += 1
    return n


def auto_primeira_recontagem(inv_id: int, usuario: str = "") -> int:
    """Diária: tudo que não bateu com o estoque e ainda não foi recontado vai direto para a 1ª recontagem."""
    d = conciliacao_diaria(inv_id)
    if d.empty:
        return 0
    alvo = d[(d["status"] == "divergente") & (d["rodadas"] == 0)]
    return enviar_recontagem_diaria(inv_id, alvo["produto"].tolist(), usuario) if len(alvo) else 0
