"""Links públicos por revenda (Portal Comercial): cada revenda tem o seu link, com um código próprio.

O Master gera, troca (o link antigo para de funcionar) e ativa/desativa cada link em
🔑 Gestão de Acessos › 🔗 Links do Portal Comercial.
"""
import secrets

from core import tempo
from database.connection import execute, query_one

COMERCIAL = "comercial"


def _novo_token() -> str:
    return secrets.token_urlsafe(12)


def obter(operacao_id: int, tipo: str = COMERCIAL, usuario: str = "") -> dict:
    """Link da revenda (cria na primeira vez)."""
    r = query_one("SELECT * FROM links_publicos WHERE operacao_id = ? AND tipo = ?", (operacao_id, tipo))
    if r:
        return r
    execute("""INSERT INTO links_publicos (operacao_id, tipo, token, ativo, atualizado_por, atualizado_em)
               VALUES (?, ?, ?, 1, ?, ?)""", (operacao_id, tipo, _novo_token(), usuario, tempo.agora_str()))
    return query_one("SELECT * FROM links_publicos WHERE operacao_id = ? AND tipo = ?", (operacao_id, tipo))


def renovar(operacao_id: int, tipo: str = COMERCIAL, usuario: str = "") -> dict:
    obter(operacao_id, tipo, usuario)
    execute("UPDATE links_publicos SET token = ?, atualizado_por = ?, atualizado_em = ? WHERE operacao_id = ? AND tipo = ?",
            (_novo_token(), usuario, tempo.agora_str(), operacao_id, tipo))
    return obter(operacao_id, tipo)


def ativar(operacao_id: int, ativo: bool, tipo: str = COMERCIAL, usuario: str = "") -> None:
    obter(operacao_id, tipo, usuario)
    execute("UPDATE links_publicos SET ativo = ?, atualizado_por = ?, atualizado_em = ? WHERE operacao_id = ? AND tipo = ?",
            (int(bool(ativo)), usuario, tempo.agora_str(), operacao_id, tipo))


def por_token(token: str, tipo: str = COMERCIAL) -> dict | None:
    """Revenda do link — só se o link estiver ativo."""
    if not token:
        return None
    r = query_one("""SELECT l.*, o.nome AS revenda FROM links_publicos l JOIN operacoes o ON o.id = l.operacao_id
                     WHERE l.token = ? AND l.tipo = ?""", (str(token), tipo))
    return r if r and int(r.get("ativo") or 0) == 1 else None


def url_base() -> str:
    from config.settings import APP_URL_PADRAO
    from core.segredos import segredo

    url = (segredo("APP_URL") or "").strip().rstrip("/")
    if url:
        return url
    try:
        import streamlit as st

        host = st.context.headers.get("host") or ""
    except Exception:
        host = ""
    return f"https://{host}" if host and "localhost" not in host and "127.0.0.1" not in host else APP_URL_PADRAO


def url(operacao_id: int, tipo: str = COMERCIAL) -> str:
    return f"{url_base()}/?modo={tipo}&k={obter(operacao_id, tipo)['token']}"
