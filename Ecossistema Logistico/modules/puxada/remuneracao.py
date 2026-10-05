"""Puxada › Remuneração dos motoristas: fixo (nominal) + variável (viagens × valor por fábrica) no mês."""
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from repositories import logistica_repo
from services import motoristas_service as svc

R = {"format": "R$ %.2f"}


def _vis_viagens(v: pd.DataFrame) -> pd.DataFrame:
    if v.empty:
        return v
    out = v[["data_puxada", "motorista", "fabrica", "numero_pedido", "placa", "notas_fiscais", "valor"]].copy()
    out["origem"] = v["viagem_id"].map(lambda x: "📱 App" if x == x and x else "Manual")
    return out


COLS_VIAGEM = {"data_puxada": "Data", "motorista": "Motorista", "fabrica": "Fábrica", "numero_pedido": "Pedido",
               "placa": "Placa", "notas_fiscais": "NFs", "valor": st.column_config.NumberColumn("Valor", **R),
               "origem": "Origem"}


def render(usuario: dict, operacao_id: int) -> None:
    meses = logistica_repo.meses_vinculos(operacao_id) or [ui.mes_atual()]
    if ui.mes_atual() not in meses:
        meses = [ui.mes_atual()] + meses
    c1, c2 = st.columns([1, 3])
    mes = ui.seletor_mes("Mês", meses, key="rem_mes", container=c1)
    c2.caption("Variável = viagens do mês (pedidos vinculados — manuais e do App Carreteiro) × valor da viagem "
               "de cada fábrica. O valor fica em **⚙️ Cadastros › 🛣️ Trechos frota própria** e o salário fixo em **👤 Motoristas**.")
    r = svc.remuneracao(operacao_id, mes)
    resumo, viagens = r["resumo"], r["viagens"]
    if r["sem_valor"]:
        st.warning("💵 Fábricas sem valor de viagem nesta filial (contam R$ 0,00): **" + ", ".join(r["sem_valor"])
                   + "**. Cadastre em ⚙️ Cadastros › 🛣️ Trechos frota própria.")
    if resumo.empty:
        st.info("Nenhum motorista cadastrado e nenhuma viagem no mês.")
        return

    fabs = r["fabricas"]
    vis = resumo.rename(columns={f"fab::{f}": f"🏭 {f}" for f in fabs})
    ordem = ["motorista", "salario_fixo", "viagens", *[f"🏭 {f}" for f in fabs], "km", "variavel", "total"]
    vis = vis[[c for c in ordem if c in vis.columns]]
    cfg = {"motorista": "Motorista", "salario_fixo": st.column_config.NumberColumn("Fixo (nominal)", **R),
           "viagens": st.column_config.NumberColumn("Viagens", format="%d"),
           "km": st.column_config.NumberColumn("Km rodados", format="%.0f"),
           "variavel": st.column_config.NumberColumn("Variável", **R),
           "total": st.column_config.NumberColumn("Total", **R),
           **{f"🏭 {f}": st.column_config.NumberColumn(f"🏭 {f}", format="%d") for f in fabs}}
    vv = _vis_viagens(viagens)
    fixo, variavel = float(resumo["salario_fixo"].sum()), float(resumo["variavel"].sum())
    n_viagens = int(resumo["viagens"].sum())
    km_total = float(resumo["km"].sum()) if "km" in resumo else 0.0
    com_viagem = resumo[resumo["viagens"] > 0]

    tema.kpis([
        {"titulo": "Motoristas com viagem", "valor": len(com_viagem), "icone": "👤", "status": "info",
         "detalhe": f"de {len(resumo)} no cadastro", "dados": com_viagem.rename(columns={
             f"fab::{f}": f"🏭 {f}" for f in fabs})[[c for c in ordem if c in vis.columns]], "colunas": cfg},
        {"titulo": "Viagens no mês", "valor": n_viagens, "icone": "🚛", "status": "info", "dados": vv,
         "colunas": COLS_VIAGEM},
        {"titulo": "Variável do mês", "valor": ui.moeda(variavel), "icone": "💵", "status": "info",
         "detalhe": f"média {ui.moeda(variavel / n_viagens)} por viagem" if n_viagens else "",
         "dados": vis.sort_values("variavel", ascending=False), "colunas": cfg},
        {"titulo": "Fixo (nominal)", "valor": ui.moeda(fixo), "icone": "🧾", "status": "info",
         "dados": vis.sort_values("salario_fixo", ascending=False), "colunas": cfg},
        {"titulo": "Total (fixo + variável)", "valor": ui.moeda(fixo + variavel), "icone": "💰", "status": "info",
         "dados": vis, "colunas": cfg},
        {"titulo": "Produtividade", "valor": f"{ui.numero(n_viagens / len(com_viagem), 1)} viagens"
         if len(com_viagem) else "—", "icone": "📈", "status": "info",
         "detalhe": (f"por motorista · {ui.numero(km_total)} km rodados" if km_total else "por motorista no mês"),
         "dados": vis.sort_values("viagens", ascending=False), "colunas": cfg},
    ], key="kp_rem")

    tema.secao(f"Remuneração por motorista — {ui.nome_mes(mes)}",
               "Viagens por fábrica, variável e total. Clique num card ou numa barra para ver as viagens.")
    ui.tabela(vis, column_config=cfg)
    ui.downloads(vis, f"remuneracao_{mes}", key="dl_rem")

    g1, g2 = st.columns([1.4, 1])
    with g1:
        top = resumo[resumo["total"] > 0].head(15)
        if not top.empty:
            graficos.mostrar(graficos.barras(top["motorista"], {"Fixo": top["salario_fixo"], "Variável": top["variavel"]},
                                             titulo="Fixo + variável por motorista (R$)", empilhado=True),
                             key="g_rem_mot", colunas=COLS_VIAGEM, titulo="Viagens de",
                             detalhe=lambda rot: vv[vv["motorista"].str.strip().str.lower()
                                                    == rot.replace(" (não cadastrado)", "").strip().lower()]
                             if not vv.empty else vv)
    with g2:
        if not viagens.empty:
            por_fab = viagens.groupby("fabrica").agg(viagens=("id", "count"), valor_viagem=("valor", "max"),
                                                     variavel=("valor", "sum")).reset_index() \
                .sort_values("viagens", ascending=False)
            graficos.mostrar(graficos.barras_h(por_fab["fabrica"], por_fab["viagens"], titulo="Viagens por fábrica"),
                             key="g_rem_fab", detalhe=(vv, "fabrica"), colunas=COLS_VIAGEM, titulo="Fábrica")
            ui.tabela(por_fab, column_config={
                "fabrica": "Fábrica", "viagens": "Viagens",
                "valor_viagem": st.column_config.NumberColumn("Valor da viagem", **R),
                "variavel": st.column_config.NumberColumn("Variável", **R)})
    with st.expander("📋 Todas as viagens do mês com valor"):
        ui.tabela(vv, column_config=COLS_VIAGEM)
        if not vv.empty:
            ui.downloads(vv, f"viagens_remuneracao_{mes}", key="dl_rem_v")
