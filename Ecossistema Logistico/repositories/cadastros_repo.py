"""Acesso a dados: cadastros de apoio da Puxada."""
import pandas as pd

from database.connection import execute, query_all, query_df, query_one


# --- Transportadoras ------------------------------------------------------
def listar_transportadoras() -> list[dict]:
    return query_all("SELECT * FROM transportadoras ORDER BY nome")


def inserir_transportadora(nome: str, cnpj: str, contato: str) -> int:
    return execute("INSERT INTO transportadoras (nome, cnpj, contato) VALUES (?, ?, ?)",
                   (nome, cnpj, contato))


def excluir_transportadora(tid: int) -> None:
    execute("DELETE FROM transportadoras WHERE id = ?", (tid,))


# --- Centros de custo -----------------------------------------------------
def listar_centros_custo() -> list[dict]:
    return query_all("SELECT * FROM centros_custo ORDER BY nome")


def inserir_centro_custo(nome: str) -> int:
    return execute("INSERT INTO centros_custo (nome) VALUES (?)", (nome,))


def excluir_centro_custo(cid: int) -> None:
    execute("DELETE FROM centros_custo WHERE id = ?", (cid,))


# --- Origens / Destinos ---------------------------------------------------
def listar_od(operacao_id: int, papel: str | None = None) -> list[dict]:
    """papel = 'origem' | 'destino' | None (todas)."""
    sql = "SELECT * FROM origens_destinos WHERE operacao_id = ?"
    if papel == "origem":
        sql += " AND tipo IN ('Origem e destino', 'Apenas Origem')"
    elif papel == "destino":
        sql += " AND tipo IN ('Origem e destino', 'Apenas Destino')"
    return query_all(sql + " ORDER BY nome", (operacao_id,))


def inserir_od(operacao_id: int, nome: str, cidade: str, uf: str, tipo: str) -> int:
    return execute(
        "INSERT INTO origens_destinos (operacao_id, nome, cidade, uf, tipo) VALUES (?, ?, ?, ?, ?)",
        (operacao_id, nome, cidade, uf.upper(), tipo),
    )


def excluir_od(od_id: int) -> None:
    execute("DELETE FROM origens_destinos WHERE id = ?", (od_id,))


# --- Trechos --------------------------------------------------------------
def listar_trechos_df(operacao_id: int) -> pd.DataFrame:
    return query_df("""
        SELECT t.id, o.nome AS origem, d.nome AS destino, tr.nome AS transportadora, u.nome AS aprovador,
               t.distancia_km, t.pedagio, t.valor_remunerado, t.valor_frete,
               t.origem_id, t.destino_id, t.transportadora_id, t.aprovador_id
        FROM trechos t
        JOIN origens_destinos o ON o.id = t.origem_id
        JOIN origens_destinos d ON d.id = t.destino_id
        LEFT JOIN transportadoras tr ON tr.id = t.transportadora_id
        LEFT JOIN usuarios u ON u.id = t.aprovador_id
        WHERE t.operacao_id = ? ORDER BY o.nome, d.nome
    """, (operacao_id,))


def buscar_trecho(operacao_id: int, origem_id: int, destino_id: int) -> dict | None:
    return query_one(
        "SELECT * FROM trechos WHERE operacao_id = ? AND origem_id = ? AND destino_id = ?",
        (operacao_id, origem_id, destino_id),
    )


def salvar_trecho(operacao_id: int, origem_id: int, destino_id: int, km: float,
                  pedagio: float, remunerado: float, frete: float,
                  transportadora_id: int | None = None, aprovador_id: int | None = None) -> None:
    execute("""
        INSERT INTO trechos (operacao_id, origem_id, destino_id, distancia_km, pedagio, valor_remunerado, valor_frete,
                             transportadora_id, aprovador_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(operacao_id, origem_id, destino_id) DO UPDATE SET
            distancia_km = excluded.distancia_km, pedagio = excluded.pedagio,
            valor_remunerado = excluded.valor_remunerado, valor_frete = excluded.valor_frete,
            transportadora_id = excluded.transportadora_id, aprovador_id = excluded.aprovador_id
    """, (operacao_id, origem_id, destino_id, km, pedagio, remunerado, frete, transportadora_id, aprovador_id))


def excluir_trecho(trecho_id: int) -> None:
    execute("DELETE FROM trechos WHERE id = ?", (trecho_id,))


# --- Alterações ---------------------------------------------------------------
def atualizar_transportadora(tid: int, nome: str, cnpj: str, contato: str) -> None:
    execute("UPDATE transportadoras SET nome = ?, cnpj = ?, contato = ? WHERE id = ?", (nome, cnpj, contato, tid))


def atualizar_centro_custo(cid: int, nome: str) -> None:
    execute("UPDATE centros_custo SET nome = ? WHERE id = ?", (nome, cid))


def atualizar_od(od_id: int, nome: str, cidade: str, uf: str, tipo: str) -> None:
    execute("UPDATE origens_destinos SET nome = ?, cidade = ?, uf = ?, tipo = ? WHERE id = ?",
            (nome, cidade, uf.upper(), tipo, od_id))
