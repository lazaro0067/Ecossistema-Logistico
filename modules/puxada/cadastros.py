"""Puxada › Cadastros centrais: trechos, origens/destinos, transportadoras, centros de custo,
carretas, fábricas e motoristas. As tabelas de carretas/fábricas/motoristas editam direto na
célula (✏️) e salvam sozinhas."""
import pandas as pd
import streamlit as st

from config.settings import TIPOS_OD
from core import ui
from modules.componentes.autosave import editor_autosave
from repositories import cadastros_repo, logistica_repo, usuarios_repo
from services import cadastros_service as svc
from services.erros import RegraNegocioError

STATUS_CARRETA = ["Disponível", "Em Trânsito", "Manutenção", "Inativa"]


def _excluir(rotulo: str, registros: list[dict], func, key: str, campo: str = "nome") -> None:
    if not registros:
        return
    with st.popover(f"🗑️ Excluir {rotulo}"):
        rid = ui.select_registro(rotulo.capitalize(), registros, campo, key=f"{key}_sel")
        if st.button("Confirmar", key=f"{key}_btn") and rid:
            ui.acao(func, rid, sucesso="Excluído.")


def _obrig(v, nome):
    v = (v or "").strip()
    if not v:
        raise RegraNegocioError(f"Informe {nome}.")
    return v


def _aba_trechos(operacao_id: int) -> None:
    origens = cadastros_repo.listar_od(operacao_id, "origem")
    destinos = cadastros_repo.listar_od(operacao_id, "destino")
    transps = cadastros_repo.listar_transportadoras()
    aprovs = usuarios_repo.listar_aprovadores()
    if not origens or not destinos:
        st.info("Cadastre primeiro as **Origens/Destinos** (aba ao lado).")
    with st.form("f_trecho", clear_on_submit=True):
        st.caption("O trecho já leva transportadora, valor e aprovador — a solicitação de frete fica a um clique. "
                   "Se o trecho já existir, os dados são atualizados.")
        c1, c2, c3 = st.columns(3)
        o = ui.select_registro("Origem", origens, container=c1, key="tr_o")
        d = ui.select_registro("Destino", destinos, container=c2, key="tr_d")
        tr = ui.select_registro("Transportadora", transps, container=c3, key="tr_t")
        c4, c5, c6, c7, c8 = st.columns(5)
        fr = c4.number_input("Frete (R$)", min_value=0.0, step=100.0)
        ped = c5.number_input("Pedágio (R$)", min_value=0.0)
        rem = c6.number_input("Remunerado (R$)", min_value=0.0)
        km = c7.number_input("Distância (km)", min_value=0.0)
        ap = ui.select_registro("Aprovador", aprovs, container=c8, key="tr_a")
        if st.form_submit_button("💾 Salvar trecho", type="primary"):
            ui.acao(svc.salvar_trecho, operacao_id, o, d, km, ped, rem, fr, tr, ap)
    df = cadastros_repo.listar_trechos_df(operacao_id)
    ui.tabela(df.drop(columns=["origem_id", "destino_id", "transportadora_id", "aprovador_id"]) if not df.empty else df,
              vazio="Nenhum trecho cadastrado.", column_config={
                  "valor_frete": st.column_config.NumberColumn("Frete", format="R$ %.2f"),
                  "pedagio": st.column_config.NumberColumn("Pedágio", format="R$ %.2f"),
                  "valor_remunerado": st.column_config.NumberColumn("Remunerado", format="R$ %.2f")})
    if not df.empty:
        regs = [{"id": r.id, "nome": f"{r.origem} ➔ {r.destino}"} for r in df.itertuples()]
        _excluir("trecho", regs, svc.excluir_trecho, "del_tr")
        ui.downloads(df, "trechos_frete", key="dl_trechos")


def _aba_carretas(operacao_id: int) -> None:
    df = logistica_repo.carretas_df(operacao_id)

    def alterar(linha, alt):
        logistica_repo.salvar_carreta(operacao_id, int(linha["id"]), _obrig(alt.get("placa", linha["placa"]), "a placa").upper(),
                                      alt.get("modelo", linha["modelo"]) or "", float(alt.get("capacidade_hl", linha["capacidade_hl"]) or 0),
                                      alt.get("status", linha["status"]) or STATUS_CARRETA[0])

    def incluir(n):
        logistica_repo.salvar_carreta(operacao_id, None, _obrig(n.get("placa"), "a placa").upper(), n.get("modelo") or "",
                                      float(n.get("capacidade_hl") or 0), n.get("status") or STATUS_CARRETA[0])

    editor_autosave(df, f"ed_carretas_{operacao_id}", ["placa", "modelo", "capacidade_hl", "status"], alterar, incluir,
                    lambda l: logistica_repo.excluir("carretas", int(l["id"])), column_config={
                        "id": None, "placa": st.column_config.TextColumn("Placa ✏️", required=True),
                        "modelo": "Modelo ✏️", "capacidade_hl": st.column_config.NumberColumn("Capacidade (HL) ✏️", min_value=0),
                        "status": st.column_config.SelectboxColumn("Status ✏️", options=STATUS_CARRETA)})


