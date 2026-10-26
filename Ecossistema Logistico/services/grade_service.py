"""Armazém › ✅ Check de Grade — sobe o 02.05.02 do dia (sistema, depósito 1) e confere com a grade, que vem da
Grade Cora (coluna ENTRADA; o DISPONÍVEL fica para o DOI do Ressuprimento). Diferença acima do limite (padrão 5%) vira alerta para os gestores do controle e
entra no painel de itens errados."""
import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services.erros import RegraNegocioError



def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


# --- Configuração / controle -------------------------------------------------------------------------------------
def limite(operacao_id: int) -> float:
    r = query_one("SELECT limite_pct FROM grade_config WHERE operacao_id = ?", (int(operacao_id),))
    return float(r["limite_pct"]) if r and r["limite_pct"] is not None else 5.0


def salvar_limite(operacao_id: int, pct: float) -> None:
    execute("""INSERT INTO grade_config (operacao_id, limite_pct) VALUES (?, ?)
               ON CONFLICT(operacao_id) DO UPDATE SET limite_pct = excluded.limite_pct""",
            (int(operacao_id), float(pct)))


def controle(operacao_id: int) -> list[int]:
    df = query_df("SELECT usuario_id FROM grade_controle WHERE operacao_id = ?", (int(operacao_id),))
    return [int(x) for x in df["usuario_id"]]


def salvar_controle(operacao_id: int, ids: list[int]) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial para cadastrar o controle.")
    with get_conn() as conn:
        conn.execute("DELETE FROM grade_controle WHERE operacao_id = ?", (int(operacao_id),))
        conn.executemany("INSERT INTO grade_controle (operacao_id, usuario_id) VALUES (?, ?)",
                         [(int(operacao_id), int(i)) for i in ids])


# --- Sistema (02.05.02 do dia, depósito 1) × grade (02.03.04) ----------------------------------------------------
FONTE = "02.05.02 do dia (depósito 1) × Grade Cora (entrada)"


def sistema_020502(conteudo, nome: str, deposito: str = "1") -> pd.DataFrame:
    """Lê o 02.05.02 do dia (não grava nos saldos do mês): cod, descricao, sistema (caixas no depósito)."""
    from services import estoque_valor_service as ev

    df = ev.ler_020502(conteudo, nome)
    df = df[df["deposito"].astype(str).str.strip().str.lstrip("0") == str(deposito).lstrip("0")]
    if df.empty:
        raise RegraNegocioError(f"O 02.05.02 não tem itens no depósito {deposito}.")
    g = df.groupby("produto", as_index=False).agg(descricao=("descricao", "first"), sistema=("qtd_venda", "sum"))
    g = g.rename(columns={"produto": "cod"})
    g["cod"] = g["cod"].astype(str).str.lstrip("0")
    return g[g["sistema"].round(4) != 0].sort_values("descricao").reset_index(drop=True)


