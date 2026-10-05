"""Acesso a dados: armazéns e áreas."""
import pandas as pd

from database.connection import execute, query_all, query_df, query_one


def listar_armazens(operacao_id: int) -> list[dict]:
    return query_all("SELECT * FROM armazens WHERE operacao_id = ? ORDER BY nome", (operacao_id,))


def capacidade_total(operacao_id: int) -> dict:
    from repositories import operacoes_repo
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_one(f"""SELECT COALESCE(SUM(cap_hl),0) AS cap_hl, COALESCE(SUM(cap_paletes),0) AS cap_paletes
                     FROM armazens WHERE {f_sql}""", ids)
    return {"cap_hl": float(r["cap_hl"]), "cap_paletes": float(r["cap_paletes"])}


def salvar_armazem(operacao_id: int, nome: str, cap_hl: float, cap_paletes: float) -> None:
    execute("""
        INSERT INTO armazens (operacao_id, nome, cap_hl, cap_paletes) VALUES (?, ?, ?, ?)
        ON CONFLICT(operacao_id, nome) DO UPDATE SET cap_hl = excluded.cap_hl, cap_paletes = excluded.cap_paletes
    """, (operacao_id, nome, cap_hl, cap_paletes))


def excluir_armazem(armazem_id: int) -> None:
    execute("DELETE FROM armazens WHERE id = ?", (armazem_id,))


def areas_df(operacao_id: int) -> pd.DataFrame:
    return query_df("""
        SELECT ar.id, a.nome AS armazem, ar.nome AS area, ar.cap_paletes, ar.cap_hl
        FROM armazem_areas ar JOIN armazens a ON a.id = ar.armazem_id
        WHERE a.operacao_id = ? ORDER BY a.nome, ar.nome
    """, (operacao_id,))


def salvar_area(armazem_id: int, nome: str, cap_paletes: float, cap_hl: float) -> None:
    execute("""
        INSERT INTO armazem_areas (armazem_id, nome, cap_paletes, cap_hl) VALUES (?, ?, ?, ?)
        ON CONFLICT(armazem_id, nome) DO UPDATE SET cap_paletes = excluded.cap_paletes, cap_hl = excluded.cap_hl
    """, (armazem_id, nome, cap_paletes, cap_hl))


def excluir_area(area_id: int) -> None:
    execute("DELETE FROM armazem_areas WHERE id = ?", (area_id,))
