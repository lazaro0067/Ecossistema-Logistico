"""Regras de negócio: usuários, senhas e permissões por pasta."""
import secrets

from config.settings import MODULOS, PERFIS
from core.auth import hash_senha, verificar_senha
from database.connection import tipo_violacao
from repositories import usuarios_repo
from services.erros import RegraNegocioError

SENHA_MINIMA = 6


def permissoes_validas(permissoes: list[str]) -> list[str]:
    """Mantém só chaves existentes; se a pasta inteira foi dada, descarta as abas dela."""
    ok = set()
    for p in permissoes:
        mod, _, aba = p.partition(".")
        if mod in MODULOS and (not aba or aba in MODULOS[mod]["abas"]):
            ok.add(p)
    inteiras = {p for p in ok if "." not in p}
    return sorted(p for p in ok if "." not in p or p.split(".")[0] not in inteiras)


def _checar_senha(senha: str) -> None:
    if len(senha) < SENHA_MINIMA:
        raise RegraNegocioError(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")


def salvar_usuario(*, id: int | None, login: str, nome: str, senha: str, email: str, cargo: str,
                   perfil: str, e_aprovador: bool, alcada: float, ativo: bool, trocar_senha: bool,
                   permissoes: list[str], operacoes: list[int]) -> int:
    login, nome = login.strip().lower(), nome.strip()
    if not login or not nome:
        raise RegraNegocioError("Login e nome são obrigatórios.")
    if " " in login:
        raise RegraNegocioError("O login não pode ter espaços (ex.: joao.silva).")
    if perfil not in PERFIS:
        raise RegraNegocioError("Perfil inválido.")
    if not id or senha:
        _checar_senha(senha)
    if e_aprovador and alcada <= 0:
        raise RegraNegocioError("Informe a alçada (R$) do aprovador.")
    if perfil != "Master" and not permissoes:
        raise RegraNegocioError("Libere pelo menos uma pasta para o usuário.")

    dados = dict(id=id, login=login, nome=nome, email=email.strip(), cargo=cargo.strip(), perfil=perfil,
                 e_aprovador=int(e_aprovador), alcada=float(alcada if e_aprovador else 0),
                 ativo=int(ativo), trocar_senha=int(trocar_senha))
    try:
        return usuarios_repo.salvar(dados, permissoes_validas(permissoes), operacoes,
                                    hash_senha(senha) if senha else None)
    except Exception as e:
        if tipo_violacao(e) == "unica":
            raise RegraNegocioError(f"Já existe um usuário com o login '{login}'.")
        raise


def gerar_senha_provisoria() -> str:
    return "Lima" + secrets.token_hex(3)


def resetar_senha(usuario_id: int) -> str:
    """Gera senha provisória; o usuário é obrigado a trocar no próximo acesso."""
    nova = gerar_senha_provisoria()
    usuarios_repo.trocar_senha(usuario_id, hash_senha(nova), exigir_troca=True)
    return nova


def trocar_propria_senha(usuario_id: int, senha_atual: str | None, nova: str, confirmacao: str) -> None:
    """senha_atual=None é usado na troca obrigatória logo após o login."""
    u = usuarios_repo.buscar(usuario_id)
    if senha_atual is not None and not verificar_senha(senha_atual, u["senha_hash"]):
        raise RegraNegocioError("Senha atual incorreta.")
    _checar_senha(nova)
    if nova != confirmacao:
        raise RegraNegocioError("A confirmação não confere com a nova senha.")
    if verificar_senha(nova, u["senha_hash"]):
        raise RegraNegocioError("A nova senha precisa ser diferente da atual.")
    usuarios_repo.trocar_senha(usuario_id, hash_senha(nova), exigir_troca=False)
