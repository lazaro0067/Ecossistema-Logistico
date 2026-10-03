"""Puxada › Nova cotação de frete."""
import datetime as dt

import streamlit as st

from config.settings import MOTIVOS_FRETE
from core import ui
from repositories import cadastros_repo, usuarios_repo
from services import fretes_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    origens = cadastros_repo.listar_od(operacao_id, "origem")
    destinos = cadastros_repo.listar_od(operacao_id, "destino")
    transps = cadastros_repo.listar_transportadoras()
    ccs = cadastros_repo.listar_centros_custo()
    aprovs = usuarios_repo.listar_aprovadores()

    if not origens or not destinos or not transps:
        st.warning("Cadastre origens, destinos e transportadoras na aba **Cadastros** antes de cotar.")
        return

    st.subheader("Nova cotação de frete")
    c1, c2 = st.columns(2)
    o = ui.select_registro("Origem", origens, container=c1, key="cot_o")
    d = ui.select_registro("Destino", destinos, container=c2, key="cot_d")

    tabela = svc.valor_tabela(operacao_id, o, d)
    if o and d:
        if tabela is not None:
            st.info(f"💡 Valor de tabela deste trecho: **{ui.moeda(tabela)}**")
        else:
            st.caption("Trecho sem valor de tabela cadastrado.")

    with st.form("f_cotacao", clear_on_submit=True):
        c3, c4, c5 = st.columns(3)
        motivo = c3.selectbox("Motivo", MOTIVOS_FRETE)
        tr = ui.select_registro("Transportadora", transps, container=c4)
        data_frete = c5.date_input("Data do frete", value=dt.date.today(), format="DD/MM/YYYY")
        c6, c7, c8 = st.columns(3)
        valor = c6.number_input("Valor negociado (R$)", min_value=0.0, value=float(tabela or 0), step=50.0)
        cc = ui.select_registro("Centro de custo", ccs, container=c7)
        aprov_fmt = [{"id": a["id"], "nome": f"{a['nome']} (até {ui.moeda(a['alcada'])})"} for a in aprovs]
        ap = ui.select_registro("Aprovador", aprov_fmt, container=c8)
        obs = st.text_area("Observação")
        st.caption(f"Solicitante: **{usuario['nome']}**")

        if st.form_submit_button("Enviar para aprovação", type="primary"):
            ui.acao(svc.criar_cotacao, operacao_id=operacao_id, solicitante_id=usuario["id"],
                    origem_id=o, destino_id=d, transportadora_id=tr, centro_custo_id=cc,
                    aprovador_id=ap, data_frete=data_frete, motivo=motivo,
                    valor_negociado=valor, observacao=obs,
                    sucesso="Cotação enviada para aprovação!")
