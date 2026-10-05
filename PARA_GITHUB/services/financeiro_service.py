"""Regras de negócio: contas a pagar, vencimentos, fluxo de caixa e diagnóstico financeiro."""
import datetime as dt

import pandas as pd

from core import tempo
from repositories import financeiro_repo

AMBEV = "AMBEV"


def fluxo_projetado(operacao_id: int, saldo_inicial: float, dias: int = 15) -> pd.DataFrame:
    """Projeção diária: saldo = saldo anterior (ou saldo do banco informado) + recebimentos
    − contas a pagar (sem Ambev, que entra como compra manual) − compras Ambev."""
    hoje = tempo.hoje()
    datas = [hoje + dt.timedelta(days=i) for i in range(dias)]
    contas = financeiro_repo.contas_df(operacao_id)
    sem_ambev = contas[~contas["fornecedor"].fillna("").str.upper().str.contains(AMBEV)] if not contas.empty else contas
    pagar = sem_ambev.groupby("data_vencimento")["pendente"].sum() if not sem_ambev.empty else pd.Series(dtype=float)
    manuais = financeiro_repo.fluxo_df(operacao_id, datas[0].isoformat(), datas[-1].isoformat()).set_index("data")

    linhas, saldo = [], float(saldo_inicial)
    for d in datas:
        m = manuais.loc[d.isoformat()] if d.isoformat() in manuais.index else None
        banco = None if m is None or pd.isna(m["saldo_banco"]) else float(m["saldo_banco"])
        compra = 0.0 if m is None else float(m["compra_ambev"] or 0)
        receb = 0.0 if m is None else float(m["previsao_recebimento"] or 0)
        cp = float(pagar.get(d, 0.0))
        base = banco if banco is not None else saldo
        saldo = base + receb - cp - compra
        linhas.append({"data": d, "saldo_banco": banco, "previsao_recebimento": receb, "contas_pagar": cp,
                       "compra_ambev": compra, "saldo_projetado": saldo})
    return pd.DataFrame(linhas)


def diagnostico(operacao_id: int) -> dict:
    df = financeiro_repo.contas_df(operacao_id)
    if df.empty:
        return {}
    hoje = tempo.hoje()
    pend = df[df["pendente"] > 0]
    vencidos = pend[pend["data_vencimento"] < hoje]
    prox7 = pend[(pend["data_vencimento"] >= hoje) & (pend["data_vencimento"] <= hoje + dt.timedelta(days=7))]
    por_forn = pend.groupby("fornecedor")["pendente"].sum().sort_values(ascending=False)
    total = float(pend["pendente"].sum())
    return {
        "valor_total": float(df["valor"].sum()), "realizado": float(df["realizado"].sum()), "pendente": total,
        "vencidos": float(vencidos["pendente"].sum()), "qtd_vencidos": len(vencidos),
        "prox7": float(prox7["pendente"].sum()), "qtd_prox7": len(prox7),
        "top_fornecedores": por_forn.head(10),
        "concentracao_top3": float(por_forn.head(3).sum() / total * 100) if total else 0.0,
        "por_conta": pend.groupby(pend["conta_gerencial"].fillna("—"))["pendente"].sum().sort_values(ascending=False).head(8),
        "por_pacote": pend.groupby(pend["pacote"].fillna("—"))["pendente"].sum().sort_values(ascending=False).head(8),
    }
