"""Gente › 👔 Gestores — cadastro dos gestores (donos de departamento e de contas do OBZ).

Depois de cadastrado, o gestor pode ganhar acesso ao sistema (vira usuário, perfil Gestor) e ser vinculado como
dono de um departamento do OBZ e sub-dono de contas (🎯 Gestão OBZ › ⚙️ Cadastros › 🌳 Árvore de donos).
"""
import pandas as pd

from core import tempo
from database.connection import execute, query_df, query_one
from services.erros import RegraNegocioError

PERMISSOES_GESTOR = ["financeiro.obz_gestao", "financeiro.obz_tend", "financeiro.obz_reuniao",
                     "financeiro.obz_aprov"]


def listar(so_ativos: bool = False) -> pd.DataFrame:
    df = query_df("""SELECT g.*, u.email AS login_acesso, u.ativo AS acesso_ativo FROM gestores g
                     LEFT JOIN usuarios u ON u.id = g.usuario_id""" + (" WHERE g.ativo = 1" if so_ativos else "")
                  + " ORDER BY g.nome")
    return df


def nomes() -> dict[int, str]:
    df = listar(so_ativos=True)
    return {int(i): n for i, n in zip(df["id"], df["nome"])}


def buscar(gid: int) -> dict | None:
    return query_one("SELECT * FROM gestores WHERE id = ?", (int(gid),))


def salvar(gid: int | None, nome: str, cargo: str = "", email: str = "", telefone: str = "",
           departamento: str = "", ativo: bool = True) -> int:
    nome = (nome or "").strip()
    if not nome:
        raise RegraNegocioError("Informe o nome do gestor.")
    dados = (nome, (cargo or "").strip(), (email or "").strip().lower(), (telefone or "").strip(),
             (departamento or "").strip(), 1 if ativo else 0)
    if gid:
        execute("UPDATE gestores SET nome = ?, cargo = ?, email = ?, telefone = ?, departamento = ?, ativo = ? "
                "WHERE id = ?", (*dados, int(gid)))
        return int(gid)
    return execute("INSERT INTO gestores (nome, cargo, email, telefone, departamento, ativo, criado_em) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", (*dados, tempo.agora().strftime("%Y-%m-%d %H:%M")))


def excluir(gid: int) -> None:
    execute("DELETE FROM obz_resp WHERE gestor_id = ?", (int(gid),))
    execute("UPDATE obz_areas SET dono_gestor_id = NULL WHERE dono_gestor_id = ?", (int(gid),))
    execute("DELETE FROM gestores WHERE id = ?", (int(gid),))


def criar_acesso(gid: int, operacoes: list[int], enviar_email: bool = True) -> dict:
    """Cria o usuário do gestor (login = e-mail) com acesso à Gestão OBZ e vincula ao cadastro."""
    from services import usuarios_service

    g = buscar(gid)
    if not g:
        raise RegraNegocioError("Gestor não encontrado.")
    if g.get("usuario_id"):
        raise RegraNegocioError("Este gestor já tem acesso.")
    if not g.get("email"):
        raise RegraNegocioError("Cadastre o e-mail do gestor antes de criar o acesso (é o login).")
    r = usuarios_service.salvar_usuario(id=None, nome=g["nome"], senha="", email=g["email"],
                                        cargo=g.get("cargo") or "Gestor", perfil="Gestor", e_aprovador=False,
                                        alcada=0.0, ativo=True, trocar_senha=True, permissoes=PERMISSOES_GESTOR,
                                        operacoes=operacoes, enviar_email=enviar_email)
    execute("UPDATE gestores SET usuario_id = ? WHERE id = ?", (r["id"], int(gid)))
    return r


def vincular_usuario(gid: int, usuario_id: int | None) -> None:
    execute("UPDATE gestores SET usuario_id = ? WHERE id = ?", (usuario_id, int(gid)))


def gestor_do_usuario(usuario_id: int) -> int | None:
    r = query_one("SELECT id FROM gestores WHERE usuario_id = ? AND ativo = 1", (int(usuario_id),))
    return int(r["id"]) if r else None
