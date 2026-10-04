"""Painel Master — usuários, permissões por pasta e operações."""
import pandas as pd
import streamlit as st

from config.settings import MODULOS, PERFIL_MASTER, PERFIS
from core import tema, ui
from repositories import operacoes_repo, usuarios_repo
from services import cadastros_service, usuarios_service
from services.erros import RegraNegocioError


# --- Árvore de permissões (pastas e subpastas) ---------------------------
def _arvore_permissoes(chave: str, atuais: list[str]) -> list[str]:
    """Um bloco por pasta: 'pasta inteira' ou abas escolhidas. Devolve a lista de chaves."""
    escolhidas: list[str] = []
    cols = st.columns(3)
    for i, (mod, info) in enumerate(MODULOS.items()):
        with cols[i % 3].container(border=True):
            tem_inteira = mod in atuais
            abas_atuais = [a for a in info["abas"] if f"{mod}.{a}" in atuais]
            inteira = st.checkbox(f"{info['icone']} **{info['rotulo']}** — pasta inteira",
                                  value=tem_inteira, key=f"{chave}_p_{mod}")
            if inteira:
                escolhidas.append(mod)
                st.caption("Acesso a todas as abas, inclusive as que forem criadas no futuro.")
            else:
                for aba, rotulo in info["abas"].items():
                    if st.checkbox(rotulo, value=aba in abas_atuais, key=f"{chave}_p_{mod}_{aba}"):
                        escolhidas.append(f"{mod}.{aba}")
    return escolhidas


def _form_usuario(existente: dict | None, operacoes: list[dict]) -> None:
    u = existente or {}
    chave = f"u{u.get('id', 'novo')}_{st.session_state.get('_adm_ver', 0)}"

    st.markdown("**Dados de acesso**")
    c1, c2, c3 = st.columns(3)
    login = c1.text_input("Login (usuário)", value=u.get("login", ""), key=f"{chave}_login",
                          placeholder="joao.silva", disabled=bool(existente))
    nome = c2.text_input("Nome completo", value=u.get("nome", ""), key=f"{chave}_nome")
    senha = c3.text_input("Senha inicial" if not existente else "Nova senha (vazio = manter)",
                          type="password", key=f"{chave}_senha")
    c4, c5, c6 = st.columns(3)
    email = c4.text_input("E-mail", value=u.get("email") or "", key=f"{chave}_email")
    cargo = c5.text_input("Cargo", value=u.get("cargo") or "", key=f"{chave}_cargo")
    perfil = c6.selectbox("Perfil", PERFIS, index=PERFIS.index(u.get("perfil", "Operacional")),
                          key=f"{chave}_perfil",
                          help="Master: acesso total e gestão de acessos. Gestor: define metas. "
                               "Operacional: usa as pastas liberadas.")
    c7, c8, c9, c10 = st.columns(4)
    aprov = c7.checkbox("Aprova fretes", value=bool(u.get("e_aprovador")), key=f"{chave}_aprov")
    alcada = c8.number_input("Alçada (R$)", min_value=0.0, value=float(u.get("alcada") or 0), step=1000.0,
                             key=f"{chave}_alc", disabled=not aprov)
    ativo = c9.checkbox("Usuário ativo", value=bool(u.get("ativo", 1)), key=f"{chave}_ativo")
    trocar = c10.checkbox("Exigir troca de senha", value=bool(u.get("trocar_senha", 1)), key=f"{chave}_troca",
                          help="No próximo login o usuário cria a própria senha.")

    nomes_op = {o["id"]: o["nome"] for o in operacoes}
    ops = st.multiselect("🏢 Operações que pode acessar (vazio = todas)", list(nomes_op),
                         default=[o for o in u.get("operacoes", []) if o in nomes_op],
                         format_func=nomes_op.get, key=f"{chave}_ops")

    st.markdown("**📁 Permissões por pasta**")
    if perfil == PERFIL_MASTER:
        st.info("Perfil Master acessa todas as pastas e a Gestão de Acessos.")
        permissoes = []
    else:
        permissoes = _arvore_permissoes(chave, u.get("modulos", []))

    if st.button("💾 Salvar usuário", type="primary", key=f"{chave}_salvar"):
        try:
            usuarios_service.salvar_usuario(
                id=u.get("id"), login=login if not existente else u["login"], nome=nome, senha=senha,
                email=email, cargo=cargo, perfil=perfil, e_aprovador=aprov, alcada=alcada, ativo=ativo,
                trocar_senha=trocar, permissoes=permissoes, operacoes=ops)
        except RegraNegocioError as e:
            st.error(str(e))
            return
        st.session_state["_adm_ver"] = st.session_state.get("_adm_ver", 0) + 1  # limpa o formulário
        ui.avisar(f"Usuário '{nome}' salvo!")
        st.rerun()


