"""Minha conta — troca de senha."""
import streamlit as st

from core import ui
from services import usuarios_service


def render(usuario: dict, operacao_id: int | None) -> None:
    ui.cabecalho("👤 Minha conta", f"{usuario['nome']} · {usuario.get('cargo') or usuario['perfil']}")
    with st.form("f_senha", clear_on_submit=True):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Confirme a nova senha", type="password")
        if st.form_submit_button("Alterar senha", type="primary"):
            ui.acao(usuarios_service.trocar_propria_senha, usuario["id"], atual, nova, conf,
                    sucesso="Senha alterada!")
