"""Acesso a dados: usuários, permissões (pastas/abas) e operações permitidas."""
import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_all, query_df, query_one


def buscar_por_login(login: str) -> dict | None:
    return query_one("SELECT * FROM usuarios WHERE login = ?", (login,))


def buscar(usuario_id: int) -> dict | None:
    return query_one("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))


def carregar_sessao(usuario_id: int) -> dict:
    u = buscar(usuario_id)
    u.pop("senha_hash", None)
    u["modulos"] = [r["modulo"] for r in query_all(
        "SELECT modulo FROM usuario_modulos WHERE usuario_id = ?", (usuario_id,))]
    u["operacoes"] = [r["operacao_id"] for r in query_all(
        "SELECT operacao_id FROM usuario_operacoes WHERE usuario_id = ?", (usuario_id,))]
    return u


def registrar_acesso(usuario_id: int) -> None:
    execute("UPDATE usuarios SET ultimo_acesso = ? WHERE id = ?", (tempo.agora_str(), usuario_id))


def listar_df() -> pd.DataFrame:
    return query_df("""
        SELECT u.id, u.login, u.nome, u.cargo, u.perfil,
               CASE u.ativo WHEN 1 THEN 'Ativo' ELSE 'Inativo' END AS situacao,
               CASE u.e_aprovador WHEN 1 THEN 'Sim' ELSE 'Não' END AS aprovador,
               u.alcada, u.ultimo_acesso,
               (SELECT COUNT(*) FROM usuario_modulos m WHERE m.usuario_id = u.id) AS pastas,
               COALESCE((SELECT group_concat(o.nome, ', ') FROM usuario_operacoes uo
                         JOIN operacoes o ON o.id = uo.operacao_id WHERE uo.usuario_id = u.id), 'Todas') AS operacoes
        FROM usuarios u ORDER BY u.ativo DESC, u.nome
    """)


def listar(apenas_ativos: bool = True) -> list[dict]:
    sql = "SELECT id, login, nome, perfil, e_aprovador, alcada, ativo FROM usuarios"
    if apenas_ativos:
        sql += " WHERE ativo = 1"
    return query_all(sql + " ORDER BY nome")


def listar_aprovadores() -> list[dict]:
    return query_all(
        "SELECT id, nome, alcada FROM usuarios WHERE e_aprovador = 1 AND ativo = 1 ORDER BY nome")


def salvar(dados: dict, permissoes: list[str], operacoes: list[int], senha_hash: str | None = None) -> int:
    """Insere (sem `id`) ou atualiza (com `id`) e regrava permissões/operações."""
    with get_conn() as conn:
        campos = ("login", "nome", "email", "cargo", "perfil", "e_aprovador", "alcada", "ativo", "trocar_senha")
        valores = [dados[c] for c in campos]
        if dados.get("id"):
            uid = dados["id"]
            conn.execute(f"UPDATE usuarios SET {', '.join(c + ' = ?' for c in campos)} WHERE id = ?",
                         (*valores, uid))
            if senha_hash:
                conn.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (senha_hash, uid))
        else:
            cur = conn.execute(
                f"INSERT INTO usuarios ({', '.join(campos)}, senha_hash) VALUES ({', '.join('?' * (len(campos) + 1))})",
                (*valores, senha_hash),
            )
            uid = cur.lastrowid

        conn.execute("DELETE FROM usuario_modulos WHERE usuario_id = ?", (uid,))
        if permissoes:
            conn.executemany("INSERT INTO usuario_modulos (usuario_id, modulo) VALUES (?, ?)",
                             [(uid, p) for p in sorted(set(permissoes))])
        conn.execute("DELETE FROM usuario_operacoes WHERE usuario_id = ?", (uid,))
        if operacoes:
            conn.executemany("INSERT INTO usuario_operacoes (usuario_id, operacao_id) VALUES (?, ?)",
                             [(uid, o) for o in operacoes])
        return uid


def trocar_senha(usuario_id: int, senha_hash: str, exigir_troca: bool = False) -> None:
    execute("UPDATE usuarios SET senha_hash = ?, trocar_senha = ? WHERE id = ?",
            (senha_hash, int(exigir_troca), usuario_id))
