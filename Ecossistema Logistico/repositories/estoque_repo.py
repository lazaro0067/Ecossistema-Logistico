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
    """Estoque + cadastro do produto + linear + meta DOI. Consolidadas somam as filiais."""
    from repositories import operacoes_repo

    ids = operacoes_repo.ids_efetivos(operacao_id)
    if len(ids) == 1:
        return _posicao_filial(ids[0])
    partes = [p for p in (_posicao_filial(i) for i in ids) if not p.empty]
    if not partes:
        return _posicao_filial(ids[0])
    df = pd.concat(partes)
    soma = ["inicial", "entrada", "saida", "disponivel", "linear_cx_dia"]
    primeiro = ["descricao", "tipo", "categoria", "fator_hl", "cx_pallet", "dt_atualizacao"]
    return (df.groupby("cod", as_index=False)
              .agg(**{c: (c, "sum") for c in soma}, **{c: (c, "first") for c in primeiro}, doi_meta=("doi_meta", "mean")))


def _posicao_filial(operacao_id: int) -> pd.DataFrame:
    df = _estoque_filial(operacao_id)
    if df.empty:
        return df
    # produto com venda na linear e fora da grade de estoque (02.03.04) = Stock Out (disponível 0)
    fora = query_df("""
        SELECT l.cod, COALESCE(p.descricao, 'Cód ' || CAST(l.cod AS TEXT)) AS descricao, p.tipo, p.categoria,
               0 AS inicial, 0 AS entrada, 0 AS saida, 0 AS disponivel,
               COALESCE(p.fator_hl, 0) AS fator_hl, COALESCE(p.cx_pallet, 0) AS cx_pallet,
               l.linear_cx_dia, COALESCE(m.doi_meta, 7.0) AS doi_meta, NULL AS dt_atualizacao
        FROM linear_vendas l
        LEFT JOIN produtos p  ON p.cod = l.cod
        LEFT JOIN metas_doi m ON m.operacao_id = l.operacao_id AND m.cod = l.cod
        WHERE l.operacao_id = ? AND COALESCE(l.linear_cx_dia, 0) > 0
          AND NOT EXISTS (SELECT 1 FROM estoque e WHERE e.operacao_id = l.operacao_id AND e.cod = l.cod)
    """, (operacao_id,))
    if fora.empty:
        return df
    return pd.concat([df, fora], ignore_index=True).sort_values("cod").reset_index(drop=True)


def _estoque_filial(operacao_id: int) -> pd.DataFrame:
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
    from repositories import operacoes_repo
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, p = f"SELECT * FROM curva_abc WHERE {f_sql}", list(ids)
    if mes_ano:
        sql += " AND mes_ano = ?"
        p.append(mes_ano)
    return query_df(sql + " ORDER BY mes_ano DESC, total_qtde DESC", p)


def meses_curva_abc(operacao_id: int) -> list[str]:
    from repositories import operacoes_repo
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT DISTINCT mes_ano FROM curva_abc WHERE {f_sql} ORDER BY mes_ano DESC", ids)
    return df["mes_ano"].tolist()
