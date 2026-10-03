"""Puxada › OBZ de frete (Real x Meta)."""
import streamlit as st

from core import ui
from core.auth import e_master
from repositories import fretes_repo
from services import fretes_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    mes = st.text_input("Mês (AAAA-MM)", value=ui.mes_atual(), key="obz_mes")
    r = svc.resumo_obz(operacao_id, mes)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Meta OBZ", ui.moeda(r["meta"]))
    c2.metric("Realizado / comprometido", ui.moeda(r["realizado"]), f"{ui.pct(r['pct'])} da meta",
              delta_color="inverse")
    c3.metric("Saldo", ui.moeda(r["saldo"]))
    c4.metric("Em aprovação", ui.moeda(r["pendente"]))
    if r["meta"]:
        st.progress(min(r["pct"] / 100, 1.0))
        if r["realizado"] + r["pendente"] > r["meta"]:
            st.warning("⚠️ Se as cotações pendentes forem aprovadas, a meta do mês será estourada.")

    if e_master(usuario) or usuario.get("perfil") == "Gestor":
        with st.form("f_meta_obz"):
            v = st.number_input(f"Definir meta de {mes} (R$)", min_value=0.0, value=r["meta"], step=1000.0)
            if st.form_submit_button("Salvar meta"):
                fretes_repo.salvar_meta(operacao_id, mes, v)
                ui.avisar("Meta gravada!")
                st.rerun()

    st.divider()
    st.subheader("Histórico mensal")
    hist = svc.historico_obz(operacao_id)
    if not hist.empty:
        st.bar_chart(hist.set_index("mes_ano")[["meta", "realizado"]])
    ui.tabela(hist)
