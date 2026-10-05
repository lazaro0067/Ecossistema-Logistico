"""Puxada › Cadastros › Motoristas — cadastro organizado em 3 partes:
📋 Lista (edição direto na tabela) · ➕ Novo motorista (com CPF + senha do app) · 🔑 Acesso & senha."""
import datetime as dt

import pandas as pd
import streamlit as st

from config.settings import CNH_ALERTA_DIAS
from core import tema, ui
from modules.componentes.autosave import editor_autosave
from repositories import motoristas_repo as repo
from services import carreteiro_service, motoristas_service as svc
from services.erros import RegraNegocioError

SEM_GESTOR = "— sem gestor (avisa o Master) —"
PARTES = ["📋 Lista de motoristas", "➕ Novo motorista", "🔑 Acesso & senha"]


def _cartao_senha(df: pd.DataFrame) -> None:
    """Depois de criar acesso / definir senha: mensagem pronta para copiar ou mandar no WhatsApp."""
    from modules.puxada.app_motorista import link_do_app, link_whatsapp

    nova = st.session_state.pop("mot_senha_nova", None)
    if not nova:
        return
    tel = next((r["telefone"] for r in df.to_dict("records") if r["nome"] == nova["nome"]), None)
    linha_senha = (f"🔑 Senha provisória: {nova['senha']}\n\nNo primeiro acesso você cria a sua senha."
                   if nova.get("senha") else "🔑 Senha: a que foi cadastrada com a Puxada.")
    msg = (f"Olá, {nova['nome'].split()[0]}! Seu acesso ao App Carreteiro do Grupo Lima:\n\n"
           f"🔗 {link_do_app()}\n👤 Login (CPF): {nova['login']}\n{linha_senha}\n\n"
           "Dica: no celular, use “Adicionar à tela inicial”.")
    with st.container(border=True):
        st.success(f"✅ Acesso de **{nova['nome']}** pronto. Envie ao motorista:")
        st.code(msg, language=None)
        st.link_button(f"📲 Enviar para {nova['nome'].split()[0]} pelo WhatsApp", link_whatsapp(msg, tel),
                       type="primary")


# --- ➕ Novo motorista ----------------------------------------------------------
def _novo(operacao_id: int, gestores: list[dict]) -> None:
    with st.form("mot_novo", clear_on_submit=True):
        tema.secao("👤 Dados do motorista")
        c1, c2, c3 = st.columns([2, 1, 1])
        nome = c1.text_input("Nome completo *")
        cpf = c2.text_input("CPF * (é o login do app)", placeholder="só números")
        tel = c3.text_input("Celular (WhatsApp)", placeholder="(62) 99999-0000")

        tema.secao("🪪 CNH", f"O gestor recebe aviso toda semana a partir de {CNH_ALERTA_DIAS // 30} meses antes do vencimento.")
        c4, c5, c6 = st.columns(3)
        cnh = c4.text_input("Nº da CNH")
        validade = c5.date_input("Validade da CNH", value=None, format="DD/MM/YYYY",
                                 min_value=dt.date(2000, 1, 1), max_value=dt.date(2050, 12, 31))
        ids = [None] + [g["id"] for g in gestores]
        nomes = {g["id"]: g["nome"] for g in gestores}
        gestor = c6.selectbox("Gestor responsável", ids, format_func=lambda i: SEM_GESTOR if i is None else nomes[i])

        tema.secao("💵 Remuneração e 🔑 acesso ao App Carreteiro")
        c7, c8, c9 = st.columns(3)
        salario = c7.number_input("Salário fixo (R$)", min_value=0.0, step=100.0)
        senha = c8.text_input("Senha do app", type="password",
                              help="O motorista entra com o CPF e esta senha. Vazio = gera uma senha provisória.")
        conf = c9.text_input("Confirme a senha", type="password")
        if st.form_submit_button("💾 Salvar motorista", type="primary"):
            try:
                if not (cpf or "").strip():
                    raise RegraNegocioError("Informe o CPF — ele é o login do motorista no app.")
                if senha and senha != conf:
                    raise RegraNegocioError("A confirmação não confere com a senha.")
                mid = svc.salvar_motorista(operacao_id, None, nome, cpf, tel, cnh, validade, gestor, salario)
                r = carreteiro_service.salvar_acesso_motorista(mid, cpf, senha or None, conf if senha else None)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["mot_senha_nova"] = {"nome": nome.strip(), **r}
                st.session_state["mot_parte"] = PARTES[0]
                ui.avisar(f"Motorista {nome.strip()} cadastrado com acesso ao app.")
                st.rerun()


