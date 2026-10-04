"""Acesso a dados genérico para as tabelas de registros operacionais
(Distribuição, Frota, Gente, Financeiro, Compras)."""
import pandas as pd

from database.connection import execute, query_df

TABELAS_PERMITIDAS = {
    "distribuicao_rotas", "frota_manutencao", "gente_ssma", "financeiro_obz", "compras_pedidos",
}


def _checar(tabela: str) -> None:
    if tabela not in TABELAS_PERMITIDAS:
        raise ValueError(f"Tabela não permitida: {tabela}")


def listar_df(tabela: str, operacao_id: int, coluna_data: str | None = None,
              mes_ano: str | None = None) -> pd.DataFrame:
    _checar(tabela)
    sql, p = f"SELECT * FROM {tabela} WHERE operacao_id = ?", [operacao_id]
    if coluna_data and mes_ano:
        sql += f" AND substr({coluna_data}, 1, 7) = ?"
        p.append(mes_ano)
    return query_df(sql + " ORDER BY id DESC", p)


def inserir(tabela: str, dados: dict) -> int:
    _checar(tabela)
    cols = list(dados)
    return execute(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   [dados[c] for c in cols])


def excluir(tabela: str, registro_id: int, operacao_id: int) -> None:
    _checar(tabela)
    execute(f"DELETE FROM {tabela} WHERE id = ? AND operacao_id = ?", (registro_id, operacao_id))
