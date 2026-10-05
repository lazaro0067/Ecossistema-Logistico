"""Ecossistema Logístico — Revenda Ambev.

Ponto de entrada. Rode com:   streamlit run app.py

Este arquivo só: configura a página, garante o banco, faz o login,
desenha o menu e encaminha para o módulo escolhido. Regras ficam em
services/, SQL em repositories/ e telas em modules/.
"""
import os

import streamlit as st

from config.settings import APP_EMPRESA, APP_ICONE, APP_SUBTITULO, APP_TITULO, MODULO_ADMIN, MODULOS

# Link exclusivo dos motoristas: ...?app=motorista  (ou um app publicado à parte com ECO_MODO=carreteiro)
MODO_MOTORISTA = (str(st.query_params.get("app", "")).lower() in ("motorista", "carreteiro")
                  or os.environ.get("ECO_MODO", "").lower() == "carreteiro")

if MODO_MOTORISTA:
    st.set_page_config(page_title="App Carreteiro — Grupo Lima", page_icon="🚛", layout="centered",
                       initial_sidebar_state="collapsed")
else:
    st.set_page_config(page_title=f"{APP_TITULO} — {APP_SUBTITULO}", page_icon=APP_ICONE,
                       layout="wide", initial_sidebar_state="expanded")

from core import session, tema, ui  # noqa: E402
from core.auth import autenticar, e_master, e_motorista, operacoes_permitidas, pode_acessar_modulo  # noqa: E402
from database.connection import is_postgres  # noqa: E402
from database.schema import init_db  # noqa: E402
from modules import PAGINAS  # noqa: E402
from services import usuarios_service  # noqa: E402


# pastas que só fazem sentido por filial (sem visão consolidada)
SO_FILIAL = {"puxada", "distribuicao", "frota", "gente", "financeiro", "compras"}


@st.cache_resource(show_spinner="Preparando o banco de dados...")
def _preparar_banco(destino: str) -> bool:
    """Cria/atualiza as tabelas. O `destino` (arquivo ou URL do banco) entra na chave do cache:
    se o banco mudar de lugar, as tabelas são criadas de novo no banco novo."""
    init_db()
    return True


def _destino_banco() -> str:
    from config.settings import DB_PATH
    from database.connection import database_url

    return database_url() if is_postgres() else str(DB_PATH)


def tela_login() -> None:
    with st.container(key="login_card"):
        esq, dir_ = st.columns([1.05, 1])
        with esq:
            tema.painel_marca(APP_TITULO, APP_SUBTITULO, APP_EMPRESA, APP_ICONE)
        with dir_:
            if st.session_state.get("_tela") == "esqueci":
                tela_esqueci_senha()
                return
            tema.titulo_form("Bem-vindo(a) 👋", "Entre com o seu e-mail corporativo e senha.")
            with st.form("login"):
                email = st.text_input("E-mail (motorista: CPF ou celular)", placeholder="nome@grupolima.com.br",
                                      autocomplete="username")
                senha = st.text_input("Senha", type="password", placeholder="••••••••",
                                      autocomplete="current-password")
                if st.form_submit_button("Entrar", type="primary", **ui.LARGURA):
                    usuario = autenticar(email, senha)
                    if usuario:
                        session.logar(usuario)
                        st.rerun()
                    st.error("E-mail ou senha inválidos.")
            if ui.botao("Esqueci minha senha", key="btn_esqueci"):
                st.session_state["_tela"] = "esqueci"
                st.rerun()