# --- 🔑 Acesso & senha ------------------------------------------------------------
def _acesso(df: pd.DataFrame) -> None:
    from modules.puxada.app_motorista import link_do_app, link_whatsapp

    regs = df.to_dict("records")
    mid = ui.select_registro("Motorista", regs, key="mot_acesso_sel", permitir_vazio=False)
    sel = next((r for r in regs if r["id"] == mid), None)
    if not sel:
        return
    tema.kpis([
        {"titulo": "Login do app", "valor": sel.get("acesso") or "—", "icone": "👤",
         "status": "info" if sel.get("acesso") else "neutro"},
        {"titulo": "Situação", "valor": sel["situacao_acesso"], "icone": "📱",
         "status": {"Ativo": "bom", "Bloqueado": "critico"}.get(sel["situacao_acesso"], "atencao")},
        {"titulo": "Último acesso", "valor": (sel.get("ultimo_acesso") or "nunca")[:16], "icone": "🕒",
         "status": "info"},
    ])
    c1, c2 = st.columns(2)
    with c1, st.form(f"mot_senha_{mid}", clear_on_submit=True):
        if sel.get("usuario_id"):
            tema.secao("Alterar senha", "O motorista passa a entrar com o CPF e a nova senha.")
        else:
            tema.secao("Criar acesso", "Login = CPF do motorista.")
        login = st.text_input("Login (CPF)", value=sel.get("acesso") or sel.get("cpf") or "",
                              disabled=bool(sel.get("usuario_id")))
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Confirme a senha", type="password")
        if st.form_submit_button("💾 Salvar senha" if sel.get("usuario_id") else "🔑 Criar acesso", type="primary"):
            try:
                if sel.get("usuario_id"):
                    carreteiro_service.definir_senha_motorista(mid, nova, conf)
                    st.session_state["mot_senha_nova"] = {"nome": sel["nome"], "login": sel["acesso"], "senha": None}
                else:
                    if not nova:
                        raise RegraNegocioError("Defina a senha do motorista.")
                    r = carreteiro_service.salvar_acesso_motorista(mid, login, nova, conf)
                    st.session_state["mot_senha_nova"] = {"nome": sel["nome"], **r}
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar("Senha salva." if sel.get("usuario_id") else "Acesso criado.")
                st.rerun()
    with c2:
        tema.secao("Outras ações")
        msg = (f"Olá, {sel['nome'].split()[0]}! Link do App Carreteiro do Grupo Lima:\n{link_do_app()}"
               + (f"\n\nLogin (CPF): {sel['acesso']}" if sel.get("acesso") else ""))
        st.link_button("📲 Mandar o link pelo WhatsApp", link_whatsapp(msg, sel.get("telefone")), **ui.LARGURA)
        if sel.get("usuario_id"):
            if st.button("🎲 Gerar senha provisória", key=f"mot_prov_{mid}", **ui.LARGURA,
                         help="Gera uma senha aleatória; o motorista cria a dele no próximo acesso."):
                senha = carreteiro_service.nova_senha_motorista(mid)
                st.session_state["mot_senha_nova"] = {"nome": sel["nome"], "login": sel["acesso"], "senha": senha}
                st.rerun()
            ativo = sel["situacao_acesso"] == "Ativo"
            if st.button("🔒 Bloquear acesso" if ativo else "🔓 Desbloquear acesso", key=f"mot_bloq_{mid}", **ui.LARGURA):
                ui.acao(carreteiro_service.bloquear_acesso, mid, not ativo,
                        sucesso="Acesso bloqueado." if ativo else "Acesso liberado.")
        with st.popover("🗑️ Excluir motorista", **ui.LARGURA):
            st.caption("Motorista com viagens lançadas não pode ser excluído — bloqueie o acesso.")
            if st.button(f"Confirmar exclusão de {sel['nome'].split()[0]}", key=f"mot_excluir_{mid}"):
                from database.connection import tipo_violacao
                from repositories import logistica_repo

                try:
                    logistica_repo.excluir("motoristas", int(mid))
                except Exception as e:
                    st.error("Este motorista tem viagens lançadas e não pode ser excluído."
                             if tipo_violacao(e) == "fk" else f"Não foi possível excluir: {e}")
                else:
                    ui.avisar("Motorista excluído.", "info")
                    st.rerun()


