"""Painel Master — usuários, permissões por pasta e operações."""
import pandas as pd
import streamlit as st

from config.settings import MODULOS, PERFIL_MASTER, PERFIS
from core import tema, ui
from repositories import operacoes_repo, usuarios_repo
from services import cadastros_service, email_service, usuarios_service
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

    st.markdown("**Dados de acesso** — o e-mail é o login")
    c1, c2, c3 = st.columns(3)
    email = c1.text_input("E-mail (login) *", value=u.get("email") or "", key=f"{chave}_email",
                          placeholder="nome@grupolima.com.br")
    nome = c2.text_input("Nome completo *", value=u.get("nome", ""), key=f"{chave}_nome")
    smtp_ok = email_service.configurado()
    rot_senha = ("Nova senha (vazio = manter)" if existente else
                 "Senha inicial (vazio = gerar e enviar por e-mail)" if smtp_ok else "Senha inicial (vazio = gerar)")
    senha = c3.text_input(rot_senha, type="password", key=f"{chave}_senha")
    c5, c6 = st.columns([2, 1])
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
            res = usuarios_service.salvar_usuario(
                id=u.get("id"), nome=nome, senha=senha, email=email, cargo=cargo, perfil=perfil,
                e_aprovador=aprov, alcada=alcada, ativo=ativo, trocar_senha=trocar, permissoes=permissoes,
                operacoes=ops, enviar_email=True)
        except RegraNegocioError as e:
            st.error(str(e))
            return
        st.session_state["_adm_ver"] = st.session_state.get("_adm_ver", 0) + 1  # limpa o formulário
        if res["email_enviado"]:
            ui.avisar(f"Usuário '{nome}' criado! Os dados de acesso foram enviados para {email.strip().lower()}.")
        elif res["senha_provisoria"]:
            st.session_state["_adm_senha"] = (nome, email.strip().lower(), res["senha_provisoria"])
            ui.avisar(f"Usuário '{nome}' criado!")
        else:
            ui.avisar(f"Usuário '{nome}' salvo!")
        st.rerun()


def _aba_usuarios(usuario_logado: dict) -> None:
    if st.session_state.get("_adm_senha"):
        nome, email, senha = st.session_state["_adm_senha"]
        st.success(f"Envie ao usuário **{nome}** — login: **{email}** · senha provisória:")
        st.code(senha, language=None)
        if st.button("✓ Já anotei", key="adm_senha_ok"):
            st.session_state.pop("_adm_senha")
            st.rerun()
    if not email_service.configurado():
        st.info("📧 O envio de e-mail não está configurado: senhas provisórias aparecem na tela e o "
                "“Esqueci minha senha” fica indisponível. Veja o README (seção E-mail) para ativar.")
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
            regs = [{"id": r["id"], "nome": f"{r['nome']} ({r['email'] or r['login']})"} for r in todos]
            uid = ui.select_registro("Usuário", regs, key="adm_edit")
            if not uid:
                return
            if modo.startswith("✏️"):
                _form_usuario({**usuarios_repo.buscar(uid), **usuarios_repo.carregar_sessao(uid)}, operacoes)
            else:
                alvo = usuarios_repo.buscar(uid)
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Código por e-mail** — o próprio usuário cria a nova senha.")
                    if st.button(f"📧 Enviar código para {alvo['email'] or '—'}", key="adm_codigo",
                                 disabled=not (email_service.configurado() and alvo["email"])):
                        try:
                            usuarios_service.solicitar_codigo(alvo["email"])
                        except RegraNegocioError as e:
                            st.error(str(e))
                        else:
                            st.success("Código enviado. O usuário usa “Esqueci minha senha” na tela de login.")
                with c2:
                    st.write("**Senha provisória** — troca obrigatória no próximo login.")
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


def _aba_importar_antigo() -> None:
    import contextlib
    import io
    import sqlite3
    import tempfile

    st.caption("Traga os dados do sistema antigo (arquivo puxada_ambev.db). Os bancos antigos não são alterados; "
               "o que já existir aqui é atualizado, sem duplicar. Usuários antigos entram com troca de senha obrigatória.")
    c1, c2 = st.columns(2)
    principal = c1.file_uploader("Banco principal antigo (puxada_ambev.db)", type=["db", "sqlite", "sqlite3"],
                                 key="mig_principal")
    puxada = c2.file_uploader("Banco do 'Sistema Puxada' (opcional)", type=["db", "sqlite", "sqlite3"], key="mig_puxada")
    ops = [o["nome"] for o in operacoes_repo.listar(apenas_ativas=True) if not o.get("membros")]
    op_pux = (st.selectbox("Operação dos fretes do Sistema Puxada", ops, key="mig_op",
                           index=ops.index("Lima Rio Verde") if "Lima Rio Verde" in ops else 0)
              if puxada and ops else None)
    if not principal or not st.button("📦 Importar dados antigos", type="primary", key="mig_btn"):
        return
    from scripts import migrar_banco_antigo as mig

    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log), tempfile.TemporaryDirectory() as tmp:
            caminhos = []
            for nome, arq in (("principal.db", principal), ("puxada.db", puxada)):
                if arq:
                    caminho = f"{tmp}/{nome}"
                    with open(caminho, "wb") as f:
                        f.write(arq.getvalue())
                    caminhos.append(caminho)
            con = sqlite3.connect(caminhos[0])
            con.row_factory = sqlite3.Row
            mig.migrar_principal(con)
            if puxada and op_pux:
                con2 = sqlite3.connect(caminhos[1])
                con2.row_factory = sqlite3.Row
                mig.migrar_puxada(con2, op_pux)
    except Exception as e:
        st.error(f"A importação parou: {e}")
    else:
        st.success("Importação concluída!")
    st.code(log.getvalue() or "(sem saída)", language=None)


def render(usuario: dict, operacao_id: int | None) -> None:
    ui.cabecalho("Gestão de Acessos", "Usuários, senhas, permissões por pasta e operações", "🔑")
    a1, a2, a3 = st.tabs(["👤 Usuários & Permissões", "🏢 Operações", "📦 Importar sistema antigo"])
    with a1:
        _aba_usuarios(usuario)
    with a2:
        _aba_operacoes()
    with a3:
        _aba_importar_antigo()
