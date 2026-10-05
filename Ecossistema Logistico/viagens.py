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
    df["origem"] = df["viagem_id"].map(lambda v: "📱 App Carreteiro" if v == v and v else "Manual")
    vis = df.drop(columns=["id", "viagem_id"])
    for c in ("placa", "fabrica", "motorista", "transportadora"):
        vis[c] = vis[c].fillna("—")

    def resumo(campo):
        return vis.groupby(campo).agg(viagens=("numero_pedido", "count"), hl=("hl_carregado", "sum"),
                                      nfs=("qtd_nfs", "sum")).reset_index().sort_values("viagens", ascending=False)

    sem_nf = vis[vis["qtd_nfs"] == 0]
    tema.kpis([
        {"titulo": "Viagens no mês", "valor": len(df), "icone": "🚚", "status": "info", "dados": vis,
         "detalhe": f"{int((df['origem'] != 'Manual').sum())} pelo App Carreteiro"},
        {"titulo": "HL carregado", "valor": ui.numero(df["hl_carregado"].sum(), 1), "icone": "🍺", "status": "info",
         "dados": vis.sort_values("hl_carregado", ascending=False)},
        {"titulo": "Carretas ativas", "valor": df["placa"].nunique(), "icone": "🚛", "status": "info",
         "dados": resumo("placa")},
        {"titulo": "Motoristas", "valor": df["motorista"].nunique(), "icone": "👤", "status": "info",
         "dados": resumo("motorista")},
        {"titulo": "NFs vinculadas", "valor": int(df["qtd_nfs"].sum()), "icone": "📄", "status": "info",
         "dados": vis[vis["qtd_nfs"] > 0][["data_puxada", "numero_pedido", "placa", "motorista", "notas_fiscais", "qtd_nfs"]]},
        {"titulo": "Viagens sem NF", "valor": len(sem_nf), "icone": "⚠️", "dados": sem_nf,
         "status": "atencao" if len(sem_nf) else "bom", "selo": "completar" if len(sem_nf) else "completo"},
    ], key="kp_via")
    g1, g2 = st.columns(2)
    for col, campo, titulo, k in ((g1, "placa", "Viagens por carreta", "car"), (g2, "fabrica", "Viagens por fábrica", "fab")):
        cont = vis[campo].value_counts().head(10)
        with col:
            graficos.mostrar(graficos.barras_h(cont.index, cont.values, titulo=titulo), key=f"g_via_{k}",
                             detalhe=(vis, campo), titulo=titulo.replace("Viagens por ", "").capitalize())
    g3, g4 = st.columns(2)
    for col, campo, titulo, k in ((g3, "motorista", "Viagens por motorista", "mot"),
                                  (g4, "transportadora", "Viagens por transportadora", "tr")):
        cont = vis[campo].value_counts().head(10)
        with col:
            graficos.mostrar(graficos.barras_h(cont.index, cont.values, titulo=titulo), key=f"g_via_{k}",
                             detalhe=(vis, campo), titulo=titulo.replace("Viagens por ", "").capitalize())
    por_dia = df.groupby("data_puxada").size()
    graficos.mostrar(graficos.barras(por_dia.index, {"Viagens": por_dia.values}, titulo="Viagens por dia"),
                     key="g_via_dia", detalhe=(vis, "data_puxada"), titulo="Dia")
    st.caption("🔎 Clique num card ou numa barra para ver as viagens.")
    with st.expander("📋 Todas as viagens do mês"):
        ui.tabela(vis)
    ui.downloads(vis, f"viagens_{mes}", key="dl_via")
