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
        div = svc.divergencia(r.valor_negociado, r.valor_tabela)
        diferente = div is not None and abs(div[0]) >= 0.01
        sinal = ("🔺" if div and div[0] > 0 else "🔻") if diferente else ("✅" if div is not None else "⚪")
        tipo = getattr(r, "tipo_carga", None)
        tipo = tipo if isinstance(tipo, str) else ""
        with st.expander(f"{sinal} #{r.id} · {r.origem} ➔ {r.destino} · {tipo} · {ui.moeda(r.valor_negociado)}",
                         expanded=True):
            if div is None:
                st.info("⚪ Sem frete cadastrado para este trecho/transportadora/tipo — confira o valor.")
            elif diferente:
                (st.error if div[0] > 0 else st.warning)(
                    f"**Frete {svc.texto_divergencia(r.valor_negociado, r.valor_tabela)}** — cadastrado "
                    f"{ui.moeda(r.valor_tabela)} · negociado {ui.moeda(r.valor_negociado)}. "
                    "Para aprovar é obrigatório justificar (fica no relatório).")
            else:
                st.success(f"✅ Igual ao frete cadastrado ({ui.moeda(r.valor_tabela)}).")
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Transportadora:** {r.transportadora}")
            c1.write(f"**Carga:** {tipo or '—'}")
            c2.write(f"**Solicitante:** {r.solicitante}")
            c2.write(f"**Data do frete:** {r.data_frete} · **Motivo:** {r.motivo}")
            c3.write(f"**Centro de custo:** {r.centro_custo or '-'}")
            c3.write(f"**Aprovador:** {r.aprovador}")
            if r.observacao:
                st.write(f"**Obs. do solicitante:** {r.observacao}")
            just = st.text_input("Justificativa da aprovação" + (" *" if diferente else " (opcional)"),
                                 key=f"just_{r.id}", placeholder="Ex.: carga urgente, sem transportadora na tabela...")
            motivo = st.text_input("Motivo (obrigatório para rejeitar)", key=f"mot_{r.id}")
            a, b = st.columns(2)
            if a.button("✅ Aprovar", key=f"ap_{r.id}", type="primary"):
                ui.acao(svc.aprovar, r.id, usuario, just, sucesso=f"Cotação #{r.id} aprovada.")
            if b.button("❌ Rejeitar", key=f"rej_{r.id}"):
                ui.acao(svc.rejeitar, r.id, usuario, motivo, sucesso=f"Cotação #{r.id} rejeitada.")
    ui.downloads(df, "fretes_pendentes_aprovacao", key="dl_aprov")