# --- 📋 Lista ---------------------------------------------------------------------------
def _lista(operacao_id: int, df: pd.DataFrame, gestores: list[dict]) -> None:
    st.caption("Clique na célula ✏️ para editar — salva sozinho. Senha e acesso ficam em **🔑 Acesso & senha**.")
    nomes_gestor = {g["nome"]: g["id"] for g in gestores}
    ed = df[["id", "nome", "cpf", "telefone", "cnh", "validade", "situacao_cnh", "gestor", "salario_fixo",
             "situacao_acesso"]].copy()
    ed["gestor"] = ed["gestor"].fillna(SEM_GESTOR)
    ed["salario_fixo"] = pd.to_numeric(ed["salario_fixo"], errors="coerce").fillna(0.0)
    for c in ("cpf", "telefone", "cnh"):
        ed[c] = ed[c].fillna("")

    def alterar(linha, alt):
        atual = {**linha, **alt}
        gestor = atual.get("gestor")
        svc.salvar_motorista(operacao_id, int(linha["id"]), atual.get("nome"), atual.get("cpf") or "",
                             atual.get("telefone") or "", atual.get("cnh") or "", atual.get("validade"),
                             nomes_gestor.get(gestor) if gestor and gestor != SEM_GESTOR else None,
                             atual.get("salario_fixo"))

    editor_autosave(ed, f"ed_mot_{operacao_id}", ["nome", "cpf", "telefone", "cnh", "validade", "gestor",
                                                  "salario_fixo"], alterar, column_config={
        "id": None,
        "nome": st.column_config.TextColumn("Motorista ✏️", required=True, width="medium"),
        "cpf": st.column_config.TextColumn("CPF ✏️"),
        "telefone": st.column_config.TextColumn("Celular ✏️"),
        "cnh": st.column_config.TextColumn("Nº CNH ✏️"),
        "validade": st.column_config.DateColumn("Validade CNH ✏️", format="DD/MM/YYYY"),
        "situacao_cnh": st.column_config.TextColumn("Situação da CNH", width="medium"),
        "gestor": st.column_config.SelectboxColumn("Gestor ✏️", options=[SEM_GESTOR, *nomes_gestor], width="medium"),
        "salario_fixo": st.column_config.NumberColumn("Salário fixo ✏️", format="R$ %.2f", min_value=0),
        "situacao_acesso": st.column_config.TextColumn("App")})
    ui.downloads(df[["nome", "cpf", "telefone", "cnh", "cnh_validade", "situacao_cnh", "gestor", "salario_fixo",
                     "situacao_acesso"]], "motoristas", key="dl_motoristas")


def render(operacao_id: int) -> None:
    df = repo.lista_df(operacao_id)
    gestores = repo.gestores()
    _cartao_senha(df)

    if not df.empty:
        df["validade"] = df["cnh_validade"].map(svc._data)
        info = df["cnh_validade"].map(svc.status_cnh)
        df["situacao_cnh"] = [i[1] for i in info]
        dias = pd.Series([i[2] for i in info], index=df.index, dtype="float")
    else:
        dias = pd.Series(dtype="float")
    vis_cols = ["nome", "cpf", "telefone", "cnh", "situacao_cnh", "gestor", "salario_fixo", "situacao_acesso"]
    cfg = {"nome": "Motorista", "cpf": "CPF", "telefone": "Celular", "cnh": "CNH", "situacao_cnh": "Validade da CNH",
           "gestor": "Gestor", "salario_fixo": st.column_config.NumberColumn("Salário fixo", format="R$ %.2f"),
           "situacao_acesso": "App"}

    def lista(mask=None):
        if df.empty:
            return pd.DataFrame(columns=vis_cols)
        return (df if mask is None else df[mask])[vis_cols]

    vencendo = (dias >= 0) & (dias <= CNH_ALERTA_DIAS)
    vencidas = dias < 0
    sem_validade = df["validade"].isna() if not df.empty else pd.Series(dtype=bool)
    sem_app = df["situacao_acesso"] != "Ativo" if not df.empty else pd.Series(dtype=bool)
    tema.kpis([
        {"titulo": "Motoristas", "valor": len(df), "icone": "👤", "status": "info", "dados": lista(), "colunas": cfg},
        {"titulo": "Com acesso ao app", "valor": int((~sem_app).sum()), "icone": "📱",
         "status": "atencao" if sem_app.any() else "bom", "detalhe": f"{int(sem_app.sum())} sem acesso",
         "dados": lista(sem_app), "colunas": cfg},
        {"titulo": "CNH vence em até 3 meses", "valor": int(vencendo.sum()), "icone": "🪪",
         "status": "atencao" if vencendo.any() else "bom", "selo": "renovar" if vencendo.any() else "em dia",
         "dados": lista(vencendo), "colunas": cfg},
        {"titulo": "CNH vencida", "valor": int(vencidas.sum()), "icone": "⛔",
         "status": "critico" if vencidas.any() else "bom", "selo": "não pode rodar" if vencidas.any() else "nenhuma",
         "dados": lista(vencidas), "colunas": cfg},
        {"titulo": "Sem validade da CNH", "valor": int(sem_validade.sum()), "icone": "❔",
         "status": "atencao" if sem_validade.any() else "bom", "dados": lista(sem_validade), "colunas": cfg},
    ], key="kp_motoristas")

    with st.container(key="nav_mot_partes"):
        parte = ui._escolha("mot_parte", PARTES, PARTES[0] if not df.empty else PARTES[1], pills=True)
    if parte == PARTES[1]:
        _novo(operacao_id, gestores)
    elif df.empty:
        st.info("Nenhum motorista cadastrado nesta filial. Use **➕ Novo motorista**.")
    elif parte == PARTES[2]:
        _acesso(df)
    else:
        _lista(operacao_id, df, gestores)
