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
               t.tipo, t.distancia_km, t.pedagio, t.valor_remunerado, t.valor_frete,
               t.origem_id, t.destino_id, t.transportadora_id, t.aprovador_id
        FROM trechos t
        JOIN origens_destinos o ON o.id = t.origem_id
        JOIN origens_destinos d ON d.id = t.destino_id
        LEFT JOIN transportadoras tr ON tr.id = t.transportadora_id
        LEFT JOIN usuarios u ON u.id = t.aprovador_id
        WHERE t.operacao_id = ? ORDER BY o.nome, d.nome, tr.nome, t.tipo
    """, (operacao_id,))


def buscar_trecho(operacao_id: int, origem_id: int, destino_id: int, transportadora_id: int | None = None,
                  tipo: str | None = None) -> dict | None:
    """Trecho mais específico: mesma transportadora e tipo; senão o genérico (sem transportadora/tipo)."""
    linhas = query_all("SELECT * FROM trechos WHERE operacao_id = ? AND origem_id = ? AND destino_id = ?",
                       (operacao_id, origem_id, destino_id))

    def nota(t):
        tr, tp = t.get("transportadora_id"), t.get("tipo")
        if transportadora_id and tr and tr != transportadora_id:
            return -1
        if tipo and tp and tp != tipo:
            return -1
        return (2 if transportadora_id and tr == transportadora_id else 0) + (1 if tipo and tp == tipo else 0)

    validos = sorted(((nota(t), t) for t in linhas), key=lambda x: -x[0])
    return validos[0][1] if validos and validos[0][0] >= 0 else None


def trecho_igual(operacao_id: int, origem_id: int, destino_id: int, transportadora_id: int | None,
                 tipo: str | None, ignorar_id: int | None = None) -> dict | None:
    for t in query_all("SELECT * FROM trechos WHERE operacao_id = ? AND origem_id = ? AND destino_id = ?",
                       (operacao_id, origem_id, destino_id)):
        if t["id"] != ignorar_id and (t.get("transportadora_id") or None) == (transportadora_id or None) \
                and (t.get("tipo") or None) == (tipo or None):
            return t
    return None


def salvar_trecho(operacao_id: int, origem_id: int, destino_id: int, km: float,
                  pedagio: float, remunerado: float, frete: float,
                  transportadora_id: int | None = None, aprovador_id: int | None = None,
                  tipo: str | None = None, trecho_id: int | None = None) -> None:
    """Grava pelo id (alteração) ou pela chave origem + destino + transportadora + tipo."""
    alvo = trecho_id or (trecho_igual(operacao_id, origem_id, destino_id, transportadora_id, tipo) or {}).get("id")
    if alvo:
        execute("""UPDATE trechos SET origem_id = ?, destino_id = ?, distancia_km = ?, pedagio = ?, valor_remunerado = ?,
                   valor_frete = ?, transportadora_id = ?, aprovador_id = ?, tipo = ? WHERE id = ?""",
                (origem_id, destino_id, km, pedagio, remunerado, frete, transportadora_id, aprovador_id, tipo, alvo))
    else:
        execute("""INSERT INTO trechos (operacao_id, origem_id, destino_id, distancia_km, pedagio, valor_remunerado,
                   valor_frete, transportadora_id, aprovador_id, tipo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (operacao_id, origem_id, destino_id, km, pedagio, remunerado, frete, transportadora_id, aprovador_id,
                 tipo))


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


# --- Metas mensais por centro de custo ---------------------------------------------
def metas_centro_custo_df(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    """Centros de custo com a meta do mês e o realizado (frete spot aprovado/finalizado do mês)."""
    return query_df("""
        SELECT cc.id, cc.nome,
               COALESCE((SELECT m.valor_meta FROM metas_centro_custo m WHERE m.centro_custo_id = cc.id
                         AND m.operacao_id = ? AND m.mes_ano = ?), 0) AS meta,
               COALESCE((SELECT SUM(c.valor_negociado) FROM cotacoes_frete c WHERE c.centro_custo_id = cc.id
                         AND c.operacao_id = ? AND substr(c.data_frete, 1, 7) = ?
                         AND c.status IN ('Aprovado', 'Finalizado')), 0) AS realizado
        FROM centros_custo cc ORDER BY cc.nome""", (operacao_id, mes_ano, operacao_id, mes_ano))


def salvar_meta_centro_custo(operacao_id: int, cc_id: int, mes_ano: str, valor: float) -> None:
    if query_one("SELECT id FROM metas_centro_custo WHERE operacao_id = ? AND centro_custo_id = ? AND mes_ano = ?",
                 (operacao_id, cc_id, mes_ano)):
        execute("UPDATE metas_centro_custo SET valor_meta = ? WHERE operacao_id = ? AND centro_custo_id = ? "
                "AND mes_ano = ?", (valor, operacao_id, cc_id, mes_ano))
    else:
        execute("INSERT INTO metas_centro_custo (operacao_id, centro_custo_id, mes_ano, valor_meta) "
                "VALUES (?, ?, ?, ?)", (operacao_id, cc_id, mes_ano, valor))
