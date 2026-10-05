"""Puxada › Viagens do mês — gestão separada:
  🚛 Frota própria  — pedidos vinculados (manuais e do App Carreteiro), com a remuneração variável;
  🚚 Spot (frete)   — fretes contratados aprovados/finalizados;
  ⚖️ Comparativo    — quantas viagens e quanto custou cada modelo, por fábrica/origem.
"""
import unicodedata

import pandas as pd
import streamlit as st

from config.settings import StatusFrete
from core import graficos, tema, ui
from repositories import fretes_repo, logistica_repo

PARTES = ["🚛 Frota própria", "🚚 Spot (frete)", "⚖️ Comparativo"]
R = {"format": "R$ %.2f"}


def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()


def render(usuario: dict, operacao_id: int) -> None:
    from services import motoristas_service

    meses = sorted(set(logistica_repo.meses_vinculos(operacao_id)) | {ui.mes_atual()}, reverse=True)
    mes = ui.seletor_mes("Mês", meses, key="via_mes", container=st.columns([1, 3])[0])
    propria = motoristas_service.remuneracao(operacao_id, mes)["viagens"]
    spot = fretes_repo.listar_df(operacao_id, StatusFrete.COMPROMETIDOS, mes)
    cols_spot = ["id", "data_frete", "status", "origem", "destino", "transportadora", "valor_negociado", "numero_cte"]
    spot_vis = spot[cols_spot] if not spot.empty else pd.DataFrame(columns=cols_spot)
    n_p, n_s = len(propria), len(spot)
    custo_p = float(propria["valor"].sum()) if n_p else 0.0
    custo_s = float(spot["valor_negociado"].sum()) if n_s else 0.0
    fmt_spot = {"valor_negociado": st.column_config.NumberColumn("Valor", **R)}
    tema.kpis([
        {"titulo": "Viagens no mês", "valor": n_p + n_s, "icone": "🧭", "status": "info",
         "detalhe": "frota própria + spot"},
        {"titulo": "🚛 Frota própria", "valor": n_p, "icone": "", "status": "info",
         "detalhe": f"variável motoristas {ui.moeda(custo_p)}",
         "dados": propria.drop(columns=["id", "viagem_id"], errors="ignore") if n_p else None},
        {"titulo": "🚚 Spot (frete)", "valor": n_s, "icone": "", "status": "atencao" if n_s else "info",
         "detalhe": f"custo {ui.moeda(custo_s)}", "dados": spot_vis if n_s else None, "colunas": fmt_spot},
        {"titulo": "% das viagens no spot", "valor": ui.pct(n_s / (n_p + n_s) * 100 if n_p + n_s else 0, 0),
         "icone": "📊", "status": "atencao" if n_p + n_s and n_s / (n_p + n_s) > .3 else "bom"},
        {"titulo": "Custo médio por viagem", "valor": ui.moeda(custo_s / n_s) if n_s else "—", "icone": "💸",
         "status": "info", "detalhe": f"própria (variável): {ui.moeda(custo_p / n_p) if n_p else '—'}"},
    ], key="kp_via_tot")

    with st.container(key="nav_via_partes"):
        parte = ui._escolha("via_parte", PARTES, PARTES[0], pills=True)
    if parte == PARTES[1]:
        _spot(spot_vis, fmt_spot)
        return
    if parte == PARTES[2]:
        _comparativo(propria, spot)
        return
    df = logistica_repo.vinculos_df(operacao_id, mes)
    if df.empty:
        st.info("Nenhuma viagem da frota própria neste mês. Elas entram pelo 📱 App Carreteiro ou em "
                "**🔗 Vincular Pedido & NFs**.")
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
        {"titulo": "Viagens da frota própria", "valor": len(df), "icone": "🚚", "status": "info", "dados": vis,
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
    ], key="kp_via_prop")
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