def _aba_usuarios(usuario_logado: dict) -> None:
    df = usuarios_repo.listar_df()
    ativos = int((df["situacao"] == "Ativo").sum()) if not df.empty else 0
    tema.kpis([
        {"titulo": "Usuários ativos", "valor": ativos, "icone": "👤", "status": "info"},
        {"titulo": "Masters", "valor": int((df["perfil"] == PERFIL_MASTER).sum()), "icone": "🔑", "status": "info"},
        {"titulo": "Aprovadores", "valor": int((df["aprovador"] == "Sim").sum()), "icone": "✅", "status": "info"},
        {"titulo": "Nunca acessaram", "valor": int(df["ultimo_acesso"].isna().sum()), "icone": "⏳",
         "status": "atencao" if df["ultimo_acesso"].isna().any() else "bom", "selo": "aguardando 1º login"},
    ])
    ui.tabela(df, column_config={"alcada": st.column_config.NumberColumn("alçada", format="R$ %.0f"),
                                 "pastas": st.column_config.NumberColumn("pastas/abas")})

    operacoes = operacoes_repo.listar()
    modo = st.radio("O que deseja fazer?", ["➕ Novo usuário", "✏️ Editar usuário", "🔁 Resetar senha"],
                    horizontal=True, key="adm_modo")
    with st.container(border=True):
        if modo.startswith("➕"):
            _form_usuario(None, operacoes)
        else:
            todos = usuarios_repo.listar(apenas_ativos=False)
            regs = [{"id": r["id"], "nome": f"{r['nome']} ({r['login']})"} for r in todos]
            uid = ui.select_registro("Usuário", regs, key="adm_edit")
            if not uid:
                return
            if modo.startswith("✏️"):
                _form_usuario({**usuarios_repo.buscar(uid), **usuarios_repo.carregar_sessao(uid)}, operacoes)
            else:
                st.write("Gera uma senha provisória. O usuário será obrigado a trocá-la no próximo login.")
                if st.button("Gerar senha provisória", type="primary", key="adm_reset"):
                    nova = usuarios_service.resetar_senha(uid)
                    st.success("Senha provisória gerada. Envie ao usuário:")
                    st.code(nova, language=None)


def _aba_operacoes() -> None:
    st.caption("Cada operação (filial/CDD) tem seus próprios fretes, estoques e indicadores.")
    with st.form("f_op", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        nome, cnpj = c1.text_input("Nome"), c2.text_input("CNPJ")
        cidade, uf = c3.text_input("Cidade"), c4.text_input("UF", max_chars=2)
        if st.form_submit_button("➕ Cadastrar operação"):
            ui.acao(cadastros_service.criar_operacao, nome, cnpj, cidade, uf)

    ops = operacoes_repo.listar()
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
    ui.cabecalho("Gestão de Acessos", "Usuários, senhas, permissões por pasta e operações", "🔑")
    a1, a2 = st.tabs(["👤 Usuários & Permissões", "🏢 Operações"])
    with a1:
        _aba_usuarios(usuario)
    with a2:
        _aba_operacoes()
