"""Leitura de configurações secretas (senhas, SMTP, banco).

Ordem: variável de ambiente → st.secrets (Streamlit Cloud: Settings › Secrets
ou arquivo .streamlit/secrets.toml no PC). Nunca coloque segredos no código.
"""
import os


def segredo(nome: str, padrao=None):
    valor = os.environ.get(nome)
    if valor not in (None, ""):
        return valor
    try:
        import streamlit as st
        valor = st.secrets.get(nome)
    except Exception:
        valor = None
    return padrao if valor in (None, "") else valor
