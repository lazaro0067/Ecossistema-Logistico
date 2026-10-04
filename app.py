"""Ecossistema Logístico — Revenda Ambev.

Ponto de entrada. Rode com:   streamlit run app.py

Este arquivo só: configura a página, garante o banco, faz o login,
desenha o menu e encaminha para o módulo escolhido. Regras ficam em
services/, SQL em repositories/ e telas em modules/.
"""
import streamlit as st

from config.settings import APP_EMPRESA, APP_ICONE, APP_SUBTITULO, APP_TITULO, MODULO_ADMIN, MODULOS

st.set_page_config(page_title=f"{APP_TITULO} — {APP_SUBTITULO}", page_icon=APP_ICONE,
                   layout="wide", initial_sidebar_state="expanded")

from core import session, tema, ui  # noqa: E402
from core.auth import autenticar, e_master, operacoes_permitidas, pode_acessar_modulo  # noqa: E402
from database.connection import is_postgres  # noqa: E402
from database.schema import init_db  # noqa: E402
from modules import PAGINAS  # noqa: E402
from services import usuarios_service  # noqa: E402


@st.cache_resource(show_spinner="Preparando o banco de dados...")
def _preparar_banco() -> bool:
    init_db()
    return True


def tela_login() -> None:
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        st.markdown('<div class="eco-login">', unsafe_allow_html=True)
        tema.cabecalho(APP_TITULO, f"{APP_SUBTITULO} · {APP_EMPRESA}", APP_ICONE)
        with st.form("login"):
            login = st.text_input("Usuário", placeholder="seu.login")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", type="primary", **ui.LARGURA):
                usuario = autenticar(login, senha)
                if usuario:
                    session.logar(usuario)
                    st.rerun()
                st.error("Usuário ou senha inválidos.")
        st.caption("Esqueceu a senha? Peça ao administrador (Master) para gerar uma nova.")
        st.markdown("</div>", unsafe_allow_html=True)


def tela_troca_obrigatoria(usuario: dict) -> None:
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        tema.cabecalho("Crie sua senha", f"Olá, {usuario['nome']}! Por segurança, defina uma senha pessoal "
                       "antes de continuar.", "🔐")
        with st.form("troca_obrigatoria"):
            nova = st.text_input("Nova senha", type="password")
            conf = st.text_input("Confirme a nova senha", type="password")
            if st.form_submit_button("Salvar e entrar", type="primary", **ui.LARGURA):
                try:
                    usuarios_service.trocar_propria_senha(usuario["id"], None, nova, conf)
                except Exception as e:
                    st.error(str(e))
                else:
                    usuario["trocar_senha"] = 0
                    ui.avisar("Senha criada! Bem-vindo(a).")
                    st.rerun()
        if st.button("Sair"):
            session.sair()
            st.rerun()


def _nav(rotulo: str, pagina: str, atual: str) -> None:
    if ui.botao(rotulo, key=f"nav_{pagina}", type="primary" if pagina == atual else "secondary"):
        session.ir_para(pagina)
        st.rerun()


def menu_lateral(usuario: dict, atual: str) -> None:
    with st.sidebar:
        st.markdown(
            f'<div class="eco-marca"><div class="logo">{APP_ICONE}</div><div><b>{APP_TITULO}</b>'
            f'<span>{APP_SUBTITULO}</span></div></div>'
            f'<div class="eco-user"><b>{tema._e(usuario["nome"])}</b>'
            f'{tema._e(usuario.get("cargo") or usuario["perfil"])} · {tema._e(usuario["perfil"])}</div>',
            unsafe_allow_html=True,
        )
        ops = operacoes_permitidas(usuario)
        if ops:
            ids = [o["id"] for o in ops]
            nomes = {o["id"]: o["nome"] for o in ops}
            atual_op = session.operacao_id() if session.operacao_id() in ids else ids[0]
            escolhida = st.selectbox("🏢 Unidade / Operação", ids, index=ids.index(atual_op), format_func=nomes.get)
            st.session_state.operacao_id = escolhida
            st.session_state.operacao_nome = nomes[escolhida]

        st.markdown('<div class="eco-menu-titulo">Visão geral</div>', unsafe_allow_html=True)
        _nav("🏠  Início", "inicio", atual)
        st.markdown('<div class="eco-menu-titulo">Departamentos</div>', unsafe_allow_html=True)
        for chave, m in MODULOS.items():
            if pode_acessar_modulo(usuario, chave):
                _nav(f"{m['icone']}  {m['rotulo']}", chave, atual)
        st.markdown('<div class="eco-menu-titulo">Conta</div>', unsafe_allow_html=True)
        if e_master(usuario):
            _nav("🔑  Gestão de Acessos", MODULO_ADMIN, atual)
        _nav("⚙️  Minha conta", "conta", atual)
        if ui.botao("🚪  Sair", key="nav_sair"):
            session.sair()
            st.rerun()
        if not is_postgres():
            st.caption("💽 Banco local (SQLite)")


def main() -> None:
    tema.aplicar()
    try:
        _preparar_banco()
    except Exception as e:
        st.error(f"Não foi possível conectar ao banco de dados: {e}")
        st.stop()
    session.iniciar()

    usuario = session.usuario()
    if not usuario:
        tela_login()
        return
    if usuario.get("trocar_senha"):
        tela_troca_obrigatoria(usuario)
        return

    pagina = session.pagina() or "inicio"
    if pagina == MODULO_ADMIN and not e_master(usuario):
        pagina = "inicio"
    if pagina in MODULOS and not pode_acessar_modulo(usuario, pagina):
        pagina = "inicio"

    menu_lateral(usuario, pagina)
    operacao_id = session.operacao_id()
    ui.mostrar_avisos()

    if operacao_id is None and pagina not in (MODULO_ADMIN, "conta"):
        tema.cabecalho("Nenhuma operação disponível", icone="🏢")
        if e_master(usuario):
            st.info("Cadastre a primeira operação (filial/CDD) em **🔑 Gestão de Acessos › Operações**.")
        else:
            st.warning("Você não está vinculado a nenhuma operação ativa. Fale com o administrador.")
        return

    PAGINAS[pagina](usuario, operacao_id)


main()
