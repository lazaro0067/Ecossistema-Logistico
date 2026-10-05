"""Acesso a dados: cadastro completo dos motoristas, valor da viagem por fábrica e notificações."""
import pandas as pd

from database.connection import execute, query_all, query_df, query_one
from repositories import operacoes_repo


# --- Motoristas ---------------------------------------------------------------
def lista_df(operacao_id: int) -> pd.DataFrame:
    """Motoristas com acesso ao app, gestor responsável e dados da CNH."""
    return query_df("""SELECT m.id, m.nome, m.cpf, m.telefone, m.cnh, m.cnh_validade, m.salario_fixo,
                              m.gestor_id, g.nome AS gestor, m.usuario_id, u.login AS acesso,
                              CASE WHEN u.id IS NULL THEN 'Sem acesso' WHEN u.ativo = 1 THEN 'Ativo'
                                   ELSE 'Bloqueado' END AS situacao_acesso,
                              u.ultimo_acesso
                       FROM motoristas m
                       LEFT JOIN usuarios u ON u.id = m.usuario_id
                       LEFT JOIN usuarios g ON g.id = m.gestor_id
                       WHERE m.operacao_id = ? ORDER BY m.nome""", (operacao_id,))


def todos_com_cnh() -> list[dict]:
    """Todos os motoristas (todas as filiais) com validade de CNH — para os alertas."""
    return query_all("""SELECT m.id, m.nome, m.cnh, m.cnh_validade, m.gestor_id, m.operacao_id, o.nome AS operacao
                        FROM motoristas m JOIN operacoes o ON o.id = m.operacao_id
                        WHERE m.cnh_validade IS NOT NULL AND m.cnh_validade <> ''""")


def gestores() -> list[dict]:
    """Quem pode ser gestor responsável: usuários ativos que não são motoristas."""
    return query_all("SELECT id, nome, email, perfil FROM usuarios WHERE ativo = 1 AND perfil <> 'Motorista' "
                     "ORDER BY nome")


def masters() -> list[dict]:
    return query_all("SELECT id, nome, email FROM usuarios WHERE ativo = 1 AND perfil = 'Master'")


# --- Valor da viagem por fábrica (por filial) --------------------------------------
def valores_viagem(operacao_id: int) -> dict[int, float]:
    return {r["fabrica_id"]: float(r["valor_viagem"] or 0) for r in query_all(
        "SELECT fabrica_id, valor_viagem FROM remuneracao_fabrica WHERE operacao_id = ?", (operacao_id,))}


def salvar_valor_viagem(operacao_id: int, fabrica_id: int, valor: float) -> None:
    if query_one("SELECT id FROM remuneracao_fabrica WHERE operacao_id = ? AND fabrica_id = ?",
                 (operacao_id, fabrica_id)):
        execute("UPDATE remuneracao_fabrica SET valor_viagem = ? WHERE operacao_id = ? AND fabrica_id = ?",
                (valor, operacao_id, fabrica_id))
    else:
        execute("INSERT INTO remuneracao_fabrica (operacao_id, fabrica_id, valor_viagem) VALUES (?, ?, ?)",
                (operacao_id, fabrica_id, valor))


def viagens_mes(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    """Viagens do mês (pedidos vinculados — manuais e do App Carreteiro)."""
    f_sql, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"""SELECT id, data_puxada, numero_pedido, placa, fabrica, motorista, notas_fiscais, viagem_id
                        FROM vinculos_pedidos WHERE {f_sql} AND substr(data_puxada, 1, 7) = ?
                        ORDER BY data_puxada, id""", [*p, mes_ano])


# --- Notificações --------------------------------------------------------------------
def criar_notificacao(usuario_id: int, tipo: str, chave: str, titulo: str, texto: str, pagina: str | None,
                      quando: str) -> int:
    return execute("""INSERT INTO notificacoes (usuario_id, tipo, chave, titulo, texto, pagina, criado_em)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""", (usuario_id, tipo, chave, titulo, texto, pagina, quando))


def ultima_notificacao(usuario_id: int, chave: str) -> dict | None:
    return query_one("SELECT * FROM notificacoes WHERE usuario_id = ? AND chave = ? ORDER BY criado_em DESC LIMIT 1",
                     (usuario_id, chave))


def notificacoes(usuario_id: int, apenas_nao_lidas: bool = False, limite: int = 100) -> list[dict]:
    sql = "SELECT * FROM notificacoes WHERE usuario_id = ?"
    if apenas_nao_lidas:
        sql += " AND lida_em IS NULL"
    return query_all(sql + " ORDER BY criado_em DESC, id DESC LIMIT ?", (usuario_id, limite))


def nao_lidas(usuario_id: int) -> int:
    r = query_one("SELECT COUNT(*) AS n FROM notificacoes WHERE usuario_id = ? AND lida_em IS NULL", (usuario_id,))
    return int(r["n"]) if r else 0


def marcar_lida(usuario_id: int, nid: int | None, quando: str) -> None:
    if nid:
        execute("UPDATE notificacoes SET lida_em = ? WHERE id = ? AND usuario_id = ?", (quando, nid, usuario_id))
    else:
        execute("UPDATE notificacoes SET lida_em = ? WHERE usuario_id = ? AND lida_em IS NULL", (quando, usuario_id))