def _spot(df: pd.DataFrame, fmt: dict) -> None:
    if df.empty:
        st.info("Nenhum frete spot aprovado ou finalizado neste mês (📝 Solicitar Frete).")
        return
    tema.secao("Fretes spot do mês", "Aprovados e finalizados — clique numa barra para ver os fretes.")
    base = df.assign(transportadora=df["transportadora"].fillna("—"),
                     trecho=df["origem"].fillna("—") + " ➔ " + df["destino"].fillna("—"))
    g1, g2 = st.columns(2)
    with g1:
        t = base.groupby("transportadora")["valor_negociado"].sum().sort_values(ascending=False)
        graficos.mostrar(graficos.barras_h(t.index, t.values, titulo="Custo por transportadora (R$)"),
                         key="g_spot_tr", detalhe=(base, "transportadora"), colunas=fmt, titulo="Transportadora")
    with g2:
        t = base.groupby("trecho").size().sort_values(ascending=False).head(10)
        graficos.mostrar(graficos.barras_h(t.index, t.values, titulo="Fretes por trecho"),
                         key="g_spot_trecho", detalhe=(base, "trecho"), colunas=fmt, titulo="Trecho")
    ui.tabela(df, column_config=fmt)
    ui.downloads(df, "fretes_spot", key="dl_spot")


def _comparativo(propria: pd.DataFrame, spot: pd.DataFrame) -> None:
    tema.secao("Frota própria x spot por fábrica / origem",
               "Própria = variável pago ao motorista (o custo fixo da frota não entra). Spot = valor do frete.")
    linhas = {}
    for r in propria.to_dict("records") if not propria.empty else []:
        k = _n(r.get("fabrica"))
        d = linhas.setdefault(k, {"origem": r.get("fabrica") or "—", "viagens_proprias": 0, "custo_proprio": 0.0,
                                  "viagens_spot": 0, "custo_spot": 0.0})
        d["viagens_proprias"] += 1
        d["custo_proprio"] += float(r.get("valor") or 0)
    for r in spot.to_dict("records") if not spot.empty else []:
        k = _n(r.get("origem"))
        d = linhas.setdefault(k, {"origem": r.get("origem") or "—", "viagens_proprias": 0, "custo_proprio": 0.0,
                                  "viagens_spot": 0, "custo_spot": 0.0})
        d["viagens_spot"] += 1
        d["custo_spot"] += float(r.get("valor_negociado") or 0)
    if not linhas:
        st.info("Sem viagens no mês.")
        return
    tab = pd.DataFrame(linhas.values())
    tab["% spot"] = (tab["viagens_spot"] / (tab["viagens_proprias"] + tab["viagens_spot"]) * 100).round(0)
    tab["custo médio próprio"] = tab["custo_proprio"] / tab["viagens_proprias"].where(tab["viagens_proprias"] > 0)
    tab["custo médio spot"] = tab["custo_spot"] / tab["viagens_spot"].where(tab["viagens_spot"] > 0)
    tab = tab.sort_values(["viagens_proprias", "viagens_spot"], ascending=False)
    graficos.mostrar(graficos.barras(tab["origem"], {"Frota própria": tab["viagens_proprias"],
                                                     "Spot": tab["viagens_spot"]},
                                     titulo="Viagens por fábrica / origem", empilhado=True), key="g_via_comp")
    ui.tabela(tab, column_config={
        "origem": "Fábrica / origem", "viagens_proprias": "Viagens próprias", "viagens_spot": "Viagens spot",
        "custo_proprio": st.column_config.NumberColumn("Variável própria", **R),
        "custo_spot": st.column_config.NumberColumn("Custo spot", **R),
        "custo médio próprio": st.column_config.NumberColumn("Médio próprio", **R),
        "custo médio spot": st.column_config.NumberColumn("Médio spot", **R),
        "% spot": st.column_config.NumberColumn("% spot", format="%.0f%%")})
    ui.downloads(tab, "comparativo_propria_spot", key="dl_comp")