def grade_020304(operacao_id: int) -> tuple[pd.DataFrame, str | None]:
    """Grade = coluna ENTRADA da Grade Cora (última carregada): (cod, descricao, grade), data da carga.
    O DISPONÍVEL é usado no DOI. Base antiga sem a coluna Entrada: usa o disponível (e avisa na tela)."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT cod, MAX(descricao) AS descricao, SUM(entrada) AS entrada, SUM(disponivel) AS disponivel, "
                  f"MAX(dt_atualizacao) AS dt FROM estoque WHERE {trecho} GROUP BY cod", p)
    if df.empty:
        return pd.DataFrame(columns=["cod", "descricao", "grade"]), None
    dt_ = df["dt"].dropna().max() if "dt" in df else None
    df["cod"] = df["cod"].astype(str).str.replace(r"\.0$", "", regex=True).str.lstrip("0")
    ent = pd.to_numeric(df["entrada"], errors="coerce").fillna(0.0)
    usa_entrada = bool((ent != 0).any())
    df["grade"] = ent if usa_entrada else pd.to_numeric(df["disponivel"], errors="coerce").fillna(0.0)
    df.attrs["coluna"] = "entrada" if usa_entrada else "disponível (a grade carregada não tem Entrada)"
    return df.drop(columns=["dt", "entrada", "disponivel"]), dt_


def comparar(sist: pd.DataFrame, grade: pd.DataFrame, lim: float) -> pd.DataFrame:
    """Todos os produtos do depósito 1 (sistema) e da grade. Diferença = grade − sistema."""
    if "descricao" in grade:
        grade = grade.rename(columns={"descricao": "desc_grade"})
    df = sist.merge(grade, on="cod", how="outer")
    if "desc_grade" in df:
        df["descricao"] = df["descricao"].fillna(df["desc_grade"])
        df = df.drop(columns="desc_grade")
    df["sistema"] = df["sistema"].fillna(0.0)
    df["grade"] = df["grade"].fillna(0.0)
    df["descricao"] = df["descricao"].fillna("(sem descrição)")
    df["dif"] = df["grade"] - df["sistema"]
    base = df["sistema"].where(df["sistema"] != 0, df["grade"])
    df["dif_pct"] = (df["dif"] / base.abs().where(base != 0) * 100).fillna(0.0)
    df["divergente"] = df["dif_pct"].abs() > lim
    return df.sort_values("dif_pct", key=lambda s: -s.abs()).reset_index(drop=True)


def salvar_check(operacao_id: int, data: str, fonte: str, comp: pd.DataFrame, usuario: dict, obs: str = "") -> int:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial para conferir a grade.")
    if comp.empty:
        raise RegraNegocioError("Nada para conferir.")
    lim = limite(operacao_id)
    cid = execute("""INSERT INTO grade_checks (operacao_id, data, fonte, limite_pct, itens, divergentes, obs, criado_por,
                                               criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (int(operacao_id), data, fonte, lim, len(comp), int(comp["divergente"].sum()), obs or None,
                   usuario.get("nome"), agora()))
    with get_conn() as conn:
        conn.executemany("""INSERT INTO grade_check_itens (check_id, cod, descricao, sistema, grade, dif, dif_pct,
                            divergente) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                         [(cid, r.cod, r.descricao, float(r.sistema), float(r.grade), float(r.dif), float(r.dif_pct),
                           1 if r.divergente else 0) for r in comp.itertuples(index=False)])
    _alertar(operacao_id, cid, data, comp)
    return int(cid)


def _alertar(operacao_id: int, cid: int, data: str, comp: pd.DataFrame) -> None:
    div = comp[comp["divergente"]]
    if div.empty:
        return
    try:
        from repositories import motoristas_repo

        filial = (operacoes_repo.buscar(operacao_id) or {}).get("nome", "")
        top = "; ".join(f"{r.cod} {str(r.descricao)[:26]}: sistema {r.sistema:.0f} × grade {r.grade:.0f} "
                        f"({r.dif_pct:+.0f}%)" for r in div.head(5).itertuples())
        for uid in controle(operacao_id):
            motoristas_repo.criar_notificacao(
                uid, "grade", f"grade:{cid}:{uid}", f"⚠️ Grade {filial}: {len(div)} item(ns) com diferença",
                f"Check de {data[8:10]}/{data[5:7]}: {len(div)} de {len(comp)} itens acima de {limite(operacao_id):.0f}%. "
                f"{top}{' …' if len(div) > 5 else ''}", "armazem", agora() + ":00")
    except Exception:  # noqa: BLE001
        pass


def checks(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT * FROM grade_checks WHERE {trecho} ORDER BY data DESC, id DESC", p)


def itens(check_id: int) -> pd.DataFrame:
    df = query_df("SELECT * FROM grade_check_itens WHERE check_id = ?", (int(check_id),))
    for c in ("sistema", "grade", "dif", "dif_pct"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["divergente"] = df["divergente"].astype(int) == 1
    return df


def recorrentes(operacao_id: int, ultimos: int = 10) -> pd.DataFrame:
    """Itens que deram diferença em mais de um check (dos últimos N)."""
    ck = checks(operacao_id).head(ultimos)
    if ck.empty:
        return pd.DataFrame()
    ph = ", ".join("?" * len(ck))
    df = query_df(f"SELECT check_id, cod, descricao, dif, dif_pct FROM grade_check_itens WHERE divergente = 1 "
                  f"AND check_id IN ({ph})", tuple(int(i) for i in ck["id"]))
    if df.empty:
        return df
    g = df.groupby("cod", as_index=False).agg(descricao=("descricao", "first"), vezes=("check_id", "nunique"),
                                              dif_media=("dif", "mean"))
    g["de"] = len(ck)
    return g[g["vezes"] > 1].sort_values("vezes", ascending=False).reset_index(drop=True)


def excluir_check(check_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM grade_check_itens WHERE check_id = ?", (int(check_id),))
        conn.execute("DELETE FROM grade_checks WHERE id = ?", (int(check_id),))
