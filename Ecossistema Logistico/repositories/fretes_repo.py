"""Acesso a dados: cotações de frete e metas OBZ."""
import pandas as pd

from database.connection import execute, query_df, query_one

_SELECT_COTACAO = """
    SELECT c.id, c.status, c.data_requisicao, c.data_frete, c.motivo,
           o.nome AS origem, d.nome AS destino, t.nome AS transportadora,
           cc.nome AS centro_custo, c.valor_negociado, c.valor_tabela,
           s.nome AS solicitante, a.nome AS aprovador, c.aprovador_id, c.solicitante_id,
           c.observacao, c.decidido_em, c.motivo_rejeicao,
           c.numero_cte, c.nf_arquivo, c.cte_arquivo, c.finalizado_em
    FROM cotacoes_frete c
    LEFT JOIN origens_destinos o ON o.id = c.origem_id
    LEFT JOIN origens_destinos d ON d.id = c.destino_id
    LEFT JOIN transportadoras t  ON t.id = c.transportadora_id
    LEFT JOIN centros_custo cc   ON cc.id = c.centro_custo_id
    LEFT JOIN usuarios s         ON s.id = c.solicitante_id
    LEFT JOIN usuarios a         ON a.id = c.aprovador_id
"""


def inserir(dados: dict) -> int:
    campos = list(dados.keys())
    return execute(
        f"INSERT INTO cotacoes_frete ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
        [dados[c] for c in campos],
    )


def atualizar(cotacao_id: int, **campos) -> None:
    execute(
        f"UPDATE cotacoes_frete SET {', '.join(k + ' = ?' for k in campos)} WHERE id = ?",
        (*campos.values(), cotacao_id),
    )


def buscar(cotacao_id: int) -> dict | None:
    return query_one(_SELECT_COTACAO + " WHERE c.id = ?", (cotacao_id,))


def listar_df(operacao_id: int, status: list[str] | None = None,
              mes_ano: str | None = None, aprovador_id: int | None = None) -> pd.DataFrame:
    sql, params = _SELECT_COTACAO + " WHERE c.operacao_id = ?", [operacao_id]
    if status:
        sql += f" AND c.status IN ({', '.join('?' * len(status))})"
        params += status
    if mes_ano:
        sql += " AND substr(c.data_frete, 1, 7) = ?"
        params.append(mes_ano)
    if aprovador_id:
        sql += " AND c.aprovador_id = ?"
        params.append(aprovador_id)
    return query_df(sql + " ORDER BY c.id DESC", params)


def total_por_status(operacao_id: int, mes_ano: str, status: list[str]) -> float:
    r = query_one(
        f"""SELECT COALESCE(SUM(valor_negociado), 0) AS t FROM cotacoes_frete
            WHERE operacao_id = ? AND substr(data_frete, 1, 7) = ?
              AND status IN ({', '.join('?' * len(status))})""",
        (operacao_id, mes_ano, *status),
    )
    return float(r["t"])


def gasto_mensal_df(operacao_id: int, status: list[str]) -> pd.DataFrame:
    return query_df(
        f"""SELECT substr(data_frete, 1, 7) AS mes_ano, SUM(valor_negociado) AS realizado
            FROM cotacoes_frete WHERE operacao_id = ? AND status IN ({', '.join('?' * len(status))})
            GROUP BY 1 ORDER BY 1""",
        (operacao_id, *status),
    )


# --- Metas OBZ ------------------------------------------------------------
def salvar_meta(operacao_id: int, mes_ano: str, valor: float) -> None:
    execute("""
        INSERT INTO metas_obz (operacao_id, mes_ano, meta_valor) VALUES (?, ?, ?)
        ON CONFLICT(operacao_id, mes_ano) DO UPDATE SET meta_valor = excluded.meta_valor
    """, (operacao_id, mes_ano, valor))


def buscar_meta(operacao_id: int, mes_ano: str) -> float:
    r = query_one("SELECT meta_valor FROM metas_obz WHERE operacao_id = ? AND mes_ano = ?",
                  (operacao_id, mes_ano))
    return float(r["meta_valor"]) if r else 0.0


def metas_df(operacao_id: int) -> pd.DataFrame:
    return query_df("SELECT mes_ano, meta_valor AS meta FROM metas_obz WHERE operacao_id = ? ORDER BY mes_ano",
                    (operacao_id,))
