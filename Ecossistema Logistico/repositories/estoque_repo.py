"""Acesso a dados: produtos, estoque, linear de vendas, metas DOI e curva ABC."""
import pandas as pd

from database.connection import execute, query_df, query_one


def contar_produtos() -> int:
    return int(query_one("SELECT COUNT(*) AS n FROM produtos")["n"])


def buscar_produtos_df(filtro: str = "", limite: int = 200) -> pd.DataFrame:
    like = f"%{filtro}%"
    return query_df(
        "SELECT * FROM produtos WHERE CAST(cod AS TEXT) LIKE ? OR descricao LIKE ? ORDER BY cod LIMIT ?",
        (like, like, limite),
    )


def posicao_estoque_df(operacao_id: int) -> pd.DataFrame:
    """Estoque + cadastro do produto + linear + meta DOI numa só tabela."""
    return query_df("""
        SELECT e.cod, COALESCE(p.descricao, e.descricao) AS descricao,
               p.tipo, p.categoria,
               e.inicial, e.entrada, e.saida, e.disponivel,
               COALESCE(p.fator_hl, 0)  AS fator_hl,
               COALESCE(p.cx_pallet, 0) AS cx_pallet,
               COALESCE(l.linear_cx_dia, 0) AS linear_cx_dia,
               COALESCE(m.doi_meta, 7.0) AS doi_meta,
               e.dt_atualizacao
        FROM estoque e
        LEFT JOIN produtos p      ON p.cod = e.cod
        LEFT JOIN linear_vendas l ON l.operacao_id = e.operacao_id AND l.cod = e.cod
        LEFT JOIN metas_doi m     ON m.operacao_id = e.operacao_id AND m.cod = e.cod
        WHERE e.operacao_id = ?
        ORDER BY e.cod
    """, (operacao_id,))


def salvar_meta_doi(operacao_id: int, cod: int, doi: float) -> None:
    execute("""
        INSERT INTO metas_doi (operacao_id, cod, doi_meta) VALUES (?, ?, ?)
        ON CONFLICT(operacao_id, cod) DO UPDATE SET doi_meta = excluded.doi_meta
    """, (operacao_id, cod, doi))


def curva_abc_df(operacao_id: int, mes_ano: str | None = None) -> pd.DataFrame:
    sql, p = "SELECT * FROM curva_abc WHERE operacao_id = ?", [operacao_id]
    if mes_ano:
        sql += " AND mes_ano = ?"
        p.append(mes_ano)
    return query_df(sql + " ORDER BY mes_ano DESC, total_qtde DESC", p)


def meses_curva_abc(operacao_id: int) -> list[str]:
    df = query_df("SELECT DISTINCT mes_ano FROM curva_abc WHERE operacao_id = ? ORDER BY mes_ano DESC",
                  (operacao_id,))
    return df["mes_ano"].tolist()
