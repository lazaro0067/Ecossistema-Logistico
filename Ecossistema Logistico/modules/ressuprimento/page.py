"""Módulo Ressuprimento — volume real x sell-in x meta por cesta."""
import streamlit as st

from core import session, ui
from modules.componentes.importador import importador
from repositories import ressuprimento_repo
from services import ressuprimento_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("🔄 Ressuprimento", session.operacao_nome())
    aba_p, aba_m, aba_i = st.tabs(["📊 Aderência", "🎯 Metas mensais", "📥 Importar"])

    meses = ressuprimento_repo.meses_disponiveis(operacao_id) or [ui.mes_atual()]

    with aba_p:
        mes = st.selectbox("Mês", meses, key="rs_mes")
        df = svc.aderencia_mensal(operacao_id, mes)
        if df.empty:
            st.info("Sem lançamentos de ressuprimento para este mês. Importe na aba **Importar**.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Real (HL)", ui.numero(df["real_hl"].sum(), 1))
            c2.metric("Sell-in (HL)", ui.numero(df["sellin_hl"].sum(), 1))
            meta = df["meta_hl"].sum()
            c3.metric("Atingimento da meta", ui.pct(df["real_hl"].sum() / meta * 100) if meta else "—")
            ui.tabela(df)
            cesta = st.selectbox("Evolução diária da cesta", df["cesta"].tolist(), key="rs_cesta")
            evo = svc.evolucao_diaria(operacao_id, mes, cesta)
            st.line_chart(evo.set_index("data")[["real_acum", "sellin_acum"]])

    with aba_m:
        mes_meta = st.text_input("Mês (AAAA-MM)", value=meses[0], key="rs_mes_meta")
        cestas = svc.aderencia_mensal(operacao_id, mes_meta)["cesta"].tolist()
        metas = ressuprimento_repo.metas_df(operacao_id, mes_meta).set_index("cesta")["meta_volume_hl"].to_dict()
        with st.form("f_meta_ress"):
            cesta_nova = st.text_input("Nova cesta (opcional)")
            valores = {c: st.number_input(c, min_value=0.0, value=float(metas.get(c, 0)), key=f"mt_{c}")
                       for c in sorted(set(cestas) | set(metas))}
            nova_meta = st.number_input("Meta da nova cesta (HL)", min_value=0.0)
            if st.form_submit_button("Salvar metas"):
                for c, v in valores.items():
                    ressuprimento_repo.salvar_meta(operacao_id, mes_meta, c, v)
                if cesta_nova.strip():
                    ressuprimento_repo.salvar_meta(operacao_id, mes_meta, cesta_nova.strip(), nova_meta)
                ui.avisar("Metas salvas!")
                st.rerun()

    with aba_i:
        importador(["ressuprimento"], operacao_id, key="imp_rs")
