"""Puxada › Cadastros › Motoristas — cadastro claro, validade da CNH, gestor responsável,
salário fixo e criação do acesso ao App Carreteiro."""
import datetime as dt

import pandas as pd
import streamlit as st

from config.settings import CNH_ALERTA_DIAS
from core import tema, tempo, ui
from modules.componentes.autosave import editor_autosave
from repositories import motoristas_repo as repo
from services import carreteiro_service, motoristas_service as svc
from services.erros import RegraNegocioError

SEM_GESTOR = "— sem gestor (avisa o Master) —"


def _cartao_senha(df: pd.DataFrame) -> None:
    """Depois de criar acesso / nova senha: mensagem pronta para copiar ou mandar no WhatsApp."""
    from modules.puxada.app_motorista import link_do_app, link_whatsapp

    nova = st.session_state.pop("mot_senha_nova", None)
    if not nova:
        return
    link = link_do_app()
    tel = next((r["telefone"] for r in df.to_dict("records") if r["nome"] == nova["nome"]), None)
    msg = (f"Olá, {nova['nome'].split()[0]}! Seu acesso ao App Carreteiro do Grupo Lima:\n\n"
           f"🔗 {link}\n👤 Login: {nova['login']}\n🔑 Senha provisória: {nova['senha']}\n\n"
           "No primeiro acesso você cria a sua senha. Dica: no celular, use “Adicionar à tela inicial”.")
    with st.container(border=True):
        st.success(f"🔑 Acesso de **{nova['nome']}** pronto — a senha aparece só agora. Envie ao motorista:")
        st.code(msg, language=None)
        st.link_button(f"📲 Enviar para {nova['nome'].split()[0]} pelo WhatsApp", link_whatsapp(msg, tel),
                       type="primary")


