"""Puxada › Aprovação de fretes."""
import streamlit as st

from config.settings import StatusFrete
from core import ui
from core.auth import e_master
from repositories import fretes_repo
from services import fretes_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    so_minhas = not e_master(usuario)
    df = fretes_repo.listar_df(operacao_id, [StatusFrete.PENDENTE],
                               aprovador_id=usuario["id"] if so_minhas else None)
    st.subheader("Fretes aguardando " + ("sua aprovação" if so_minhas else "aprovação"))
    if df.empty:
        st.info("Nenhum frete pendente. ✅")
        return

    for r in df.itertuples():
        dif = ""
        if r.valor_tabela:
            delta = (r.valor_negociado - r.valor_tabela) / r.valor_tabela * 100
            dif = f" | {'🔺' if delta > 0 else '🔻'} {ui.pct(abs(delta))} vs tabela"
        with st.expander(f"#{r.id} · {r.origem} ➔ {r.destino} · {ui.moeda(r.valor_negociado)}{dif}"):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Transportadora:** {r.transportadora}")
            c1.write(f"**Motivo:** {r.motivo}")
            c2.write(f"**Solicitante:** {r.solicitante}")
            c2.write(f"**Data do frete:** {r.data_frete}")
            c3.write(f"**Centro de custo:** {r.centro_custo or '-'}")
            c3.write(f"**Aprovador:** {r.aprovador}")
            if r.observacao:
                st.write(f"**Obs.:** {r.observacao}")

            motivo = st.text_input("Motivo (obrigatório para rejeitar)", key=f"mot_{r.id}")
            a, b = st.columns(2)
            if a.button("✅ Aprovar", key=f"ap_{r.id}", type="primary"):
                ui.acao(svc.aprovar, r.id, usuario, sucesso=f"Cotação #{r.id} aprovada.")
            if b.button("❌ Rejeitar", key=f"rej_{r.id}"):
                ui.acao(svc.rejeitar, r.id, usuario, motivo, sucesso=f"Cotação #{r.id} rejeitada.")
