"""Regras de negócio: posição de estoque, DOI e ocupação do armazém."""
import numpy as np
import pandas as pd

from repositories import armazem_repo, estoque_repo


def posicao_com_indicadores(operacao_id: int) -> pd.DataFrame:
    df = estoque_repo.posicao_estoque_df(operacao_id)
    if df.empty:
        return df
    df["hl"] = df["disponivel"] * df["fator_hl"]
    df["paletes"] = np.where(df["cx_pallet"] > 0, df["disponivel"] / df["cx_pallet"], 0.0)
    df["doi"] = np.where(df["linear_cx_dia"] > 0, df["disponivel"] / df["linear_cx_dia"], np.nan)
    df["situacao"] = np.select(
        [df["doi"].isna(), df["disponivel"] <= 0, df["doi"] < df["doi_meta"] * 0.5,
         df["doi"] < df["doi_meta"], df["doi"] > df["doi_meta"] * 2],
        ["Sem giro", "Ruptura", "Crítico", "Abaixo da meta", "Excesso"],
        default="OK",
    )
    # Sugestão de compra para atingir a meta de dias
    df["sugestao_cx"] = np.maximum(df["doi_meta"] * df["linear_cx_dia"] - df["disponivel"], 0).round(0)
    return df


def resumo(operacao_id: int, df: pd.DataFrame | None = None) -> dict:
    df = posicao_com_indicadores(operacao_id) if df is None else df
    cap = armazem_repo.capacidade_total(operacao_id)
    hl = float(df["hl"].sum()) if not df.empty else 0.0
    pal = float(df["paletes"].sum()) if not df.empty else 0.0
    com_giro = df.dropna(subset=["doi"]) if not df.empty else df
    doi_medio = (com_giro["disponivel"].sum() / com_giro["linear_cx_dia"].sum()
                 if not com_giro.empty and com_giro["linear_cx_dia"].sum() > 0 else 0.0)
    return {
        "skus": int(len(df)),
        "hl": hl,
        "paletes": pal,
        "cap_hl": cap["cap_hl"],
        "cap_paletes": cap["cap_paletes"],
        "ocup_hl": hl / cap["cap_hl"] * 100 if cap["cap_hl"] else 0.0,
        "ocup_paletes": pal / cap["cap_paletes"] * 100 if cap["cap_paletes"] else 0.0,
        "doi_medio": float(doi_medio),
        "rupturas": int((df["situacao"] == "Ruptura").sum()) if not df.empty else 0,
        "criticos": int((df["situacao"] == "Crítico").sum()) if not df.empty else 0,
    }
