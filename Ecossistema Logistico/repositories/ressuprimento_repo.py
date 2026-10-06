"""Acesso a dados: ressuprimento diário, metas mensais e pedidos marcados."""
import pandas as pd

from database.connection import execute, query_df
from repositories import operacoes_repo


def diario_df(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"""
        SELECT data, cesta, SUM(volume_sellin_hl) AS volume_sellin_hl, SUM(volume_real_hl) AS volume_real_hl
        FROM ressuprimento_diario
        WHERE {f_sql} AND substr(data, 1, 7) = ?
        GROUP BY data, cesta ORDER BY data, cesta
    """, (*ids, mes_ano))


def diario_ops_df(operacao_id: int, de: str | None = None, ate: str | None = None) -> pd.DataFrame:
    """Linhas por filial (sem somar) — base do cálculo do real do mês."""
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, p = (f"""SELECT operacao_id, data, cesta, volume_sellin_hl, volume_real_hl, volume_txt FROM ressuprimento_diario
                  WHERE {f_sql}""", list(ids))
    if de:
        sql += " AND data >= ?"
        p.append(de)
    if ate:
        sql += " AND data <= ?"
        p.append(ate)
    return query_df(sql + " ORDER BY operacao_id, cesta, data", p)


def meses_disponiveis(operacao_id: int) -> list[str]:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT DISTINCT substr(data,1,7) AS m FROM ressuprimento_diario WHERE {f_sql} ORDER BY m DESC", ids)
    return df["m"].tolist()


def metas_df(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT cesta, SUM(meta_volume_hl) AS meta_volume_hl FROM metas_ressuprimento "
                    f"WHERE {f_sql} AND mes_ano = ? GROUP BY cesta", (*ids, mes_ano))


def salvar_meta(operacao_id: int, mes_ano: str, cesta: str, meta: float) -> None:
    execute("""
        INSERT INTO metas_ressuprimento (operacao_id, mes_ano, cesta, meta_volume_hl) VALUES (?, ?, ?, ?)
        ON CONFLICT(operacao_id, mes_ano, cesta) DO UPDATE SET meta_volume_hl = excluded.meta_volume_hl
    """, (operacao_id, mes_ano, cesta, meta))


# --- Pedidos marcados (Puxada) -------------------------------------------
def pedidos_marcados_df(operacao_id: int, data_puxada: str | None = None) -> pd.DataFrame:
    sql, p = """SELECT data_puxada, numero_pedido, cod, descricao, cx_solicitadas, cx_marcadas,
                       hl_marcado, status_item, dt_atualizacao
                FROM pedidos_marcados WHERE """ + operacoes_repo.filtro("operacao_id", operacao_id)[0], \
        list(operacoes_repo.ids_efetivos(operacao_id))
    if data_puxada:
        sql += " AND data_puxada = ?"
        p.append(data_puxada)
    return query_df(sql + " ORDER BY data_puxada DESC, numero_pedido, cod", p)


def datas_puxada(operacao_id: int) -> list[str]:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT DISTINCT data_puxada FROM pedidos_marcados WHERE {f_sql} ORDER BY data_puxada DESC", ids)
    return df["data_puxada"].tolist()
