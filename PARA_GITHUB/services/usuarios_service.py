"""Regras de negócio: usuários, senhas e permissões por pasta."""
import datetime as dt
import hashlib
import hmac
import re
import secrets

from config.settings import MODULOS, PERFIS
from core import tempo
from core.auth import hash_senha, verificar_senha
from database.connection import tipo_violacao
from repositories import usuarios_repo
from services import email_service
from services.erros import RegraNegocioError

SENHA_MINIMA = 6
_FMT = "%Y-%m-%d %H:%M:%S"


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


_EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RX.match(email):
        raise RegraNegocioError("Informe um e-mail válido (ex.: nome@empresa.com.br).")
    return email


def salvar_usuario(*, id: int | None, nome: str, senha: str, email: str, cargo: str,
                   perfil: str, e_aprovador: bool, alcada: float, ativo: bool, trocar_senha: bool,
                   permissoes: list[str], operacoes: list[int], enviar_email: bool = False) -> dict:
    """Cria/atualiza usuário. O e-mail é o login.
    Novo usuário sem senha + enviar_email=True → gera senha provisória e envia por e-mail.
    Devolve {"id", "senha_provisoria" (se gerada e NÃO enviada), "email_enviado"}."""
    nome = nome.strip()
    email = validar_email(email)
    if not nome:
        raise RegraNegocioError("Informe o nome.")
    if perfil not in PERFIS:
        raise RegraNegocioError("Perfil inválido.")
    if usuarios_repo.email_em_uso(email, id):
        raise RegraNegocioError(f"O e-mail {email} já está em uso por outro usuário.")
    gerada = None
    if not id and not senha:
        gerada = senha = gerar_senha_provisoria()
        trocar_senha = True
    if senha:
        _checar_senha(senha)
    if e_aprovador and alcada <= 0:
        raise RegraNegocioError("Informe a alçada (R$) do aprovador.")
    if perfil != "Master" and not permissoes:
        raise RegraNegocioError("Libere pelo menos uma pasta para o usuário.")
    if id and perfil != "Master" and usuarios_repo.buscar(id)["perfil"] == "Master" and _masters_ativos() <= 1:
        raise RegraNegocioError("Este é o único Master ativo — crie outro Master antes de mudar este perfil.")
    if id and not ativo and usuarios_repo.buscar(id)["perfil"] == "Master" and _masters_ativos() <= 1:
        raise RegraNegocioError("Não é possível desativar o único Master ativo.")

    dados = dict(id=id, login=email, nome=nome, email=email, cargo=cargo.strip(), perfil=perfil,
                 e_aprovador=int(e_aprovador), alcada=float(alcada if e_aprovador else 0),
                 ativo=int(ativo), trocar_senha=int(trocar_senha))
    try:
        uid = usuarios_repo.salvar(dados, permissoes_validas(permissoes), operacoes,
                                   hash_senha(senha) if senha else None)
    except Exception as e:
        if tipo_violacao(e) == "unica":
            raise RegraNegocioError(f"O e-mail {email} já está em uso.")
        raise

    enviado = False
    if gerada and enviar_email and email_service.configurado():
        try:
            email_service.enviar_boas_vindas(email, nome, gerada)
            enviado = True
        except RegraNegocioError:
            enviado = False
    return {"id": uid, "senha_provisoria": None if enviado else gerada, "email_enviado": enviado}


def _masters_ativos() -> int:
    return sum(1 for u in usuarios_repo.listar(apenas_ativos=True) if u["perfil"] == "Master")


def gerar_senha_provisoria() -> str:
    return "Lima" + secrets.token_hex(3)


def resetar_senha(usuario_id: int) -> str:
    """Gera senha provisória; o usuário é obrigado a trocar no próximo acesso."""
    nova = gerar_senha_provisoria()
    usuarios_repo.trocar_senha(usuario_id, hash_senha(nova), exigir_troca=True)
    return nova


# --- "Esqueci minha senha": código de 6 dígitos por e-mail ------------------
CODIGO_MINUTOS = 15
CODIGO_MAX_TENTATIVAS = 5
CODIGOS_POR_HORA = 3


def _hash_codigo(usuario_id: int, codigo: str) -> str:
    return hashlib.sha256(f"{usuario_id}:{codigo}".encode()).hexdigest()


def solicitar_codigo(email: str) -> None:
    """Envia o código. Para não revelar quais e-mails existem, e-mail desconhecido
    termina "com sucesso" sem enviar nada."""
    email = validar_email(email)
    if not email_service.configurado():
        raise RegraNegocioError("O envio de e-mail ainda não foi configurado. Peça ao administrador (Master) "
                                "uma senha provisória.")
    u = usuarios_repo.buscar_por_email(email)
    if not u or not u["ativo"]:
        return
    agora = tempo.agora()
    if usuarios_repo.codigos_recentes(u["id"], (agora - dt.timedelta(hours=1)).strftime(_FMT)) >= CODIGOS_POR_HORA:
        raise RegraNegocioError("Muitos pedidos de código em pouco tempo. Aguarde alguns minutos e tente de novo.")
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    usuarios_repo.criar_codigo(u["id"], _hash_codigo(u["id"], codigo), agora.strftime(_FMT),
                               (agora + dt.timedelta(minutes=CODIGO_MINUTOS)).strftime(_FMT))
    email_service.enviar_codigo(u["email"], u["nome"], codigo, CODIGO_MINUTOS)


def redefinir_com_codigo(email: str, codigo: str, nova: str, confirmacao: str) -> None:
    email = validar_email(email)
    invalido = RegraNegocioError("Código inválido ou expirado. Peça um novo código.")
    u = usuarios_repo.buscar_por_email(email)
    if not u or not u["ativo"]:
        raise invalido
    c = usuarios_repo.codigo_ativo(u["id"])
    if not c or c["expira_em"] < tempo.agora().strftime(_FMT) or c["tentativas"] >= CODIGO_MAX_TENTATIVAS:
        raise invalido
    codigo = re.sub(r"\D", "", codigo or "")
    if not hmac.compare_digest(c["codigo_hash"], _hash_codigo(u["id"], codigo)):
        usuarios_repo.marcar_codigo(c["id"], tentativa=True)
        restantes = CODIGO_MAX_TENTATIVAS - c["tentativas"] - 1
        raise RegraNegocioError(f"Código incorreto. {max(restantes, 0)} tentativa(s) restante(s)."
                                if restantes > 0 else "Código bloqueado por tentativas erradas. Peça um novo.")
    _checar_senha(nova)
    if nova != confirmacao:
        raise RegraNegocioError("A confirmação não confere com a nova senha.")
    usuarios_repo.trocar_senha(u["id"], hash_senha(nova), exigir_troca=False)
    usuarios_repo.marcar_codigo(c["id"], usado=True)


def trocar_proprio_email(usuario_id: int, novo: str, senha_atual: str) -> str:
    u = usuarios_repo.buscar(usuario_id)
    if not verificar_senha(senha_atual, u["senha_hash"]):
        raise RegraNegocioError("Senha atual incorreta.")
    novo = validar_email(novo)
    if usuarios_repo.email_em_uso(novo, usuario_id):
        raise RegraNegocioError("Este e-mail já está em uso.")
    usuarios_repo.trocar_email(usuario_id, novo)
    return novo


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
