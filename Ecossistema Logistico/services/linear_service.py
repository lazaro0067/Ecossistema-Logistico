"""📈 Linear dinâmica — venda média por dia (cx/dia) de cada produto, calculada pelo próprio sistema.

• Base: a venda dos últimos 2 meses (03.02.37 vendas, venda + bonificação, em caixas) ÷ dias de venda do período.
• Média inteligente quando o produto não tem os 2 meses:
    – produto novo (1ª venda dentro dos 2 meses) → média desde a 1ª venda;
    – sem venda nos 2 meses, mas vendeu nos últimos 6 → média dos 6 meses;
    – nunca vendeu / pouco dado → fica a linear que foi subida (relatório Linear).
• Crescimento: % em cima da média (ex.: +10%).
• Crítica por produto: um valor manual (cx/dia) que vale no lugar do calculado.
• Ligada/desligada por revenda: ligada, substitui a linear subida em todo o sistema (sugestão, DOI, estoque do
  dia…); desligada, volta tudo para a linear subida.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from core import tempo
from database.connection import execute, query_df, query_one

DIAS_BASE = 60          # "últimos 2 meses"
DIAS_LONGO = 180        # média longa (6 meses)
MIN_DIAS_VENDA = 5      # menos que isso: dado fraco
_CACHE: dict = {}


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


# --- configuração e críticas --------------------------------------------------------------------------------------
def config(op: int) -> dict:
    try:
        r = query_one("SELECT * FROM linear_config WHERE operacao_id = ?", (int(op),))
    except Exception:  # noqa: BLE001 — banco antes da migração
        r = None
    return {"ativa": bool(r and r["ativa"]), "crescimento": float(r["crescimento"] or 0) if r else 0.0,
            "por": (r or {}).get("atualizado_por"), "em": (r or {}).get("atualizado_em")}


def salvar_config(op: int, ativa: bool, crescimento: float, usuario: str = "") -> None:
    execute("""INSERT INTO linear_config (operacao_id, ativa, crescimento, atualizado_por, atualizado_em)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT(operacao_id) DO UPDATE SET ativa = excluded.ativa,
               crescimento = excluded.crescimento, atualizado_por = excluded.atualizado_por,
               atualizado_em = excluded.atualizado_em""",
            (int(op), 1 if ativa else 0, float(crescimento or 0), usuario, agora()))
    _CACHE.clear()


def ajustes(op: int) -> pd.DataFrame:
    try:
        return query_df("SELECT cod, linear_manual, obs, por, em FROM linear_ajustes WHERE operacao_id = ?", (int(op),))
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=["cod", "linear_manual", "obs", "por", "em"])


def salvar_ajuste(op: int, cod: int, linear_manual: float | None, obs: str = "", usuario: str = "") -> None:
    """linear_manual vazio e sem observação = tira a crítica (volta ao calculado)."""
    if (linear_manual is None or pd.isna(linear_manual)) and not (obs or "").strip():
        execute("DELETE FROM linear_ajustes WHERE operacao_id = ? AND cod = ?", (int(op), int(cod)))
    else:
        val = None if linear_manual is None or pd.isna(linear_manual) else max(float(linear_manual), 0.0)
        execute("""INSERT INTO linear_ajustes (operacao_id, cod, linear_manual, obs, por, em) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(operacao_id, cod) DO UPDATE SET linear_manual = excluded.linear_manual,
                   obs = excluded.obs, por = excluded.por, em = excluded.em""",
                (int(op), int(cod), val, (obs or "").strip() or None, usuario, agora()))
    _CACHE.clear()


# --- cálculo ------------------------------------------------------------------------------------------------------
def _cod(v) -> int | None:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _vendas(op: int, de: dt.date, ate: dt.date) -> pd.DataFrame:
    """Caixas vendidas por produto e dia (venda + bonificação, status do padrão de venda)."""
    from services import faturamento_service as fs

    ops = [str(x) for x in fs.operacoes_do_setor("hl_venda")]
    st_ = fs.STATUS_PADRAO["venda"]
    sql = ("SELECT data, produto, MAX(descricao) AS descricao, SUM(qtde) AS cx, operacao_cod, status "
           "FROM notas_prod_dia WHERE operacao_id = ? AND origem = 'venda' AND data BETWEEN ? AND ? "
           "GROUP BY data, produto, operacao_cod, status")
    d = query_df(sql, (int(op), de.isoformat(), ate.isoformat()))
    if d.empty:
        return pd.DataFrame(columns=["data", "cod", "descricao", "cx"])
    d = d[d["operacao_cod"].astype(str).isin(ops) & d["status"].astype(str).isin(st_)] if ops else d
    d["cod"] = d["produto"].map(_cod)
    d = d.dropna(subset=["cod"])
    d["cx"] = pd.to_numeric(d["cx"], errors="coerce").fillna(0.0)
    d["data"] = pd.to_datetime(d["data"]).dt.date
    return d.groupby(["data", "cod"], as_index=False).agg(cx=("cx", "sum"), descricao=("descricao", "first"))


def _assinatura(op: int, cfg: dict, hoje: dt.date) -> tuple:
    try:
        n = query_one("SELECT COUNT(*) AS n, MAX(id) AS m FROM notas_prod_dia WHERE operacao_id = ? AND origem = 'venda'",
                      (int(op),))
        a = query_one("SELECT COUNT(*) AS n, MAX(em) AS m FROM linear_ajustes WHERE operacao_id = ?", (int(op),))
        lv = query_one("SELECT COUNT(*) AS n, SUM(linear_cx_dia) AS s FROM linear_vendas WHERE operacao_id = ?",
                       (int(op),))
    except Exception:  # noqa: BLE001
        n = a = lv = {}
    return (op, hoje, cfg["crescimento"], cfg["em"], tuple((n or {}).values()), tuple((a or {}).values()),
            tuple((lv or {}).values()))


def calcular(op: int, hoje: dt.date | None = None) -> pd.DataFrame:
    """Uma linha por produto: linear subida, média calculada, método, dinâmica (+ crescimento), crítica e final."""
    hoje = hoje or tempo.hoje()
    cfg = config(op)
    chave = _assinatura(op, cfg, hoje)
    if chave in _CACHE:
        return _CACHE[chave].copy()
    ate = hoje - dt.timedelta(days=1)  # até ontem (o dia de hoje está incompleto)
    ini_base = ate - dt.timedelta(days=DIAS_BASE - 1)
    ini_longo = ate - dt.timedelta(days=DIAS_LONGO - 1)
    v = _vendas(op, ini_longo, ate)
    dias_venda_longo = sorted(v["data"].unique()) if not v.empty else []
    dias_base = [d for d in dias_venda_longo if d >= ini_base]
    sub = query_df("SELECT cod, linear_cx_dia FROM linear_vendas WHERE operacao_id = ?", (int(op),))
    subida = {int(c): float(x or 0) for c, x in zip(sub["cod"], sub["linear_cx_dia"])}
    prods = query_df("SELECT cod, descricao FROM produtos")
    nomes = {int(c): d for c, d in zip(prods["cod"], prods["descricao"]) if _cod(c) is not None}
    linhas = []
    cods = sorted(set(subida) | (set(v["cod"].astype(int)) if not v.empty else set()))
    por_prod = {int(c): g for c, g in v.groupby("cod")} if not v.empty else {}
    for c in cods:
        g = por_prod.get(c)
        base = g[g["data"] >= ini_base] if g is not None else None
        media, metodo, dias = None, "", 0
        if base is not None and not base.empty and len(dias_base) >= MIN_DIAS_VENDA:
            primeira = base["data"].min()
            ja_vendia = g is not None and (g["data"] < ini_base).any()
            if ja_vendia or primeira <= ini_base + dt.timedelta(days=7):
                dias = len(dias_base)
                media, metodo = base["cx"].sum() / dias, "2 meses"
            else:  # produto novo: média desde a 1ª venda
                dias = len([d for d in dias_base if d >= primeira])
                if dias >= 3:
                    media, metodo = base["cx"].sum() / dias, "desde a 1ª venda (novo)"
        elif g is not None and not g.empty and len(dias_venda_longo) >= MIN_DIAS_VENDA:
            dias = len(dias_venda_longo)
            media, metodo = g["cx"].sum() / dias, "6 meses (sem venda recente)"
        if media is None:
            if subida.get(c):
                media, metodo = subida[c], "linear subida (sem histórico)"
            else:
                media, metodo = 0.0, "sem venda"
        calculado = metodo.startswith(("2 meses", "desde", "6 meses"))
        dinamica = media * (1 + cfg["crescimento"] / 100) if calculado else media
        desc = nomes.get(c)
        if not desc and g is not None and not g.empty:
            desc = g["descricao"].dropna().iloc[0] if g["descricao"].notna().any() else None
        linhas.append({"cod": c, "descricao": desc or f"Cód {c}", "linear_subida": subida.get(c),
                       "media": media, "metodo": metodo, "dias_venda": dias, "linear_dinamica": dinamica})
    out = pd.DataFrame(linhas, columns=["cod", "descricao", "linear_subida", "media", "metodo", "dias_venda",
                                        "linear_dinamica"])
    aj = ajustes(op)
    aj["cod"] = aj["cod"].map(_cod)
    out = out.merge(aj[["cod", "linear_manual", "obs", "por", "em"]], on="cod", how="left")
    out["linear_final"] = out["linear_manual"].where(out["linear_manual"].notna(), out["linear_dinamica"])
    out.attrs.update(periodo=(ini_base, ate), dias_base=len(dias_base))
    _CACHE.clear()
    _CACHE[chave] = out
    return out.copy()


def efetiva(op: int) -> pd.DataFrame | None:
    """Linear que o sistema usa nesta revenda: a dinâmica (ligada) ou None (= a linear subida, como sempre foi)."""
    if not config(op)["ativa"]:
        return None
    d = calcular(op)
    return d[["cod", "linear_final"]].rename(columns={"linear_final": "linear_cx_dia"})
