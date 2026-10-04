"""Puxada › Cadastros de apoio (OD, trechos, transportadoras, centros de custo)."""
import pandas as pd
import streamlit as st

from config.settings import TIPOS_OD
from core import ui
from repositories import cadastros_repo
from services import cadastros_service as svc


def _excluir(rotulo: str, registros: list[dict], func, key: str, campo: str = "nome") -> None:
    if not registros:
        return
    with st.popover(f"🗑️ Excluir {rotulo}"):
        rid = ui.select_registro(rotulo.capitalize(), registros, campo, key=f"{key}_sel")
        if st.button("Confirmar", key=f"{key}_btn") and rid:
            ui.acao(func, rid, sucesso="Excluído.")


def render(usuario: dict, operacao_id: int) -> None:
    t_od, t_tr, t_transp, t_cc = st.tabs(["Origens/Destinos", "Trechos", "Transportadoras", "Centros de Custo"])

    with t_od:
        with st.form("f_od", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([3, 3, 1, 3])
            nome, cidade = c1.text_input("Nome"), c2.text_input("Cidade")
            uf, tipo = c3.text_input("UF", max_chars=2), c4.selectbox("Tipo", TIPOS_OD)
            if st.form_submit_button("+ Salvar"):
                ui.acao(svc.criar_od, operacao_id, nome, cidade, uf, tipo)
        ods = cadastros_repo.listar_od(operacao_id)
        ui.tabela(pd.DataFrame(ods).drop(columns=["operacao_id"], errors="ignore"))
        _excluir("origem/destino", ods, svc.excluir_od, "del_od")

    with t_tr:
        origens = cadastros_repo.listar_od(operacao_id, "origem")
        destinos = cadastros_repo.listar_od(operacao_id, "destino")
        with st.form("f_trecho", clear_on_submit=True):
            st.caption("Se o trecho já existir, os valores são atualizados.")
            c1, c2, c3 = st.columns(3)
            o = ui.select_registro("Origem", origens, container=c1, key="tr_o")
            d = ui.select_registro("Destino", destinos, container=c2, key="tr_d")
            km = c3.number_input("Distância (km)", min_value=0.0)
            c4, c5, c6 = st.columns(3)
            ped = c4.number_input("Pedágio (R$)", min_value=0.0)
            rem = c5.number_input("Remunerado (R$)", min_value=0.0)
            fr = c6.number_input("Frete (R$)", min_value=0.0)
            if st.form_submit_button("+ Salvar trecho"):
                ui.acao(svc.salvar_trecho, operacao_id, o, d, km, ped, rem, fr)
        df = cadastros_repo.listar_trechos_df(operacao_id)
        ui.tabela(df, vazio="Nenhum trecho cadastrado.")
        if not df.empty:
            regs = [{"id": r.id, "nome": f"{r.origem} ➔ {r.destino}"} for r in df.itertuples()]
            _excluir("trecho", regs, svc.excluir_trecho, "del_tr")

    with t_transp:
        with st.form("f_transp", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            n, cnpj, cont = c1.text_input("Nome"), c2.text_input("CNPJ"), c3.text_input("Contato")
            if st.form_submit_button("+ Salvar"):
                ui.acao(svc.criar_transportadora, n, cnpj, cont)
        regs = cadastros_repo.listar_transportadoras()
        ui.tabela(pd.DataFrame(regs))
        _excluir("transportadora", regs, svc.excluir_transportadora, "del_transp")

    with t_cc:
        with st.form("f_cc", clear_on_submit=True):
            n = st.text_input("Nome do centro de custo")
            if st.form_submit_button("+ Salvar"):
                ui.acao(svc.criar_centro_custo, n)
        regs = cadastros_repo.listar_centros_custo()
        ui.tabela(pd.DataFrame(regs))
        _excluir("centro de custo", regs, svc.excluir_centro_custo, "del_cc")
