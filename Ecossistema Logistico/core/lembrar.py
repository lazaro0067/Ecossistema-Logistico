"""“Manter conectado” por COOKIE do navegador — a chave de acesso nunca vai no endereço da página.

Antes a chave ficava no link (?s=… / ?k=…): quem recebia o link copiado entrava na conta de quem mandou. Agora ela
fica num cookie só deste navegador (não vai junto quando o link é copiado). Links antigos com ?s/?k são ignorados.
Se o navegador não aceitar o cookie, o sistema só pede o login de novo — nunca entra na conta errada.
"""
import json

import streamlit as st

COOKIES = {"s": "eco_s", "k": "eco_k"}  # s = sistema · k = App Carreteiro (motorista)
DIAS = 30


def ler(tipo: str) -> str | None:
    try:
        return (st.context.cookies or {}).get(COOKIES[tipo]) or None
    except Exception:  # noqa: BLE001 — versão sem st.context.cookies: sem “manter conectado”
        return None


def guardar(tipo: str, token: str | None) -> None:
    """Grava o cookie na próxima vez que a tela desenhar (depois do st.rerun do login)."""
    if token:
        st.session_state["_cookie_por"] = (COOKIES[tipo], token)
        st.session_state["_lembrar"] = True


def esquecer(*tipos: str) -> None:
    st.session_state["_cookie_tirar"] = [COOKIES[t] for t in (tipos or COOKIES)]
    st.session_state.pop("_lembrar", None)


def limpar_endereco(*tipos: str) -> None:
    """Chave antiga de login no endereço: não vale mais — some do link. Padrão: só ?s (sistema). O ?k só é chave de
    login no App Carreteiro (em outros links, ?k é o link público/da revenda e deve continuar)."""
    for q in (tipos or ("s",)):
        if q in st.query_params:
            del st.query_params[q]


def aplicar() -> None:
    """Chame no começo de toda tela: grava/apaga o cookie pendente no navegador."""
    por = st.session_state.pop("_cookie_por", None)
    tirar = st.session_state.pop("_cookie_tirar", None)
    if not por and not tirar:
        return
    cmds = []
    if por:
        cmds.append(f"{por[0]}={por[1]}; path=/; max-age={DIAS * 86400}; SameSite=Lax; Secure")
    for nome in tirar or []:
        cmds.append(f"{nome}=; path=/; max-age=0; SameSite=Lax; Secure")
    js = ("<script>(function(){var c=" + json.dumps(cmds) + ";for(var i=0;i<c.length;i++){"
          "try{document.cookie=c[i];}catch(e){}try{window.parent.document.cookie=c[i];}catch(e){}"
          "try{window.top.document.cookie=c[i];}catch(e){}}})();</script>")
    try:
        import streamlit.components.v1 as components

        components.html(js, height=0)
    except Exception:  # noqa: BLE001
        pass
