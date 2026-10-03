"""Regras de negócio: usuários e acessos."""
import sqlite3

from config.settings import MODULOS, PERFIS
from core.auth import hash_senha, verificar_senha
from repositories import usuarios_repo
from services.erros import RegraNegocioError


def salvar_usuario(*, id: int | None, login: str, nome: str, senha: str, email: str, cargo: str,
                   perfil: str, e_aprovador: bool, alcada: float, ativo: bool,
                   modulos: list[str], operacoes: list[int]) -> int:
    login, nome = login.strip().lower(), nome.strip()
    if not login or not nome:
        raise RegraNegocioError("Login e nome são obrigatórios.")
    if perfil not in PERFIS:
        raise RegraNegocioError("Perfil inválido.")
    if not id and len(senha) < 6:
        raise RegraNegocioError("A senha precisa ter pelo menos 6 caracteres.")
    if id and senha and len(senha) < 6:
        raise RegraNegocioError("A nova senha precisa ter pelo menos 6 caracteres.")
    if e_aprovador and alcada <= 0:
        raise RegraNegocioError("Informe a alçada (R$) do aprovador.")
    modulos = [m for m in modulos if m in MODULOS]

    dados = dict(id=id, login=login, nome=nome, email=email.strip(), cargo=cargo.strip(),
                 perfil=perfil, e_aprovador=int(e_aprovador), alcada=float(alcada if e_aprovador else 0),
                 ativo=int(ativo))
    try:
        return usuarios_repo.salvar(dados, modulos, operacoes, hash_senha(senha) if senha else None)
    except sqlite3.IntegrityError:
        raise RegraNegocioError(f"Já existe um usuário com o login '{login}'.")


def trocar_propria_senha(usuario_id: int, senha_atual: str, nova: str, confirmacao: str) -> None:
    u = usuarios_repo.buscar(usuario_id)
    if not verificar_senha(senha_atual, u["senha_hash"]):
        raise RegraNegocioError("Senha atual incorreta.")
    if len(nova) < 6:
        raise RegraNegocioError("A nova senha precisa ter pelo menos 6 caracteres.")
    if nova != confirmacao:
        raise RegraNegocioError("A confirmação não confere com a nova senha.")
    usuarios_repo.trocar_senha(usuario_id, hash_senha(nova))
