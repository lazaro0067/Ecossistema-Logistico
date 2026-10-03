"""Acesso a dados: ressuprimento diário, metas mensais e pedidos marcados."""
import pandas as pd

from database.connection import execute, query_df


def diario_df(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    return query_df("""
        SELECT data, cesta, volume_sellin_hl, volume_real_hl
        FROM ressuprimento_diario
        WHERE operacao_id = ? AND substr(data, 1, 7) = ?
        ORDER BY data, cesta
    """, (operacao_id, mes_ano))


def meses_disponiveis(operacao_id: int) -> list[str]:
    df = query_df("SELECT DISTINCT substr(data,1,7) AS m FROM ressuprimento_diario WHERE operacao_id = ? ORDER BY m DESC",
                  (operacao_id,))
    return df["m"].tolist()


def metas_df(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    return query_df("SELECT cesta, meta_volume_hl FROM metas_ressuprimento WHERE operacao_id = ? AND mes_ano = ?",
                    (operacao_id, mes_ano))


def salvar_meta(operacao_id: int, mes_ano: str, cesta: str, meta: float) -> None:
    execute("""
        INSERT INTO metas_ressuprimento (operacao_id, mes_ano, cesta, meta_volume_hl) VALUES (?, ?, ?, ?)
        ON CONFLICT(operacao_id, mes_ano, cesta) DO UPDATE SET meta_volume_hl = excluded.meta_volume_hl
    """, (operacao_id, mes_ano, cesta, meta))


# --- Pedidos marcados (Puxada) -------------------------------------------
def pedidos_marcados_df(operacao_id: int, data_puxada: str | None = None) -> pd.DataFrame:
    sql, p = """SELECT data_puxada, numero_pedido, cod, descricao, cx_solicitadas, cx_marcadas,
                       hl_marcado, status_item, dt_atualizacao
                FROM pedidos_marcados WHERE operacao_id = ?""", [operacao_id]
    if data_puxada:
        sql += " AND data_puxada = ?"
        p.append(data_puxada)
    return query_df(sql + " ORDER BY data_puxada DESC, numero_pedido, cod", p)


def datas_puxada(operacao_id: int) -> list[str]:
    df = query_df("SELECT DISTINCT data_puxada FROM pedidos_marcados WHERE operacao_id = ? ORDER BY data_puxada DESC",
                  (operacao_id,))
    return df["data_puxada"].tolist()