def _aba_fabricas() -> None:
    df = logistica_repo.fabricas_df()

    def alterar(linha, alt):
        logistica_repo.salvar_fabrica(int(linha["id"]), _obrig(alt.get("nome", linha["nome"]), "o nome"),
                                      alt.get("cidade", linha["cidade"]) or "", (alt.get("uf", linha["uf"]) or "").upper())

    def incluir(n):
        logistica_repo.salvar_fabrica(None, _obrig(n.get("nome"), "o nome"), n.get("cidade") or "", (n.get("uf") or "").upper())

    editor_autosave(df, "ed_fabricas", ["nome", "cidade", "uf"], alterar, incluir,
                    lambda l: logistica_repo.excluir("fabricas", int(l["id"])), column_config={
                        "id": None, "nome": st.column_config.TextColumn("Fábrica ✏️", required=True),
                        "cidade": "Cidade ✏️", "uf": st.column_config.TextColumn("UF ✏️", max_chars=2)})


def _aba_motoristas(operacao_id: int) -> None:
    df = logistica_repo.motoristas_df(operacao_id)

    def alterar(linha, alt):
        logistica_repo.salvar_motorista(operacao_id, int(linha["id"]), _obrig(alt.get("nome", linha["nome"]), "o nome"),
                                        alt.get("cnh", linha["cnh"]) or "", alt.get("telefone", linha["telefone"]) or "")

    def incluir(n):
        logistica_repo.salvar_motorista(operacao_id, None, _obrig(n.get("nome"), "o nome"), n.get("cnh") or "",
                                        n.get("telefone") or "")

    editor_autosave(df, f"ed_motoristas_{operacao_id}", ["nome", "cnh", "telefone"], alterar, incluir,
                    lambda l: logistica_repo.excluir("motoristas", int(l["id"])), column_config={
                        "id": None, "nome": st.column_config.TextColumn("Motorista ✏️", required=True),
                        "cnh": "CNH ✏️", "telefone": "Telefone ✏️"})


def render(usuario: dict, operacao_id: int) -> None:
    abas = st.tabs(["🛣️ Trechos", "📍 Origens/Destinos", "🏢 Transportadoras", "🚛 Carretas", "🏭 Fábricas",
                    "👤 Motoristas", "🏷️ Centros de Custo"])
    with abas[0]:
        _aba_trechos(operacao_id)

    with abas[1]:
        with st.form("f_od", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([3, 3, 1, 3])
            nome, cidade = c1.text_input("Nome (ex.: Cervejaria Anápolis)"), c2.text_input("Cidade")
            uf, tipo = c3.text_input("UF", max_chars=2), c4.selectbox("Tipo", TIPOS_OD)
            if st.form_submit_button("➕ Salvar"):
                ui.acao(svc.criar_od, operacao_id, nome, cidade, uf, tipo)
        ods = cadastros_repo.listar_od(operacao_id)
        ui.tabela(pd.DataFrame(ods).drop(columns=["operacao_id"], errors="ignore"))
        _excluir("origem/destino", ods, svc.excluir_od, "del_od")

    with abas[2]:
        with st.form("f_transp", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            n, cnpj, cont = c1.text_input("Nome"), c2.text_input("CNPJ"), c3.text_input("Contato / e-mail / telefone")
            if st.form_submit_button("➕ Salvar"):
                ui.acao(svc.criar_transportadora, n, cnpj, cont)
        regs = cadastros_repo.listar_transportadoras()
        ui.tabela(pd.DataFrame(regs))
        _excluir("transportadora", regs, svc.excluir_transportadora, "del_transp")

    with abas[3]:
        _aba_carretas(operacao_id)
    with abas[4]:
        _aba_fabricas()
    with abas[5]:
        _aba_motoristas(operacao_id)

    with abas[6]:
        with st.form("f_cc", clear_on_submit=True):
            n = st.text_input("Nome do centro de custo")
            if st.form_submit_button("➕ Salvar"):
                ui.acao(svc.criar_centro_custo, n)
        regs = cadastros_repo.listar_centros_custo()
        ui.tabela(pd.DataFrame(regs))
        _excluir("centro de custo", regs, svc.excluir_centro_custo, "del_cc")
