"""Puxada › Gestão mensal de viagens (consolidado dos pedidos vinculados)."""
import streamlit as st

from core import graficos, tema, ui
from repositories import logistica_repo


def render(usuario: dict, operacao_id: int) -> None:
    meses = logistica_repo.meses_vinculos(operacao_id) or [ui.mes_atual()]
    if ui.mes_atual() not in meses:
        meses = [ui.mes_atual()] + meses
    mes = ui.seletor_mes("Mês", meses, key="via_mes", container=st.columns([1, 3])[0])
    df = logistica_repo.vinculos_df(operacao_id, mes)
    if df.empty:
        st.info("Nenhuma viagem registrada neste mês. Registre em **🔗 Vincular Pedido & NFs**.")
        return
    df["qtd_nfs"] = df["notas_fiscais"].fillna("").map(lambda t: len([x for x in t.split(",") if x.strip()]))
    tema.kpis([
        {"titulo": "Viagens no mês", "valor": len(df), "icone": "🚚", "status": "info"},
        {"titulo": "HL carregado", "valor": ui.numero(df["hl_carregado"].sum(), 1), "icone": "🍺", "status": "info"},
        {"titulo": "Carretas ativas", "valor": df["placa"].nunique(), "icone": "🚛", "status": "info"},
        {"titulo": "Motoristas", "valor": df["motorista"].nunique(), "icone": "👤", "status": "info"},
        {"titulo": "NFs vinculadas", "valor": int(df["qtd_nfs"].sum()), "icone": "📄", "status": "info"},
        {"titulo": "Viagens sem NF", "valor": int((df["qtd_nfs"] == 0).sum()), "icone": "⚠️",
         "status": "atencao" if (df["qtd_nfs"] == 0).any() else "bom", "selo": "completar" if (df["qtd_nfs"] == 0).any() else "completo"},
    ])
    g1, g2 = st.columns(2)
    for col, campo, titulo, k in ((g1, "placa", "Viagens por carreta", "car"), (g2, "fabrica", "Viagens por fábrica", "fab")):
        cont = df[campo].fillna("—").value_counts().head(10)
        with col:
            graficos.mostrar(graficos.barras_h(cont.index, cont.values, titulo=titulo), key=f"g_via_{k}")
    g3, g4 = st.columns(2)
    for col, campo, titulo, k in ((g3, "motorista", "Viagens por motorista", "mot"),
                                  (g4, "transportadora", "Viagens por transportadora", "tr")):
        cont = df[campo].fillna("—").value_counts().head(10)
        with col:
            graficos.mostrar(graficos.barras_h(cont.index, cont.values, titulo=titulo), key=f"g_via_{k}")
    por_dia = df.groupby("data_puxada").size()
    graficos.mostrar(graficos.barras(por_dia.index, {"Viagens": por_dia.values}, titulo="Viagens por dia"), key="g_via_dia")
    with st.expander("📋 Todas as viagens do mês"):
        ui.tabela(df.drop(columns=["id"]))
    ui.downloads(df, f"viagens_{mes}", key="dl_via")
