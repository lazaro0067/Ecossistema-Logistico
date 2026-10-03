"""Puxada › Pedidos marcados (aderência solicitado x marcado)."""
import streamlit as st

from core import ui
from modules.componentes.importador import importador
from repositories import ressuprimento_repo


def render(usuario: dict, operacao_id: int) -> None:
    datas = ressuprimento_repo.datas_puxada(operacao_id)
    aba_v, aba_i = st.tabs(["Consulta", "Importar planilha"])

    with aba_v:
        if not datas:
            st.info("Nenhum pedido marcado importado ainda.")
        else:
            data = st.selectbox("Data da puxada", datas, key="pm_data")
            df = ressuprimento_repo.pedidos_marcados_df(operacao_id, data)
            sol, mar = df["cx_solicitadas"].sum(), df["cx_marcadas"].sum()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Pedidos", df["numero_pedido"].nunique())
            c2.metric("Cx solicitadas", ui.numero(sol))
            c3.metric("Cx marcadas", ui.numero(mar))
            c4.metric("Aderência", ui.pct(mar / sol * 100 if sol else 0))
            df["aderencia_%"] = (df["cx_marcadas"] / df["cx_solicitadas"].where(df["cx_solicitadas"] > 0) * 100).round(1)
            ui.tabela(df)
            ui.download_csv(df, f"pedidos_marcados_{data}")

    with aba_i:
        importador(["pedidos_marcados"], operacao_id, key="imp_pm")
