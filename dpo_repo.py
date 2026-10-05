"""Acesso a dados: padrões do Book DPO, layouts do armazém e política de estoque."""
import pandas as pd

from core import tempo
from database.connection import execute, query_all, query_df, query_one
from repositories import operacoes_repo


# --- Padrões DPO -------------------------------------------------------------
def buscar_padrao(operacao_id: int, modulo: str, subbloco: str) -> dict | None:
    return query_one("SELECT * FROM padroes_dpo WHERE operacao_id = ? AND modulo = ? AND subbloco = ?",
                     (operacao_id, modulo, subbloco))


def salvar_padrao(operacao_id: int, modulo: str, subbloco: str, titulo: str, conteudo: str,
                  responsavel: str, status: str, usuario: str) -> None:
    execute("""
        INSERT INTO padroes_dpo (operacao_id, modulo, subbloco, titulo, conteudo, responsavel, status,
                                 atualizado_por, dt_atualizacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(operacao_id, modulo, subbloco) DO UPDATE SET
            titulo = excluded.titulo, conteudo = excluded.conteudo, responsavel = excluded.responsavel,
            status = excluded.status, atualizado_por = excluded.atualizado_por, dt_atualizacao = excluded.dt_atualizacao
    """, (operacao_id, modulo, subbloco, titulo, conteudo, responsavel, status, usuario, tempo.agora_str()))


def resumo_padroes(operacao_id: int, modulo: str) -> pd.DataFrame:
    return query_df("SELECT subbloco, titulo, status, responsavel, dt_atualizacao FROM padroes_dpo "
                    "WHERE operacao_id = ? AND modulo = ? ORDER BY subbloco", (operacao_id, modulo))


# --- Layouts (plantas) do armazém ---------------------------------------------
def layouts(operacao_id: int) -> list[dict]:
    return query_all("SELECT id, area, nome_arquivo, tipo, conteudo, dt_atualizacao FROM layouts_armazem "
                     "WHERE operacao_id = ? ORDER BY area, id DESC", (operacao_id,))


def salvar_layout(operacao_id: int, area: str, nome: str, tipo: str, conteudo: bytes) -> None:
    execute("INSERT INTO layouts_armazem (operacao_id, area, nome_arquivo, tipo, conteudo, dt_atualizacao) "
            "VALUES (?, ?, ?, ?, ?, ?)", (operacao_id, area, nome, tipo, conteudo, tempo.agora_str()))


def excluir_layout(lid: int) -> None:
    execute("DELETE FROM layouts_armazem WHERE id = ?", (lid,))


# --- Política de estoque -------------------------------------------------------
def datas_politica(operacao_id: int) -> list[str]:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT DISTINCT data_registro FROM politica_estoque WHERE {f_sql} ORDER BY data_registro DESC", ids)
    return df["data_registro"].tolist()


def politica_df(operacao_id: int, data: str) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("p.operacao_id", operacao_id)
    return query_df(f"""SELECT p.*, COALESCE(pr.descricao, p.sku_original) AS descricao
                        FROM politica_estoque p LEFT JOIN produtos pr ON pr.cod = p.cod
                        WHERE {f_sql} AND p.data_registro = ? ORDER BY p.cod""", (*ids, data))
