"""Minha conta — dados do usuário e troca de senha."""
import streamlit as st

from config.settings import MODULOS
from core import tema, ui
from core.auth import abas_permitidas, e_master, pode_acessar_modulo
from services import usuarios_service


def render(usuario: dict, operacao_id: int | None) -> None:
    ui.cabecalho("Minha conta", f"{usuario['nome']} · {usuario.get('cargo') or usuario['perfil']}", "⚙️")
    c1, c2 = st.columns([1, 1])
    with c1:
        tema.secao("Alterar senha")
        with st.form("f_senha", clear_on_submit=True):
            atual = st.text_input("Senha atual", type="password")
            nova = st.text_input("Nova senha", type="password")
            conf = st.text_input("Confirme a nova senha", type="password")
            if st.form_submit_button("Alterar senha", type="primary"):
                ui.acao(usuarios_service.trocar_propria_senha, usuario["id"], atual, nova, conf,
                        sucesso="Senha alterada!")
    with c2:
        tema.secao("Minhas pastas", "Para mudar, fale com o administrador (Master).")
        if e_master(usuario):
            st.success("Perfil Master — acesso total.")
        for mod, info in MODULOS.items():
            if pode_acessar_modulo(usuario, mod):
                abas = [info["abas"][a] for a in abas_permitidas(usuario, mod)]
                st.markdown(f"**{info['icone']} {info['rotulo']}** — {', '.join(abas)}")
