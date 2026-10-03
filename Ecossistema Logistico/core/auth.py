"""Autenticação e permissões.

Senhas são guardadas com PBKDF2-SHA256 + salt (nunca em texto puro).
"""
import hashlib
import hmac
import secrets

from config.settings import PERFIL_MASTER

_ITERACOES = 200_000


def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), _ITERACOES)
    return f"pbkdf2${_ITERACOES}${salt}${dk.hex()}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        _, it, salt, h = senha_hash.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), h)
    except (ValueError, AttributeError):
        return False


def autenticar(login: str, senha: str) -> dict | None:
    """Devolve o usuário (com módulos e operações) ou None."""
    from repositories import usuarios_repo

    usuario = usuarios_repo.buscar_por_login(login.strip().lower())
    if not usuario or not usuario["ativo"]:
        return None
    if not verificar_senha(senha, usuario["senha_hash"]):
        return None
    return usuarios_repo.carregar_sessao(usuario["id"])


# --- Regras de permissão --------------------------------------------------
def e_master(usuario: dict) -> bool:
    return usuario.get("perfil") == PERFIL_MASTER


def pode_acessar_modulo(usuario: dict, modulo: str) -> bool:
    return e_master(usuario) or modulo in usuario.get("modulos", [])


def operacoes_permitidas(usuario: dict) -> list[dict]:
    """Master vê todas; os demais só as vinculadas (se nenhuma, vê todas)."""
    from repositories import operacoes_repo

    todas = operacoes_repo.listar(apenas_ativas=True)
    if e_master(usuario) or not usuario.get("operacoes"):
        return todas
    ids = set(usuario["operacoes"])
    return [o for o in todas if o["id"] in ids]
