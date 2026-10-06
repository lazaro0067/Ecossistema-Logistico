"""Sugestão de compra e marcação por dia (D0, D1, D2...).

Necessidade (caixas) = meta de DOI × linear (cx/dia) − disponível − já marcado nos próximos dias.
"""
import datetime as dt

import numpy as np
import pandas as pd

from core import tempo
from database.connection import query_df
from services import armazem_service


def marcado_por_dia(operacao_id: int, desde: dt.date | None = None) -> pd.DataFrame:
    desde = desde or tempo.hoje()
    from repositories import operacoes_repo
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"""
        SELECT data_puxada, cod, SUM(cx_marcadas) AS cx_marcadas, SUM(cx_solicitadas) AS cx_solicitadas,
               SUM(hl_marcado) AS hl_marcado
        FROM pedidos_marcados WHERE {f_sql} AND data_puxada >= ?
        GROUP BY data_puxada, cod ORDER BY data_puxada
    """, (*ids, desde.isoformat()))
    if not df.empty:
        hoje = tempo.hoje()
        df["dia"] = df["data_puxada"].map(lambda d: _rotulo_dia(d, hoje))
    return df


def _rotulo_dia(data_iso: str, hoje: dt.date) -> str:
    try:
        d = dt.date.fromisoformat(data_iso)
    except ValueError:
        return data_iso
    n = (d - hoje).days
    return f"D{n} · {d:%d/%m}" if n >= 0 else f"{d:%d/%m}"


def data_alvo_padrao(operacao_id: int) -> dt.date:
    """Próximo dia ainda sem marcação (como no sistema original)."""
    marc = marcado_por_dia(operacao_id)
    hoje = tempo.hoje()
    if marc.empty:
        return hoje + dt.timedelta(days=1)
    ultima = dt.date.fromisoformat(max(marc["data_puxada"]))
    return max(ultima, hoje) + dt.timedelta(days=1)


def sugestao(operacao_id: int, data_alvo: dt.date | None = None, meta_doi: float | None = None,
             arredondar_palete: bool = True) -> pd.DataFrame:
    """Quanto marcar para a puxada do dia `data_alvo`.

    estoque no dia alvo = disponível + marcado até a véspera − linear × dias até o alvo
    necessidade        = meta de DOI × linear − estoque no dia alvo
    meta_doi=None usa a meta de DOI de cada SKU; um número aplica a mesma meta a todos.
    """
    pos = armazem_service.posicao_com_indicadores(operacao_id)
    if pos.empty:
        return pos
    hoje = tempo.hoje()
    data_alvo = data_alvo or data_alvo_padrao(operacao_id)
    dias = max(1, (data_alvo - hoje).days)

    marc = marcado_por_dia(operacao_id)
    antes = marc[marc["data_puxada"] < data_alvo.isoformat()] if not marc.empty else marc
    no_dia = marc[marc["data_puxada"] == data_alvo.isoformat()] if not marc.empty else marc
    pos["marcado_cx"] = pos["cod"].map(antes.groupby("cod")["cx_marcadas"].sum() if not antes.empty else {}).fillna(0.0)
    pos["ja_marcado_alvo"] = pos["cod"].map(
        no_dia.groupby("cod")["cx_marcadas"].sum() if not no_dia.empty else {}).fillna(0.0)

    meta = pos["doi_meta"] if meta_doi is None else pd.Series(meta_doi, index=pos.index)
    pos["meta_usada"] = meta
    pos["estoque_alvo"] = np.maximum(pos["disponivel"] + pos["marcado_cx"] - pos["linear_cx_dia"] * dias, 0.0)
    nec = np.maximum(meta * pos["linear_cx_dia"] - pos["estoque_alvo"] - pos["ja_marcado_alvo"], 0.0)
    if arredondar_palete:
        cx_pal = pos["cx_pallet"].where(pos["cx_pallet"] > 0, 1)
        nec = np.where((nec > 0) & (pos["cx_pallet"] > 0), np.ceil(nec / cx_pal) * cx_pal, np.ceil(nec))
    pos["sugestao_cx"] = nec
    pos["sugestao_paletes"] = np.where(pos["cx_pallet"] > 0, pos["sugestao_cx"] / pos["cx_pallet"], 0.0)
    pos["sugestao_hl"] = pos["sugestao_cx"] * pos["fator_hl"]
    pos["doi_alvo"] = np.where(pos["linear_cx_dia"] > 0, pos["estoque_alvo"] / pos["linear_cx_dia"], np.nan)
    pos["doi_projetado"] = np.where(
        pos["linear_cx_dia"] > 0,
        (pos["estoque_alvo"] + pos["ja_marcado_alvo"] + pos["sugestao_cx"]) / pos["linear_cx_dia"], np.nan)
    alvo_cx = meta * pos["linear_cx_dia"]
    pos["cobertura_pct"] = np.where(alvo_cx > 0, (pos["estoque_alvo"] + pos["ja_marcado_alvo"]) / alvo_cx * 100, np.nan)
    pos.attrs["dias"] = dias
    pos.attrs["data_alvo"] = data_alvo
    return pos.sort_values(["cobertura_pct", "linear_cx_dia"], ascending=[True, False], na_position="last")


