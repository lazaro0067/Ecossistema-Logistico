"""Acesso a dados: contas a pagar, fluxo de caixa e metas de vendas."""
import pandas as pd

from database.connection import execute, query_df


def contas_df(operacao_id: int) -> pd.DataFrame:
    df = query_df("SELECT * FROM contas_pagar WHERE operacao_id = ? ORDER BY data_vencimento, fornecedor",
                  (operacao_id,))
    for c in ("valor", "realizado"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["pendente"] = (df["valor"] - df["realizado"]).clip(lower=0)
    df["data_vencimento"] = pd.to_datetime(df["data_vencimento"], errors="coerce").dt.date
    return df


def fluxo_df(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    return query_df("SELECT data, saldo_banco, compra_ambev, previsao_recebimento FROM fluxo_caixa "
                    "WHERE operacao_id = ? AND data BETWEEN ? AND ? ORDER BY data", (operacao_id, de, ate))


def salvar_fluxo(operacao_id: int, data: str, saldo_banco, compra_ambev: float, previsao: float) -> None:
    execute("""
        INSERT INTO fluxo_caixa (operacao_id, data, saldo_banco, compra_ambev, previsao_recebimento)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(operacao_id, data) DO UPDATE SET saldo_banco = excluded.saldo_banco,
            compra_ambev = excluded.compra_ambev, previsao_recebimento = excluded.previsao_recebimento
    """, (operacao_id, data, saldo_banco, compra_ambev, previsao))


# --- Metas de vendas -------------------------------------------------------------
def metas_vendas_df(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    return query_df("SELECT categoria, meta_hl, realizado_hl FROM metas_vendas WHERE operacao_id = ? AND mes_ano = ? "
                    "ORDER BY categoria", (operacao_id, mes_ano))


def salvar_meta_venda(operacao_id: int, mes_ano: str, categoria: str, meta: float, realizado: float) -> None:
    execute("""
        INSERT INTO metas_vendas (operacao_id, mes_ano, categoria, meta_hl, realizado_hl) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(operacao_id, mes_ano, categoria) DO UPDATE SET meta_hl = excluded.meta_hl,
            realizado_hl = excluded.realizado_hl
    """, (operacao_id, mes_ano, categoria, meta, realizado))


def excluir_meta_venda(operacao_id: int, mes_ano: str, categoria: str) -> None:
    execute("DELETE FROM metas_vendas WHERE operacao_id = ? AND mes_ano = ? AND categoria = ?",
            (operacao_id, mes_ano, categoria))
