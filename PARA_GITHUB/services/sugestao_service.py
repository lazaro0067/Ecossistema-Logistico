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
    df = query_df("""
        SELECT data_puxada, cod, SUM(cx_marcadas) AS cx_marcadas, SUM(cx_solicitadas) AS cx_solicitadas,
               SUM(hl_marcado) AS hl_marcado
        FROM pedidos_marcados WHERE operacao_id = ? AND data_puxada >= ?
        GROUP BY data_puxada, cod ORDER BY data_puxada
    """, (operacao_id, desde.isoformat()))
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


def sugestao(operacao_id: int, arredondar_palete: bool = True) -> pd.DataFrame:
    pos = armazem_service.posicao_com_indicadores(operacao_id)
    if pos.empty:
        return pos
    marc = marcado_por_dia(operacao_id)
    futuro = marc.groupby("cod")["cx_marcadas"].sum() if not marc.empty else pd.Series(dtype=float)
    pos["marcado_cx"] = pos["cod"].map(futuro).fillna(0.0)

    alvo = pos["doi_meta"] * pos["linear_cx_dia"]
    nec = np.maximum(alvo - pos["disponivel"] - pos["marcado_cx"], 0.0)
    if arredondar_palete:
        nec = np.where((nec > 0) & (pos["cx_pallet"] > 0), np.ceil(nec / pos["cx_pallet"].where(pos["cx_pallet"] > 0, 1))
                       * pos["cx_pallet"], np.ceil(nec))
    pos["sugestao_cx"] = nec
    pos["sugestao_paletes"] = np.where(pos["cx_pallet"] > 0, pos["sugestao_cx"] / pos["cx_pallet"], 0.0)
    pos["sugestao_hl"] = pos["sugestao_cx"] * pos["fator_hl"]
    pos["doi_projetado"] = np.where(pos["linear_cx_dia"] > 0,
                                    (pos["disponivel"] + pos["marcado_cx"] + pos["sugestao_cx"]) / pos["linear_cx_dia"],
                                    np.nan)
    pos["cobertura_pct"] = np.where(alvo > 0, (pos["disponivel"] + pos["marcado_cx"]) / alvo * 100, np.nan)
    # prioridade: menor cobertura primeiro
    return pos.sort_values(["cobertura_pct", "linear_cx_dia"], ascending=[True, False], na_position="last")


def status_cobertura(pct) -> str:
    if pct is None or pd.isna(pct):
        return "neutro"
    return "critico" if pct < 50 else "serio" if pct < 80 else "atencao" if pct < 100 else "bom"