def status_cobertura(pct) -> str:
    if pct is None or pd.isna(pct):
        return "neutro"
    return "critico" if pct < 50 else "serio" if pct < 80 else "atencao" if pct < 100 else "bom"


# --- Projeção de falta (ruptura) ---------------------------------------------------------
def projecao_falta(operacao_id: int, dia: dt.date) -> pd.DataFrame:
    """Quais produtos vão faltar no `dia` escolhido.

    estoque no início do dia = disponível hoje + marcado (puxadas) antes do dia − venda média × dias até o dia
    falta no dia            = venda média do dia − (estoque no início do dia + marcado para o próprio dia)
    ruptura prevista        = hoje + (disponível + tudo que já está marcado até o dia) ÷ venda média
    """
    pos = armazem_service.posicao_com_indicadores(operacao_id)
    if pos.empty:
        return pos
    hoje = tempo.hoje()
    dias = max((dia - hoje).days, 0)
    marc = marcado_por_dia(operacao_id)
    antes = marc[marc["data_puxada"] < dia.isoformat()] if not marc.empty else marc
    no_dia = marc[marc["data_puxada"] == dia.isoformat()] if not marc.empty else marc
    pos["entrada_antes"] = pos["cod"].map(antes.groupby("cod")["cx_marcadas"].sum() if not antes.empty else {}).fillna(0.0)
    pos["entrada_dia"] = pos["cod"].map(no_dia.groupby("cod")["cx_marcadas"].sum() if not no_dia.empty else {}).fillna(0.0)
    lin = pos["linear_cx_dia"]
    pos["estoque_inicio"] = pos["disponivel"] + pos["entrada_antes"] - lin * dias
    pos["estoque_fim"] = pos["estoque_inicio"] + pos["entrada_dia"] - lin
    pos["falta_cx"] = np.maximum(-pos["estoque_fim"], 0.0).round(0)
    total = pos["disponivel"] + pos["entrada_antes"] + pos["entrada_dia"]
    pos["cobertura_dias"] = np.where(lin > 0, total / lin, np.nan)
    pos["ruptura_em"] = [hoje + dt.timedelta(days=int(c)) if lin_ > 0 and c == c else None
                         for c, lin_ in zip(pos["cobertura_dias"], lin)]
    pos["falta_paletes"] = np.where(pos["cx_pallet"] > 0, np.ceil(pos["falta_cx"] / pos["cx_pallet"]), 0.0)
    pos["falta_hl"] = pos["falta_cx"] * pos["fator_hl"]
    # sobra no fim do dia em dias de venda (para avisar o que fica no limite)
    pos["sobra_dias"] = np.where(lin > 0, pos["estoque_fim"] / lin, np.nan)
    pos["situacao_dia"] = np.select(
        [lin <= 0, pos["estoque_inicio"] <= 0, pos["estoque_fim"] < 0, pos["sobra_dias"] < 1],
        ["Sem giro", "⛔ Sem estoque no dia", "🔴 Falta durante o dia", "🟡 No limite (< 1 dia)"], default="🟢 Coberto")
    ordem = {"⛔ Sem estoque no dia": 0, "🔴 Falta durante o dia": 1, "🟡 No limite (< 1 dia)": 2, "🟢 Coberto": 3,
             "Sem giro": 4}
    pos["_o"] = pos["situacao_dia"].map(ordem)
    pos.attrs["dias"] = dias
    return pos.sort_values(["_o", "falta_cx", "linear_cx_dia"], ascending=[True, False, False]).drop(columns="_o")
