"""Puxada › Painel geral de fretes."""
import streamlit as st

from config.settings import StatusFrete
from core import ui
from repositories import fretes_repo
from services import fretes_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    c1, c2 = st.columns([3, 1])
    status = c1.multiselect("Status", StatusFrete.TODOS, default=StatusFrete.TODOS, key="pn_status")
    mes = c2.text_input("Mês do frete (AAAA-MM)", value="", placeholder="todos", key="pn_mes")
    df = fretes_repo.listar_df(operacao_id, status or None, mes or None)

    if not df.empty:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Cotações", len(df))
        k2.metric("Valor total", ui.moeda(df["valor_negociado"].sum()))
        k3.metric("Pendentes", int((df["status"] == StatusFrete.PENDENTE).sum()))
        k4.metric("Ticket médio", ui.moeda(df["valor_negociado"].mean()))

    colunas = ["id", "status", "data_frete", "origem", "destino", "transportadora", "motivo",
               "valor_negociado", "valor_tabela", "centro_custo", "solicitante", "aprovador",
               "numero_cte", "motivo_rejeicao"]
    ui.tabela(df[colunas] if not df.empty else df)
    ui.download_csv(df, "fretes")

    cancelaveis = df[df["status"].isin([StatusFrete.PENDENTE, StatusFrete.APROVADO])] if not df.empty else df
    if not cancelaveis.empty:
        with st.popover("🚫 Cancelar cotação"):
            cid = st.selectbox("Cotação", cancelaveis["id"].tolist(), key="pn_cancel")
            if st.button("Confirmar cancelamento", key="pn_cancel_btn"):
                ui.acao(svc.cancelar, int(cid), usuario, sucesso="Cotação cancelada.")
