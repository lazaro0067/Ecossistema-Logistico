"""Funções genéricas de gravação em lote (usadas pelas importações)."""
from database.connection import get_conn


def upsert(tabela: str, linhas: list[dict], chaves: list[str]) -> int:
    """Insere ou atualiza várias linhas de uma vez. `chaves` = colunas únicas."""
    if not linhas:
        return 0
    colunas = list(linhas[0].keys())
    atualizar = [c for c in colunas if c not in chaves]
    sql = (
        f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))}) "
        f"ON CONFLICT({', '.join(chaves)}) DO "
        + (f"UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in atualizar)}" if atualizar else "NOTHING")
    )
    with get_conn() as conn:
        conn.executemany(sql, [tuple(l[c] for c in colunas) for l in linhas])
    return len(linhas)


def inserir_lote(tabela: str, linhas: list[dict]) -> int:
    if not linhas:
        return 0
    colunas = list(linhas[0].keys())
    with get_conn() as conn:
        conn.executemany(
            f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
            [tuple(l[c] for c in colunas) for l in linhas],
        )
    return len(linhas)


def apagar_onde(tabela: str, filtro: str, params: tuple) -> int:
    with get_conn() as conn:
        return conn.execute(f"DELETE FROM {tabela} WHERE {filtro}", params).rowcount


def substituir(tabela: str, filtro: str, params: tuple, linhas: list[dict], chaves: list[str] | None) -> int:
    """Apaga o recorte e grava as novas linhas numa única transação (tudo ou nada)."""
    if not linhas:
        return 0
    colunas = list(linhas[0].keys())
    with get_conn() as conn:
        conn.execute(f"DELETE FROM {tabela} WHERE {filtro}", params)
        conn.executemany(
            f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
            [tuple(l[c] for c in colunas) for l in linhas],
        )
    return len(linhas)


def registrar_log(operacao_id, base: str, linhas: int, arquivo: str, usuario: str) -> None:
    from core import tempo

    with get_conn() as conn:
        conn.execute("INSERT INTO bases_log (operacao_id, base, linhas, arquivo, usuario, dt) VALUES (?, ?, ?, ?, ?, ?)",
                     (operacao_id, base, linhas, arquivo, usuario, tempo.agora_str()))