def tela_esqueci_senha() -> None:
    from services import email_service
    from services.erros import RegraNegocioError

    etapa = st.session_state.get("_rec_etapa", 1)
    tema.titulo_form("Redefinir senha", "Vamos enviar um código para o seu e-mail.")
    if not email_service.configurado():
        st.warning("O envio de e-mail ainda não foi configurado neste sistema. Peça ao administrador (Master) "
                   "uma senha provisória.")
    elif etapa == 1:
        with st.form("rec_1"):
            email = st.text_input("E-mail cadastrado", value=st.session_state.get("_rec_email", ""))
            if st.form_submit_button("📧 Enviar código", type="primary", **ui.LARGURA):
                try:
                    usuarios_service.solicitar_codigo(email)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    st.session_state["_rec_email"] = email.strip().lower()
                    st.session_state["_rec_etapa"] = 2
                    st.rerun()
    else:
        email = st.session_state.get("_rec_email", "")
        st.info(f"Se **{email}** estiver cadastrado, o código chega em instantes. Confira também o spam. "
                f"O código vale {usuarios_service.CODIGO_MINUTOS} minutos.")
        with st.form("rec_2"):
            codigo = st.text_input("Código recebido", max_chars=6, placeholder="000000")
            nova = st.text_input("Nova senha", type="password", autocomplete="new-password")
            conf = st.text_input("Confirme a nova senha", type="password", autocomplete="new-password")
            if st.form_submit_button("Salvar nova senha", type="primary", **ui.LARGURA):
                try:
                    usuarios_service.redefinir_com_codigo(email, codigo, nova, conf)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    for k in ("_rec_etapa", "_rec_email", "_tela"):
                        st.session_state.pop(k, None)
                    ui.avisar("Senha alterada! Entre com o e-mail e a nova senha.")
                    st.rerun()
        if st.button("Reenviar código", key="rec_reenviar"):
            st.session_state["_rec_etapa"] = 1
            st.rerun()
    if st.button("← Voltar ao login", key="rec_voltar"):
        for k in ("_rec_etapa", "_tela"):
            st.session_state.pop(k, None)
        st.rerun()


def tela_troca_obrigatoria(usuario: dict) -> None:
    with st.container(key="login_card"):
        esq, centro = st.columns([1.05, 1])
        with esq:
            tema.painel_marca(APP_TITULO, APP_SUBTITULO, APP_EMPRESA, APP_ICONE)
    with centro:
        tema.titulo_form("Crie sua senha", f"Olá, {usuario['nome'].split()[0]}! Defina uma senha pessoal para continuar.")
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
        try:
            from repositories import motoristas_repo

            n_avisos = motoristas_repo.nao_lidas(usuario["id"])
        except Exception:
            n_avisos = 0
        _nav(f"🔔  Notificações ({n_avisos})" if n_avisos else "🔔  Notificações", "notificacoes", atual)
        if e_master(usuario):
            _nav("🔑  Gestão de Acessos", MODULO_ADMIN, atual)
        _nav("⚙️  Minha conta", "conta", atual)
        if ui.botao("🚪  Sair", key="nav_sair"):
            session.sair()
            st.rerun()
        if not is_postgres():
            st.caption("💽 Banco local (SQLite)")


def _op_do_link() -> int | None:
    from repositories import operacoes_repo

    valor = st.query_params.get("op")
    if not valor:
        ops = operacoes_repo.listar(apenas_ativas=True)
        return ops[0]["id"] if ops else None
    if str(valor).isdigit():
        return int(valor)
    op = operacoes_repo.buscar_por_nome(str(valor))
    return op["id"] if op else operacoes_repo.resolver_por_texto(str(valor))


def paginas_publicas() -> bool:
    """Links somente leitura do sistema original: ?modo=comercial e ?visualizacao=ressuprimento."""
    modo, vis = st.query_params.get("modo"), st.query_params.get("visualizacao")
    if modo != "comercial" and vis != "ressuprimento":
        return False
    from modules.componentes import estoque_dia
    from modules.ressuprimento import cestas, diario
    from repositories import operacoes_repo

    ops = operacoes_repo.listar(apenas_ativas=True)
    nomes = {o["id"]: o["nome"] for o in ops}
    atual = _op_do_link()
    ids = list(nomes)
    op = st.selectbox("🏢 Unidade", ids, index=ids.index(atual) if atual in ids else 0, format_func=nomes.get)
    st.session_state.operacao_nome = nomes.get(op, "")
    if modo == "comercial":
        tema.cabecalho("Portal Comercial", f"{APP_EMPRESA} · estoque do dia com marcações D0, D1 e D2", "🛍️",
                       [f"🏢 {nomes.get(op, '')}", "🔒 somente leitura"])
        estoque_dia.render(op, key="pub_com")
    else:
        tema.cabecalho("Acompanhamento de Ressuprimento", f"{APP_EMPRESA} · visualização somente leitura", "📈",
                       [f"🏢 {nomes.get(op, '')}", "🔒 somente leitura"])
        cestas.acompanhamento(op, chave="pub_ces")
        st.divider()
        diario.render({}, op)
    return True


