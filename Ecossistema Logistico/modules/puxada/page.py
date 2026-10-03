"""Módulo Puxada — monta as abas; cada aba vive no seu próprio arquivo."""
import streamlit as st

from core import session, ui
from modules.puxada import aprovacoes, cadastros, cotacao, encerramento, obz, painel, pedidos

ABAS = [
    ("📝 Nova Cotação", cotacao),
    ("✅ Aprovações", aprovacoes),
    ("📋 Painel de Fretes", painel),
    ("📄 Encerramento (NF/CT-e)", encerramento),
    ("📊 OBZ (Real x Meta)", obz),
    ("📦 Pedidos Marcados", pedidos),
    ("⚙️ Cadastros", cadastros),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("🚚 Puxada", session.operacao_nome())
    for aba, (_, modulo) in zip(st.tabs([a for a, _ in ABAS]), ABAS):
        with aba:
            modulo.render(usuario, operacao_id)
