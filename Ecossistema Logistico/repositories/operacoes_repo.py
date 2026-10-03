"""Acesso a dados: operações (unidades/filiais da revenda)."""
from database.connection import execute, query_all, query_one


def listar(apenas_ativas: bool = False) -> list[dict]:
    sql = "SELECT * FROM operacoes"
    if apenas_ativas:
        sql += " WHERE ativo = 1"
    return query_all(sql + " ORDER BY nome")


def buscar(operacao_id: int) -> dict | None:
    return query_one("SELECT * FROM operacoes WHERE id = ?", (operacao_id,))


def buscar_por_nome(nome: str) -> dict | None:
    return query_one("SELECT * FROM operacoes WHERE nome = ?", (nome,))


def inserir(nome: str, cnpj: str, cidade: str, uf: str) -> int:
    return execute(
        "INSERT INTO operacoes (nome, cnpj, cidade, uf) VALUES (?, ?, ?, ?)",
        (nome, cnpj, cidade, uf.upper()),
    )


def atualizar(operacao_id: int, nome: str, cnpj: str, cidade: str, uf: str, ativo: bool) -> None:
    execute(
        "UPDATE operacoes SET nome=?, cnpj=?, cidade=?, uf=?, ativo=? WHERE id=?",
        (nome, cnpj, cidade, uf.upper(), int(ativo), operacao_id),
    )
