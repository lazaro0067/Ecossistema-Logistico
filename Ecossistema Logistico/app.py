"""Ecossistema Logístico — Revenda Ambev.

Ponto de entrada. Rode com:   streamlit run app.py

Este arquivo só faz 4 coisas: configura a página, garante o banco,
mostra o login e desenha o menu/roteia para o módulo escolhido.
Toda a lógica fica em services/, o acesso a dados em repositories/
e as telas em modules/.
"""
import streamlit as st

from config.settings import APP_ICONE, APP_SUBTITULO, APP_TITULO, MODULO_ADMIN, MODULOS

st.set_page_config(page_title=f"{APP_TITULO} — {APP_SUBTITULO}", page_icon=APP_ICONE,
                   layout="wide", initial_sidebar_state="expanded")

from core import session, ui  # noqa: E402
from core.auth import autenticar, e_master, operacoes_permitidas, pode_acessar_modulo  # noqa: E402
from database.schema import init_db  # noqa: E402
from modules import PAGINAS  # noqa: E402


@st.cache_resource
def _preparar_banco() -> bool:
    init_db()
    return True


def tela_login() -> None:
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.title(f"{APP_ICONE} {APP_TITULO}")
        st.caption(APP_SUBTITULO)
        with st.form("login"):
            login = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", type="primary"):
                usuario = autenticar(login, senha)
                if usuario:
                    session.logar(usuario)
                    st.rerun()
                st.error("Usuário ou senha inválidos.")


def menu_lateral(usuario: dict) -> None:
    sb = st.sidebar
    sb.title(f"{APP_ICONE} {APP_TITULO}")
    sb.write(f"👤 **{usuario['nome']}**  \n{usuario.get('cargo') or usuario['perfil']}")

    # Seletor de operação (filial)
    ops = operacoes_permitidas(usuario)
    if ops:
        ids = [o["id"] for o in ops]
        atual = session.operacao_id() if session.operacao_id() in ids else ids[0]
        escolhida = sb.selectbox("🏢 Operação", ids, index=ids.index(atual),
                                 format_func=lambda i: next(o["nome"] for o in ops if o["id"] == i))
        st.session_state.operacao_id = escolhida
        st.session_state.operacao_nome = next(o["nome"] for o in ops if o["id"] == escolhida)

    sb.divider()
    with sb:
        if ui.botao("🏠 Início", key="nav_inicio"):
            session.ir_para("inicio")
        for chave, (rotulo, icone) in MODULOS.items():
            if pode_acessar_modulo(usuario, chave) and ui.botao(f"{icone} {rotulo}", key=f"nav_{chave}"):
                session.ir_para(chave)
        sb.divider()
        if e_master(usuario) and ui.botao("🔑 Gestão de Acessos", key="nav_admin"):
            session.ir_para(MODULO_ADMIN)
        if ui.botao("⚙️ Minha conta", key="nav_conta"):
            session.ir_para("conta")
        if ui.botao("🚪 Sair", key="nav_sair"):
            session.sair()
            st.rerun()


def main() -> None:
    _preparar_banco()
    session.iniciar()

    usuario = session.usuario()
    if not usuario:
        tela_login()
        return

    menu_lateral(usuario)
    pagina = session.pagina() or "inicio"
    operacao_id = session.operacao_id()

    # Proteções de acesso
    if pagina == MODULO_ADMIN and not e_master(usuario):
        pagina = "inicio"
    if pagina in MODULOS and not pode_acessar_modulo(usuario, pagina):
        pagina = "inicio"
    if operacao_id is None and pagina not in (MODULO_ADMIN, "conta"):
        ui.cabecalho("Nenhuma operação disponível")
        if e_master(usuario):
            st.info("Cadastre a primeira operação (filial/CDD) em **🔑 Gestão de Acessos › Operações**.")
        else:
            st.warning("Você não está vinculado a nenhuma operação ativa. Fale com o administrador.")
        return

    ui.mostrar_avisos()
    PAGINAS[pagina](usuario, operacao_id)


main()
