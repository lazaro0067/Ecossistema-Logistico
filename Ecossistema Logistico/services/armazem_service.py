"""Regras de negócio: posição de estoque, DOI e ocupação do armazém."""
import numpy as np
import pandas as pd

from repositories import armazem_repo, estoque_repo
from services import produtos_service

# Faixas do sistema original (Portal do RN e saúde DPO): DOI em dias
DOI_BAIXO, DOI_ALTO = 3.0, 15.0


def posicao_com_indicadores(operacao_id: int) -> pd.DataFrame:
    df = estoque_repo.posicao_estoque_df(operacao_id)
    if df.empty:
        return df
    for c in ("inicial", "entrada", "saida", "disponivel", "fator_hl", "cx_pallet", "linear_cx_dia", "doi_meta"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["descricao"] = df["descricao"].fillna("").astype(str).str.strip()
    df["tipo"] = df["tipo"].where(df["tipo"].notna() & (df["tipo"].astype(str).str.len() > 0),
                                  df["descricao"].map(produtos_service.tipo_sku))
    df["categoria_detalhada"] = df["descricao"].map(produtos_service.categoria_detalhada)
    df["marca"] = df["descricao"].map(produtos_service.marca)
    df["hl"] = df["disponivel"] * df["fator_hl"]
    df["paletes"] = np.where(df["cx_pallet"] > 0, df["disponivel"] / df["cx_pallet"], 0.0)
    df["doi"] = np.where(df["linear_cx_dia"] > 0, df["disponivel"] / df["linear_cx_dia"], np.nan)
    df["situacao"] = np.select(
        [df["doi"].isna(), df["disponivel"] <= 0, df["doi"] < df["doi_meta"] * 0.5,
         df["doi"] < df["doi_meta"], df["doi"] > df["doi_meta"] * 2],
        ["Sem giro", "Ruptura", "Crítico", "Abaixo da meta", "Excesso"],
        default="OK",
    )
    # Status comercial (regra do Portal do RN no sistema original)
    df["status_comercial"] = np.select(
        [df["disponivel"] <= 0, df["doi"].fillna(999) < DOI_BAIXO, df["doi"].fillna(999) <= DOI_ALTO],
        ["Stock Out", "Stock Low", "Stock Ideal"], default="Stock Over")
    # Sugestão de compra para atingir a meta de dias
    df["sugestao_cx"] = np.maximum(df["doi_meta"] * df["linear_cx_dia"] - df["disponivel"], 0).round(0)
    return df


def saude_dpo(df: pd.DataFrame) -> dict:
    """Saúde do estoque DPO: % de SKUs com DOI entre 3 e 15 dias (meta DPO ≥ 85%)."""
    if df is None or df.empty:
        return {"pct": 0.0, "saudaveis": 0, "risco": 0, "excesso": 0}
    doi = df["doi"].fillna(999)
    ok = int(((doi >= DOI_BAIXO) & (doi <= DOI_ALTO)).sum())
    return {"pct": ok / len(df) * 100, "saudaveis": ok, "risco": int((doi < DOI_BAIXO).sum()),
            "excesso": int((doi > DOI_ALTO).sum())}


def estoque_comercial(operacao_id: int) -> pd.DataFrame:
    """Estoque + marcações D0/D1/D2 (hoje e próximos dias) + estoque projetado."""
    from services import sugestao_service

    df = posicao_com_indicadores(operacao_id)
    if df.empty:
        return df
    marc = sugestao_service.marcado_por_dia(operacao_id)
    for i in range(3):
        df[f"d{i}"] = 0.0
    if not marc.empty:
        datas = sorted(marc["data_puxada"].unique())[:3]
        for i, d in enumerate(datas):
            df[f"d{i}"] = df["cod"].map(marc[marc["data_puxada"] == d].groupby("cod")["cx_marcadas"].sum()).fillna(0.0)
    from services import transito_service

    tr = transito_service.transito_por_cod(operacao_id)
    df["transito"] = df["cod"].map(tr).fillna(0.0) if not tr.empty else 0.0
    df["projetado"] = df["disponivel"] + df["transito"] + df["d0"] + df["d1"] + df["d2"]
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
