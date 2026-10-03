"""Regras de negócio: aderência do ressuprimento (real x sell-in x meta)."""
import pandas as pd

from repositories import ressuprimento_repo


def aderencia_mensal(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    diario = ressuprimento_repo.diario_df(operacao_id, mes_ano)
    if diario.empty:
        return pd.DataFrame(columns=["cesta", "sellin_hl", "real_hl", "meta_hl", "aderencia_sellin", "atingimento_meta"])
    agg = (diario.groupby("cesta", as_index=False)
                 .agg(sellin_hl=("volume_sellin_hl", "sum"), real_hl=("volume_real_hl", "sum")))
    metas = ressuprimento_repo.metas_df(operacao_id, mes_ano).rename(columns={"meta_volume_hl": "meta_hl"})
    df = agg.merge(metas, on="cesta", how="left").fillna({"meta_hl": 0})
    df["aderencia_sellin"] = (df["real_hl"] / df["sellin_hl"].where(df["sellin_hl"] > 0) * 100).round(1)
    df["atingimento_meta"] = (df["real_hl"] / df["meta_hl"].where(df["meta_hl"] > 0) * 100).round(1)
    return df


def evolucao_diaria(operacao_id: int, mes_ano: str, cesta: str) -> pd.DataFrame:
    d = ressuprimento_repo.diario_df(operacao_id, mes_ano)
    d = d[d["cesta"] == cesta].copy()
    d["real_acum"] = d["volume_real_hl"].cumsum()
    d["sellin_acum"] = d["volume_sellin_hl"].cumsum()
    return d