def _novo(operacao_id: int, gestores: list[dict]) -> None:
    with st.expander("➕ Novo motorista", expanded=False):
        with st.form("mot_novo", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            nome = c1.text_input("Nome completo *")
            cpf = c2.text_input("CPF", placeholder="só números")
            tel = c3.text_input("Celular (WhatsApp)", placeholder="(62) 99999-0000")
            c4, c5, c6, c7 = st.columns(4)
            cnh = c4.text_input("Nº da CNH")
            validade = c5.date_input("Validade da CNH", value=None, format="DD/MM/YYYY",
                                     min_value=dt.date(2000, 1, 1), max_value=dt.date(2050, 12, 31))
            salario = c6.number_input("Salário fixo (R$)", min_value=0.0, step=100.0)
            ids = [None] + [g["id"] for g in gestores]
            nomes = {g["id"]: g["nome"] for g in gestores}
            gestor = c7.selectbox("Gestor responsável", ids, format_func=lambda i: SEM_GESTOR if i is None else nomes[i],
                                  help="Recebe os avisos de CNH vencendo.")
            criar = st.checkbox("🔑 Já criar o acesso ao App Carreteiro (login = CPF; sem CPF, usa o celular)",
                                value=True)
            if st.form_submit_button("💾 Salvar motorista", type="primary"):
                try:
                    mid = svc.salvar_motorista(operacao_id, None, nome, cpf, tel, cnh, validade, gestor, salario)
                    if criar and (cpf or tel):
                        r = carreteiro_service.salvar_acesso_motorista(mid, cpf or tel)
                        if r["senha"]:
                            st.session_state["mot_senha_nova"] = {"nome": nome.strip(), **r}
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    ui.avisar(f"Motorista {nome.strip()} cadastrado.")
                    st.rerun()


def _acoes(operacao_id: int, df: pd.DataFrame) -> None:
    from modules.puxada.app_motorista import link_do_app, link_whatsapp

    tema.secao("Ações do motorista", "Criar acesso ao app, gerar nova senha, mandar o link ou excluir.")
    regs = df.to_dict("records")
    c1, c2 = st.columns([2, 3])
    mid = ui.select_registro("Motorista", regs, key="mot_acao_sel", permitir_vazio=False, container=c1)
    sel = next((r for r in regs if r["id"] == mid), None)
    if not sel:
        return
    with c2:
        b1, b2, b3 = st.columns(3)
        if not sel.get("usuario_id"):
            login = sel.get("cpf") or sel.get("telefone") or ""
            if b1.button("🔑 Criar acesso", type="primary", key="mot_criar", **ui.LARGURA,
                         help="Login = CPF (ou celular, se não houver CPF)."):
                try:
                    if not login:
                        raise RegraNegocioError("Cadastre o CPF ou o celular do motorista para criar o acesso.")
                    r = carreteiro_service.salvar_acesso_motorista(mid, login)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    st.session_state["mot_senha_nova"] = {"nome": sel["nome"], **r}
                    st.rerun()
        else:
            if b1.button("🔄 Nova senha", key="mot_reset", **ui.LARGURA):
                try:
                    senha = carreteiro_service.nova_senha_motorista(mid)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    st.session_state["mot_senha_nova"] = {"nome": sel["nome"], "login": sel["acesso"], "senha": senha}
                    st.rerun()
        msg = (f"Olá, {sel['nome'].split()[0]}! Link do App Carreteiro do Grupo Lima:\n{link_do_app()}"
               + (f"\n\nLogin: {sel['acesso']} (use a senha que você criou)." if sel.get("acesso") else ""))
        b2.link_button("📲 WhatsApp", link_whatsapp(msg, sel.get("telefone")), **ui.LARGURA)
        with b3.popover("🗑️ Excluir"):
            st.caption("Motorista com viagens lançadas não pode ser excluído — bloqueie o acesso no App Carreteiro.")
            if st.button(f"Confirmar exclusão de {sel['nome'].split()[0]}", key="mot_excluir"):
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


def render(operacao_id: int) -> None:
    df = repo.lista_df(operacao_id)
    gestores = repo.gestores()
    _cartao_senha(df)

    if not df.empty:
        df["validade"] = df["cnh_validade"].map(svc._data)
        info = df["cnh_validade"].map(svc.status_cnh)
        df["situacao_cnh"] = [i[1] for i in info]
        df["_dias"] = [i[2] for i in info]
    vis_cols = ["nome", "cpf", "telefone", "cnh", "situacao_cnh", "gestor", "salario_fixo", "situacao_acesso"]

    def lista(mask=None):
        base = df if mask is None else df[mask]
        return base[vis_cols] if not base.empty else pd.DataFrame(columns=vis_cols)

    cfg = {"nome": "Motorista", "cpf": "CPF", "telefone": "Celular", "cnh": "CNH", "situacao_cnh": "Validade da CNH",
           "gestor": "Gestor", "salario_fixo": st.column_config.NumberColumn("Salário fixo", format="R$ %.2f"),
           "situacao_acesso": "App"}
    dias = df["_dias"] if not df.empty else pd.Series(dtype=float)
    vencendo = (dias >= 0) & (dias <= CNH_ALERTA_DIAS) if not df.empty else None
    vencidas = dias < 0 if not df.empty else None
    tema.kpis([
        {"titulo": "Motoristas", "valor": len(df), "icone": "👤", "status": "info", "dados": lista(), "colunas": cfg},
        {"titulo": "Com acesso ao app", "valor": int((df["situacao_acesso"] == "Ativo").sum()) if not df.empty else 0,
         "icone": "📱", "status": "info", "colunas": cfg,
         "dados": lista(df["situacao_acesso"] != "Ativo") if not df.empty else lista(), "ver": "quem falta"},
        {"titulo": "CNH vence em até 3 meses", "valor": int(vencendo.sum()) if vencendo is not None else 0,
         "icone": "🪪", "status": "atencao" if vencendo is not None and vencendo.any() else "bom",
         "selo": "renovar" if vencendo is not None and vencendo.any() else "em dia",
         "dados": lista(vencendo) if vencendo is not None else lista(), "colunas": cfg},
        {"titulo": "CNH vencida", "valor": int(vencidas.sum()) if vencidas is not None else 0, "icone": "⛔",
         "status": "critico" if vencidas is not None and vencidas.any() else "bom",
         "selo": "não pode rodar" if vencidas is not None and vencidas.any() else "nenhuma",
         "dados": lista(vencidas) if vencidas is not None else lista(), "colunas": cfg},
        {"titulo": "Sem validade da CNH", "valor": int(df["validade"].isna().sum()) if not df.empty else 0,
         "icone": "❔", "status": "atencao" if not df.empty and df["validade"].isna().any() else "bom",
         "dados": lista(df["validade"].isna()) if not df.empty else lista(), "colunas": cfg, "ver": "completar"},
    ], key="kp_motoristas")

    _novo(operacao_id, gestores)
    if df.empty:
        st.info("Nenhum motorista cadastrado nesta filial. Use **➕ Novo motorista**.")
        return

    tema.secao("Motoristas da filial", "Clique na célula para editar (✏️) — salva sozinho. "
               f"A partir de {CNH_ALERTA_DIAS // 30} meses antes do vencimento, o gestor recebe aviso toda semana.")
    nomes_gestor = {g["nome"]: g["id"] for g in gestores}
    ed = df[["id", "nome", "cpf", "telefone", "cnh", "validade", "situacao_cnh", "gestor", "salario_fixo",
             "situacao_acesso", "acesso"]].copy()
    ed["gestor"] = ed["gestor"].fillna(SEM_GESTOR)
    ed["salario_fixo"] = pd.to_numeric(ed["salario_fixo"], errors="coerce").fillna(0.0)

    def alterar(linha, alt):
        atual = {**linha, **alt}
        gestor = atual.get("gestor")
        svc.salvar_motorista(operacao_id, int(linha["id"]), atual.get("nome"), atual.get("cpf") or "",
                             atual.get("telefone") or "", atual.get("cnh") or "", atual.get("validade"),
                             nomes_gestor.get(gestor) if gestor and gestor != SEM_GESTOR else None,
                             atual.get("salario_fixo"))

    editor_autosave(ed, f"ed_mot_{operacao_id}", ["nome", "cpf", "telefone", "cnh", "validade", "gestor",
                                                  "salario_fixo"], alterar, column_config={
        "id": None, "acesso": None,
        "nome": st.column_config.TextColumn("Motorista ✏️", required=True, width="medium"),
        "cpf": st.column_config.TextColumn("CPF ✏️", width="small"),
        "telefone": st.column_config.TextColumn("Celular ✏️", width="small"),
        "cnh": st.column_config.TextColumn("Nº CNH ✏️", width="small"),
        "validade": st.column_config.DateColumn("Validade CNH ✏️", format="DD/MM/YYYY"),
        "situacao_cnh": st.column_config.TextColumn("Situação da CNH", width="medium"),
        "gestor": st.column_config.SelectboxColumn("Gestor ✏️", options=[SEM_GESTOR, *nomes_gestor]),
        "salario_fixo": st.column_config.NumberColumn("Salário fixo ✏️", format="R$ %.2f", min_value=0),
        "situacao_acesso": st.column_config.TextColumn("App", width="small")})
    _acoes(operacao_id, df)
    ui.downloads(df[vis_cols + ["cnh_validade"]], "motoristas", key="dl_motoristas")
