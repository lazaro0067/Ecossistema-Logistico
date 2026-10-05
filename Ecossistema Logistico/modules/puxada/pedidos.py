"""Puxada › Pedidos marcados (aderência solicitado x marcado)."""
import streamlit as st

from core import graficos, tema, ui
from modules.componentes.importador import importador
from repositories import ressuprimento_repo


def render(usuario: dict, operacao_id: int) -> None:
    datas = ressuprimento_repo.datas_puxada(operacao_id)
    aba_v, aba_i = st.tabs(["Consulta", "Atualizar puxada marcada"])

    with aba_v:
        if not datas:
            st.info("Nenhum pedido marcado importado ainda.")
        else:
            data = st.selectbox("Data da puxada", datas, key="pm_data")
            df = ressuprimento_repo.pedidos_marcados_df(operacao_id, data)
            sol, mar = df["cx_solicitadas"].sum(), df["cx_marcadas"].sum()
            ader = mar / sol * 100 if sol else 0
            tema.kpis([
                {"titulo": "Pedidos", "valor": df["numero_pedido"].nunique(), "icone": "🧾", "status": "info"},
                {"titulo": "Caixas solicitadas", "valor": ui.numero(sol), "icone": "📝", "status": "info"},
                {"titulo": "Caixas marcadas", "valor": ui.numero(mar), "icone": "🚚", "status": "info",
                 "detalhe": f"{ui.numero(df['hl_marcado'].sum(), 1)} HL"},
                {"titulo": "Aderência da marcação", "valor": ui.pct(ader), "icone": "🎯",
                 "status": "bom" if 95 <= ader <= 105 else "atencao" if 85 <= ader <= 115 else "critico",
                 "selo": "marcado ≈ solicitado" if 95 <= ader <= 105 else "divergente"},
            ])
            df["aderencia_%"] = (df["cx_marcadas"] / df["cx_solicitadas"].where(df["cx_solicitadas"] > 0) * 100).round(1)
            st_cont = df["status_item"].fillna("—").value_counts()
            graficos.mostrar(graficos.barras_h(st_cont.index, st_cont.values, titulo="Itens por status"), key="g_pm")
            ui.tabela(df)
            ui.download_csv(df, f"pedidos_marcados_{data}", key="dl_pm")

    with aba_i:
        importador(["pedidos_marcados"], operacao_id, usuario, key="imp_pm")
