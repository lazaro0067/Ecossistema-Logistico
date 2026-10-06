"""Ressuprimento › ⚠️ Projeção de falta — escolha o dia e veja o que vai faltar."""
import datetime as dt

import pandas as pd
import streamlit as st

from core import tema, tempo, ui
from services import sugestao_service


def _tabela(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Situação": df["situacao_dia"],
        "Código": df["cod"],
        "Produto": df["descricao"],
        "Disponível hoje (cx)": df["disponivel"].map(ui.numero),
        "Venda/dia (cx)": df["linear_cx_dia"].map(lambda v: ui.numero(v, 1)),
        "Entradas marcadas até o dia (cx)": (df["entrada_antes"] + df["entrada_dia"]).map(ui.numero),
        "Estoque no início do dia (cx)": df["estoque_inicio"].map(ui.numero),
        "Falta (cx)": df["falta_cx"].map(lambda v: ui.numero(v) if v else "—"),
        "Falta (paletes)": df["falta_paletes"].map(lambda v: ui.numero(v) if v else "—"),
        "Cobertura (dias)": df["cobertura_dias"].map(lambda v: ui.numero(v, 1) if v == v else "—"),
        "Ruptura prevista": df["ruptura_em"].map(lambda d: d.strftime("%d/%m") if isinstance(d, dt.date) else "—"),
    })


def render(usuario: dict, operacao_id: int) -> None:
    hoje = tempo.hoje()
    st.caption("Escolha o dia. O sistema projeta o estoque até lá — estoque de hoje + puxadas já marcadas − venda "
               "média por dia — e mostra quais produtos vão faltar.")
    c1, c2 = st.columns([1, 3])
    dia = c1.date_input("Dia da projeção", value=hoje + dt.timedelta(days=1), min_value=hoje,
                        max_value=hoje + dt.timedelta(days=30), format="DD/MM/YYYY", key="rup_dia")
    df = sugestao_service.projecao_falta(operacao_id, dia)
    if df.empty:
        st.info("Sem posição de estoque para projetar. Atualize as bases (estoque, linear de vendas e pedidos marcados).")
        return
    sem = df[df["situacao_dia"] == "⛔ Sem estoque no dia"]
    falta = df[df["situacao_dia"] == "🔴 Falta durante o dia"]
    limite = df[df["situacao_dia"] == "🟡 No limite (< 1 dia)"]
    tab = _tabela(df)
    criticos = tab[tab["Situação"].isin(["⛔ Sem estoque no dia", "🔴 Falta durante o dia"])]
    tema.kpis([
        {"titulo": f"Sem estoque em {dia:%d/%m}", "valor": len(sem), "icone": "⛔",
         "status": "critico" if len(sem) else "bom", "dados": _tabela(sem)},
        {"titulo": "Faltam durante o dia", "valor": len(falta), "icone": "🔴",
         "status": "serio" if len(falta) else "bom", "dados": _tabela(falta)},
        {"titulo": "No limite (< 1 dia)", "valor": len(limite), "icone": "🟡",
         "status": "atencao" if len(limite) else "bom", "dados": _tabela(limite)},
        {"titulo": "Paletes para cobrir a falta", "valor": ui.numero(df["falta_paletes"].sum()), "icone": "📦",
         "status": "info", "detalhe": f"{ui.numero(df['falta_hl'].sum(), 1)} HL", "dados": criticos},
    ], key=f"kp_rup_{dia}")
    dias = df.attrs.get("dias", 0)
    tema.secao(f"⚠️ Produtos que vão faltar em {dia:%d/%m}",
               f"Projeção de {dias} dia(s) a partir do estoque de hoje. Ordem: mais crítico primeiro.")
    so_risco = st.toggle("Mostrar só os que faltam ou estão no limite", value=True, key="rup_so")
    vis = tab[tab["Situação"] != "🟢 Coberto"] if so_risco else tab
    vis = vis[vis["Situação"] != "Sem giro"] if so_risco else vis
    if vis.empty:
        st.success(f"Nenhum produto deve faltar em {dia:%d/%m}. 🎉")
    else:
        ui.tabela(vis)
    ui.downloads(tab, f"projecao_falta_{dia}", key="dl_rup")
