"""Cálculo da curva ABC a partir de um volume vendido por SKU."""
import pandas as pd

from config.settings import CURVA_ABC_LIMITES


def calcular(df: pd.DataFrame, col_cod="cod", col_desc="descricao", col_qtde="total_qtde") -> pd.DataFrame:
    """Recebe cod/descrição/quantidade e devolve com % acumulado e classe A/B/C."""
    base = (df.groupby(col_cod, as_index=False)
              .agg(descricao=(col_desc, "first"), total_qtde=(col_qtde, "sum"))
              .rename(columns={col_cod: "cod"}))
    base = base[base["total_qtde"] > 0].sort_values("total_qtde", ascending=False)
    total = base["total_qtde"].sum()
    if total == 0:
        return base.assign(pct_acumulado=0.0, classe="C")
    base["pct_acumulado"] = base["total_qtde"].cumsum() / total * 100
    # o item que "cruza" o limite ainda pertence à classe anterior
    anterior = base["pct_acumulado"].shift(fill_value=0)
    base["classe"] = "C"
    base.loc[anterior < CURVA_ABC_LIMITES["B"], "classe"] = "B"
    base.loc[anterior < CURVA_ABC_LIMITES["A"], "classe"] = "A"
    return base.reset_index(drop=True)


def resumo_classes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    total = df["total_qtde"].sum()
    r = df.groupby("classe").agg(skus=("cod", "count"), volume=("total_qtde", "sum")).reset_index()
    r["pct_volume"] = r["volume"] / total * 100
    r["pct_skus"] = r["skus"] / r["skus"].sum() * 100
    return r