def app_carreteiro() -> None:
    """Link separado dos motoristas: login próprio e só o App Carreteiro (de qualquer operação)."""
    from modules.puxada import app_motorista

    session.iniciar()
    usuario = session.usuario()
    ui.mostrar_avisos()
    if not usuario:
        app_motorista.tela_login()
    elif usuario.get("trocar_senha"):
        app_motorista.tela_criar_senha(usuario)
    elif not e_motorista(usuario):
        app_motorista.tela_nao_motorista(usuario)
    else:
        app_motorista.render(usuario)


def _alertas(usuario: dict) -> None:
    """Gera os avisos semanais (CNH vencendo) e lembra o usuário das notificações não lidas."""
    try:
        from repositories import motoristas_repo
        from services import motoristas_service

        motoristas_service.verificar_alertas_cnh()
        n = motoristas_repo.nao_lidas(usuario["id"])
    except Exception:
        return
    if n and not st.session_state.get("_avisou_notif"):
        st.session_state["_avisou_notif"] = True
        st.toast(f"Você tem {n} notificação(ões) — veja em 🔔 Notificações.", icon="🔔")


def main() -> None:
    tema.aplicar()
    try:
        _preparar_banco(_destino_banco())
        if not st.session_state.get("_banco_ok"):
            init_db()  # garante as tabelas uma vez por sessão (barato e idempotente)
            st.session_state["_banco_ok"] = True
    except Exception as e:
        st.error(f"Não foi possível conectar ao banco de dados: {e}")
        st.stop()
    if MODO_MOTORISTA:
        app_carreteiro()
        return
    if paginas_publicas():
        return
    session.iniciar()

    usuario = session.usuario()
    if not usuario:
        ui.mostrar_avisos()
        tela_login()
        return
    if usuario.get("trocar_senha"):
        tela_troca_obrigatoria(usuario)
        return

    if e_motorista(usuario):  # motorista vê só o App Carreteiro (tela de celular)
        from modules.puxada import app_motorista

        app_motorista.render(usuario)
        return

    pagina = session.pagina() or "inicio"
    if pagina == MODULO_ADMIN and not e_master(usuario):
        pagina = "inicio"
    if pagina in MODULOS and not pode_acessar_modulo(usuario, pagina):
        pagina = "inicio"

    _alertas(usuario)
    menu_lateral(usuario, pagina)
    operacao_id = session.operacao_id()
    ui.mostrar_avisos()

    from repositories import operacoes_repo
    if operacoes_repo.e_consolidada(operacao_id) and pagina in SO_FILIAL:
        ui.cabecalho_modulo(pagina)
        st.info(f"🔒 **{session.operacao_nome()}** é uma visão consolidada. Esta pasta trabalha por filial — "
                "escolha uma filial no menu ao lado.")
        return

    if operacao_id is None and pagina not in (MODULO_ADMIN, "conta", "notificacoes"):
        tema.cabecalho("Nenhuma operação disponível", icone="🏢")
        if e_master(usuario):
            st.info("Cadastre a primeira operação (filial/CDD) em **🔑 Gestão de Acessos › Operações**.")
        else:
            st.warning("Você não está vinculado a nenhuma operação ativa. Fale com o administrador.")
        return

    PAGINAS[pagina](usuario, operacao_id)


main()
