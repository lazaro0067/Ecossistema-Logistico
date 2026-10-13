"""Estado da sessão (usuário logado, operação e página atuais)."""
import streamlit as st


def iniciar() -> None:
    st.session_state.setdefault("usuario", None)
    st.session_state.setdefault("pagina", None)
    st.session_state.setdefault("operacao_id", None)


def usuario() -> dict | None:
    return st.session_state.get("usuario")


def logar(dados: dict) -> None:
    st.session_state.usuario = dados
    st.session_state.pagina = None
    st.session_state.operacao_id = None


def sair() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    for q in ("s", "p", "k"):  # acesso lembrado e página atual no endereço
        if q in st.query_params:
            del st.query_params[q]


def operacao_id() -> int | None:
    return st.session_state.get("operacao_id")


def operacao_nome() -> str:
    return st.session_state.get("operacao_nome", "")


def pagina() -> str | None:
    return st.session_state.get("pagina")


def ir_para(pag: str) -> None:
    st.session_state.pagina = pag
    if "s" in st.query_params:  # sistema com "manter conectado": volta na mesma página ao recarregar
        st.query_params["p"] = pag
