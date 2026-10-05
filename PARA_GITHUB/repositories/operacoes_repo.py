"""Acesso a dados: operações (unidades/filiais da revenda)."""
from database.connection import execute, query_all, query_one


def listar(apenas_ativas: bool = False) -> list[dict]:
    sql = "SELECT * FROM operacoes"
    if apenas_ativas:
        sql += " WHERE ativo = 1"
    return query_all(sql + " ORDER BY CASE WHEN membros IS NULL THEN 0 ELSE 1 END, nome")


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


# --- Operações consolidadas (ex.: Bahia = Barreiras + São Félix) ----------
def ids_efetivos(operacao_id: int) -> list[int]:
    """Filiais que compõem a operação (ela mesma, ou os membros se for consolidada)."""
    op = buscar(operacao_id)
    if op and op.get("membros"):
        return [int(x) for x in str(op["membros"]).split(",") if x.strip()]
    return [operacao_id]


def e_consolidada(operacao_id: int | None) -> bool:
    if not operacao_id:
        return False
    op = buscar(operacao_id)
    return bool(op and op.get("membros"))


def filtro(coluna: str, operacao_id: int) -> tuple[str, list[int]]:
    """Trecho SQL 'coluna IN (?, ?)' + parâmetros, já considerando consolidadas."""
    ids = ids_efetivos(operacao_id)
    return f"{coluna} IN ({', '.join('?' * len(ids))})", ids


def resolver_por_texto(texto: str) -> int | None:
    """Acha a filial a partir do nome escrito no relatório (ex.: 'Lima Bahia Samavi')."""
    from config.settings import APELIDOS_OPERACAO
    import unicodedata

    def norm(t):
        return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower().strip()

    alvo = norm(texto)
    pares = sorted(((norm(a), nome) for nome, aps in APELIDOS_OPERACAO.items() for a in [nome, *aps]),
                   key=lambda x: -len(x[0]))
    for apelido, nome in pares:
        if apelido and apelido in alvo:
            op = buscar_por_nome(nome)
            return op["id"] if op else None
    op = buscar_por_nome(str(texto).strip())
    return op["id"] if op else None
