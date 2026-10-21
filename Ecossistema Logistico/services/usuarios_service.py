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


def _checar_limite_usuarios() -> None:
    from config import plano

    lim = plano.limite_usuarios()
    if lim is None:
        return
    ativos = [u for u in usuarios_repo.listar(apenas_ativos=True) if u.get("perfil") != "Motorista"]
    if len(ativos) >= lim:
        raise RegraNegocioError(f"O plano {plano.rotulo()} permite {lim} usuários ativos — já são {len(ativos)}. "
                                "Desative um usuário ou fale com o suporte para ampliar o plano.")


def salvar_usuario(*, id: int | None, nome: str, senha: str, email: str, cargo: str,
                   perfil: str, e_aprovador: bool, alcada: float, ativo: bool, trocar_senha: bool,
                   permissoes: list[str], operacoes: list[int], enviar_email: bool = False) -> dict:
    """Cria/atualiza usuário. O e-mail é o login.
    Novo usuário sem senha + enviar_email=True → gera senha provisória e envia por e-mail.
    Devolve {"id", "senha_provisoria" (se gerada e NÃO enviada), "email_enviado"}."""
    nome = nome.strip()
    if perfil == "Motorista":
        raise RegraNegocioError("Acessos de motorista são criados e alterados em Puxada › 🚛 App Carreteiro › "
                                "🔑 Acessos dos motoristas.")
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
    if not id and ativo:
        _checar_limite_usuarios()
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


# --- 🤝 Distribuir acessos: quem o Master liberou vincula acessos e cria usuários nas revendas dele ----------
def expandir(chaves) -> set[str]:
    """Pasta inteira ('frota') vale também para cada tela ('frota.placas')."""
    out = set()
    for c in chaves or []:
        mod, _, aba = c.partition(".")
        if mod not in MODULOS:
            continue
        out.add(c)
        if not aba:
            out |= {f"{mod}.{a}" for a in MODULOS[mod]["abas"]}
    return out


def revendas_do(usuario_id: int) -> list[int] | None:
    """Revendas (filiais) do usuário; None = todas."""
    ops = usuarios_repo.carregar_sessao(usuario_id).get("operacoes") or []
    return None if not ops else [int(o) for o in ops]


def usuarios_do_delegado(delegado: dict) -> list[int]:
    """Usuários que ele pode ver/alterar: não-Master, não-motorista, só das revendas dele (nunca ele mesmo)."""
    minhas = revendas_do(delegado["id"])
    out = []
    for u in usuarios_repo.listar(apenas_ativos=False):
        if u["perfil"] in ("Master", "Motorista") or u["id"] == delegado["id"]:
            continue
        ops = revendas_do(u["id"])
        if minhas is None or (ops is not None and set(ops) <= set(minhas)):
            out.append(int(u["id"]))
    return out


def salvar_por_delegado(delegado: dict, *, id: int | None, nome: str, email: str, cargo: str, ativo: bool,
                        senha: str, permissoes: list[str], operacoes: list[int]) -> dict:
    """Cria/altera usuário só com os acessos que o Master liberou para o delegado distribuir.
    Os demais acessos do usuário (que o delegado não distribui) ficam como estão."""
    pode = usuarios_repo.distribui(delegado["id"])
    if not pode:
        raise RegraNegocioError("Você não tem acessos liberados para distribuir.")
    if id and int(id) == int(delegado["id"]):
        raise RegraNegocioError("Você não pode alterar os seus próprios acessos — peça ao Master.")
    minhas = revendas_do(delegado["id"])
    if not operacoes:
        raise RegraNegocioError("Escolha a(s) revenda(s) do usuário.")
    if minhas is not None and not set(operacoes) <= set(minhas):
        raise RegraNegocioError("Só é possível liberar as revendas que você acessa.")
    liberadas = expandir(pode)
    fora = [p for p in permissoes if p not in liberadas]
    if fora:
        raise RegraNegocioError("Há acessos que o Master não liberou para você distribuir.")
    alvo = None
    if id:
        if int(id) not in usuarios_do_delegado(delegado):
            raise RegraNegocioError("Este usuário não está nas suas revendas (ou é Master).")
        alvo = usuarios_repo.carregar_sessao(int(id))
        manter = [p for p in alvo.get("modulos", []) if p not in liberadas]
        permissoes = manter + list(permissoes)
    return salvar_usuario(
        id=id, nome=nome, senha="" if id else senha, email=email, cargo=cargo,
        perfil=(alvo or {}).get("perfil") or "Operacional",
        e_aprovador=bool((alvo or {}).get("e_aprovador")), alcada=float((alvo or {}).get("alcada") or 0),
        ativo=ativo, trocar_senha=bool((alvo or {}).get("trocar_senha", 1)) if alvo else True,
        permissoes=permissoes, operacoes=list(operacoes), enviar_email=True)


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
