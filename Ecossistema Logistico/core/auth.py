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


def autenticar(email: str, senha: str) -> dict | None:
    """Login por e-mail. Devolve o usuário (com módulos e operações) ou None.
    Aceita também o login antigo, para quem migrou do sistema anterior sem e-mail."""
    from repositories import usuarios_repo

    chave = (email or "").strip().lower()
    usuario = usuarios_repo.buscar_por_email(chave) or usuarios_repo.buscar_por_login(chave)
    if not usuario and "@" not in chave:  # motoristas entram com CPF/celular (só os números)
        digitos = "".join(c for c in chave if c.isdigit())
        usuario = usuarios_repo.buscar_por_login(digitos) if digitos else None
    if not usuario or not usuario["ativo"]:
        return None
    if not verificar_senha(senha, usuario["senha_hash"]):
        return None
    usuarios_repo.registrar_acesso(usuario["id"])
    return usuarios_repo.carregar_sessao(usuario["id"])


# --- Regras de permissão --------------------------------------------------
def e_master(usuario: dict) -> bool:
    return usuario.get("perfil") == PERFIL_MASTER


def e_motorista(usuario: dict) -> bool:
    from config.settings import PERFIL_MOTORISTA

    return usuario.get("perfil") == PERFIL_MOTORISTA


def _perms(usuario: dict) -> set[str]:
    return set(usuario.get("modulos", []))


# Telas novas liberadas junto com a tela "irmã" que o usuário já tinha (evita reconfigurar acessos)
_ABAS_IRMAS = {"armazem.pedidos": "armazem.patio", "puxada.pedidos_dia": "puxada.disponibilidade",
               "ressuprimento.puxada_pedidos": "ressuprimento.sugestao",
               "ressuprimento.ruptura": "ressuprimento.estoque"}


def pode_acessar_aba(usuario: dict, modulo: str, aba: str) -> bool:
    """Acesso à pasta inteira ("puxada") ou à subpasta ("puxada.aprovacoes")."""
    p = _perms(usuario)
    chave = f"{modulo}.{aba}"
    return e_master(usuario) or modulo in p or chave in p or _ABAS_IRMAS.get(chave) in p


def abas_permitidas(usuario: dict, modulo: str) -> list[str]:
    from config.settings import MODULOS

    return [a for a in MODULOS[modulo]["abas"] if pode_acessar_aba(usuario, modulo, a)]


def pode_acessar_modulo(usuario: dict, modulo: str) -> bool:
    p = _perms(usuario)
    return e_master(usuario) or modulo in p or any(x.startswith(modulo + ".") for x in p)


def operacoes_permitidas(usuario: dict) -> list[dict]:
    """Master vê todas; os demais só as vinculadas (se nenhuma, vê todas)."""
    from repositories import operacoes_repo

    todas = operacoes_repo.listar(apenas_ativas=True)
    if e_master(usuario) or not usuario.get("operacoes"):
        return todas
    ids = set(usuario["operacoes"])
    # visão consolidada (ex.: Bahia) aparece quando o usuário tem todas as filiais dela
    return [o for o in todas if o["id"] in ids or (operacoes_repo.e_consolidada(o["id"])
                                                   and set(operacoes_repo.ids_efetivos(o["id"])) <= ids)]


# --- "Lembrar acesso" no link do motorista ------------------------------------
# O token vai no endereço (?k=...). É assinado com a senha atual do usuário: trocar a senha
# derruba todos os tokens antigos. Vale TOKEN_DIAS dias.
TOKEN_DIAS = 30


def _assinar(usuario_id: int, expira: int, senha_hash: str) -> str:
    return hmac.new(senha_hash.encode(), f"{usuario_id}.{expira}".encode(), hashlib.sha256).hexdigest()[:32]


def gerar_token(usuario_id: int) -> str | None:
    import time

    from repositories import usuarios_repo

    u = usuarios_repo.buscar(usuario_id)
    if not u:
        return None
    expira = int(time.time()) + TOKEN_DIAS * 86400
    return f"{usuario_id}.{expira}.{_assinar(usuario_id, expira, u['senha_hash'])}"


def entrar_por_token(token: str) -> dict | None:
    """Devolve o usuário (sessão) se o token for válido, do próprio usuário ativo e não estiver vencido."""
    import time

    from repositories import usuarios_repo

    try:
        uid, expira, assinatura = str(token).split(".")
        uid, expira = int(uid), int(expira)
    except (ValueError, AttributeError):
        return None
    if expira < time.time():
        return None
    u = usuarios_repo.buscar(uid)
    if not u or not u["ativo"] or not hmac.compare_digest(_assinar(uid, expira, u["senha_hash"]), assinatura):
        return None
    usuarios_repo.registrar_acesso(uid)
    return usuarios_repo.carregar_sessao(uid)
