"""Envio de e-mails (redefinição de senha e boas-vindas) via SMTP.

Configure nos Secrets do Streamlit (ou .streamlit/secrets.toml no PC):

    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USUARIO = "sistema@suaempresa.com.br"
    SMTP_SENHA = "senha de app de 16 letras"
    SMTP_REMETENTE = "Ecossistema Logístico <sistema@suaempresa.com.br>"   # opcional
    APP_URL = "https://seu-app.streamlit.app"                                # opcional, vai no e-mail

No Gmail, a SMTP_SENHA é uma "senha de app" (Conta Google › Segurança ›
Verificação em duas etapas › Senhas de app), não a senha normal da conta.
"""
import html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from config.settings import APP_EMPRESA, APP_TITULO
from core.segredos import segredo
from services.erros import RegraNegocioError


def configurado() -> bool:
    return bool(segredo("SMTP_HOST") and segredo("SMTP_USUARIO") and segredo("SMTP_SENHA"))


def _remetente() -> str:
    nome, end = parseaddr(segredo("SMTP_REMETENTE", ""))
    return formataddr((nome or APP_TITULO, end or segredo("SMTP_USUARIO")))


def _layout(titulo: str, corpo_html: str) -> str:
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;background:#F4F6FA;padding:24px">
<div style="max-width:520px;margin:auto;background:#fff;border-radius:14px;border:1px solid #e3e6ec;overflow:hidden">
<div style="background:#0B1F3A;color:#fff;padding:16px 22px;font-size:17px;font-weight:700">🌐 {html.escape(APP_TITULO)}</div>
<div style="padding:22px;color:#0b0b0b;font-size:15px;line-height:1.5"><h2 style="margin:0 0 12px;font-size:19px">{html.escape(titulo)}</h2>
{corpo_html}</div>
<div style="padding:12px 22px;color:#898781;font-size:12px;border-top:1px solid #eee">{html.escape(APP_EMPRESA)} · e-mail automático, não responda.</div>
</div></div>"""


def enviar(para: str, assunto: str, titulo: str, corpo_html: str, corpo_texto: str) -> None:
    if not configurado():
        raise RegraNegocioError("O envio de e-mail ainda não foi configurado. Peça ao administrador (Master).")
    msg = EmailMessage()
    msg["From"] = _remetente()
    msg["To"] = para
    msg["Subject"] = assunto
    msg.set_content(corpo_texto)
    msg.add_alternative(_layout(titulo, corpo_html), subtype="html")

    host, porta = segredo("SMTP_HOST"), int(segredo("SMTP_PORT", 587))
    contexto = ssl.create_default_context()
    try:
        if porta == 465:
            with smtplib.SMTP_SSL(host, porta, context=contexto, timeout=20) as s:
                s.login(segredo("SMTP_USUARIO"), segredo("SMTP_SENHA"))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, porta, timeout=20) as s:
                s.starttls(context=contexto)
                s.login(segredo("SMTP_USUARIO"), segredo("SMTP_SENHA"))
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RegraNegocioError("O servidor de e-mail recusou o usuário/senha do SMTP. Confira os Secrets.")
    except (smtplib.SMTPException, OSError) as e:
        raise RegraNegocioError(f"Não foi possível enviar o e-mail agora ({e.__class__.__name__}). Tente de novo.")


def _link() -> str:
    url = segredo("APP_URL")
    return f'<p><a href="{html.escape(url)}" style="color:#2a78d6">Abrir o sistema</a></p>' if url else ""


def enviar_codigo(para: str, nome: str, codigo: str, minutos: int) -> None:
    corpo = (f"<p>Olá, {html.escape(nome)}!</p><p>Use o código abaixo para criar uma nova senha:</p>"
             f'<p style="font-size:30px;font-weight:800;letter-spacing:8px;margin:14px 0">{codigo}</p>'
             f"<p>O código vale por <b>{minutos} minutos</b> e só pode ser usado uma vez.</p>"
             f"<p style='color:#52514e'>Se não foi você que pediu, ignore este e-mail — sua senha continua a mesma.</p>"
             + _link())
    texto = (f"Olá, {nome}!\n\nSeu código para redefinir a senha: {codigo}\n"
             f"Vale por {minutos} minutos. Se não foi você, ignore este e-mail.")
    enviar(para, f"{codigo} é o seu código de redefinição de senha", "Redefinição de senha", corpo, texto)


def enviar_boas_vindas(para: str, nome: str, senha_provisoria: str) -> None:
    corpo = (f"<p>Olá, {html.escape(nome)}! Seu acesso foi criado.</p>"
             f"<p><b>E-mail:</b> {html.escape(para)}<br><b>Senha provisória:</b> "
             f'<span style="font-family:monospace;font-size:17px">{html.escape(senha_provisoria)}</span></p>'
             "<p>No primeiro acesso o sistema pede para você criar a sua própria senha.</p>" + _link())
    texto = (f"Olá, {nome}! Seu acesso foi criado.\nE-mail: {para}\nSenha provisória: {senha_provisoria}\n"
             "No primeiro acesso você vai criar a sua senha.")
    enviar(para, f"Seu acesso ao {APP_TITULO}", "Bem-vindo(a)!", corpo, texto)
