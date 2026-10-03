"""Painel Master — usuários, permissões e operações."""
import streamlit as st

from config.settings import MODULOS, PERFIS
from core import ui
from repositories import operacoes_repo, usuarios_repo
from services import cadastros_service, usuarios_service


def _form_usuario(existente: dict | None, operacoes: list[dict]) -> None:
    u = existente or {}
    chave = f"u_{u.get('id', 'novo')}"
    with st.form(f"f_{chave}", clear_on_submit=not existente):
        c1, c2, c3 = st.columns(3)
        login = c1.text_input("Login", value=u.get("login", ""), key=f"{chave}_login")
        nome = c2.text_input("Nome completo", value=u.get("nome", ""), key=f"{chave}_nome")
        senha = c3.text_input("Senha" + (" (vazio = manter)" if existente else ""), type="password",
                              key=f"{chave}_senha")
        c4, c5, c6 = st.columns(3)
        email = c4.text_input("E-mail", value=u.get("email") or "", key=f"{chave}_email")
        cargo = c5.text_input("Cargo", value=u.get("cargo") or "", key=f"{chave}_cargo")
        perfil = c6.selectbox("Perfil", PERFIS, index=PERFIS.index(u.get("perfil", "Operacional")),
                              key=f"{chave}_perfil")
        c7, c8, c9 = st.columns(3)
        aprov = c7.checkbox("É aprovador de frete", value=bool(u.get("e_aprovador")), key=f"{chave}_aprov")
        alcada = c8.number_input("Alçada (R$)", min_value=0.0, value=float(u.get("alcada", 0)), step=1000.0,
                                 key=f"{chave}_alc")
        ativo = c9.checkbox("Ativo", value=bool(u.get("ativo", 1)), key=f"{chave}_ativo")

        modulos = st.multiselect("Módulos liberados", list(MODULOS), default=u.get("modulos", ["puxada"]),
                                 format_func=lambda m: f"{MODULOS[m][1]} {MODULOS[m][0]}", key=f"{chave}_mod")
        nomes_op = {o["id"]: o["nome"] for o in operacoes}
        ops = st.multiselect("Operações (vazio = todas)", list(nomes_op), default=u.get("operacoes", []),
                             format_func=nomes_op.get, key=f"{chave}_ops")

        if st.form_submit_button("Salvar usuário", type="primary"):
            ui.acao(usuarios_service.salvar_usuario, id=u.get("id"), login=login, nome=nome, senha=senha,
                    email=email, cargo=cargo, perfil=perfil, e_aprovador=aprov, alcada=alcada,
                    ativo=ativo, modulos=modulos, operacoes=ops, sucesso="Usuário salvo!")


def _aba_usuarios() -> None:
    operacoes = operacoes_repo.listar()
    ui.tabela(usuarios_repo.listar_df())

    st.subheader("Cadastrar novo usuário")
    _form_usuario(None, operacoes)

    st.subheader("Editar usuário")
    todos = usuarios_repo.listar(apenas_ativos=False)
    uid = ui.select_registro("Usuário", todos, key="adm_edit")
    if uid:
        _form_usuario({**usuarios_repo.buscar(uid), **usuarios_repo.carregar_sessao(uid)}, operacoes)


def _aba_operacoes() -> None:
    st.caption("Cada operação (filial/CDD) tem seus próprios fretes, estoque e indicadores.")
    with st.form("f_op", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        nome, cnpj = c1.text_input("Nome"), c2.text_input("CNPJ")
        cidade, uf = c3.text_input("Cidade"), c4.text_input("UF", max_chars=2)
        if st.form_submit_button("+ Cadastrar operação"):
            ui.acao(cadastros_service.criar_operacao, nome, cnpj, cidade, uf)

    ops = operacoes_repo.listar()
    import pandas as pd
    ui.tabela(pd.DataFrame(ops))
    oid = ui.select_registro("Editar operação", ops, key="adm_op")
    if oid:
        o = operacoes_repo.buscar(oid)
        with st.form(f"f_op_{oid}"):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
            nome = c1.text_input("Nome", value=o["nome"])
            cnpj = c2.text_input("CNPJ", value=o["cnpj"] or "")
            cidade = c3.text_input("Cidade", value=o["cidade"] or "")
            uf = c4.text_input("UF", value=o["uf"] or "", max_chars=2)
            ativo = c5.checkbox("Ativa", value=bool(o["ativo"]))
            if st.form_submit_button("Salvar"):
                ui.acao(cadastros_service.atualizar_operacao, oid, nome, cnpj, cidade, uf, ativo)


def render(usuario: dict, operacao_id: int | None) -> None:
    ui.cabecalho("🔑 Gestão de Acessos", "Usuários, permissões e operações")
    a1, a2 = st.tabs(["👤 Usuários", "🏢 Operações"])
    with a1:
        _aba_usuarios()
    with a2:
        _aba_operacoes()
