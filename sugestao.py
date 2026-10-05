"""Ressuprimento › Sugestão de compra e marcação por dia de puxada."""
import streamlit as st

from core import graficos, tema, tempo, ui
from services import sugestao_service

_PRIO = {"critico": "🔴", "serio": "🟠", "atencao": "🟡", "bom": "🟢", "neutro": "⚪"}


def render(usuario: dict, operacao_id: int) -> None:
    st.caption("Escolha o dia da puxada. O sistema projeta o estoque até esse dia (estoque atual + já marcado − "
               "venda diária) e calcula quanto marcar para chegar na meta de cobertura.")
    alvo_padrao = sugestao_service.data_alvo_padrao(operacao_id)
    c1, c2, c3, c4 = st.columns([1.2, 1.3, 1, 1])
    alvo = c1.date_input("Data da puxada alvo", value=alvo_padrao, format="DD/MM/YYYY", key="sug_alvo")
    regra = c2.radio("Meta de cobertura", ["Meta DOI de cada SKU", "Mesma meta para todos"], key="sug_regra")
    meta = c3.number_input("Meta (dias)", min_value=1.0, max_value=30.0, value=7.0, step=0.5, key="sug_meta",
                           disabled=regra.startswith("Meta DOI"))
    arred = c4.toggle("Fechar em palete", value=True, key="sug_arred")

    sug = sugestao_service.sugestao(operacao_id, alvo, None if regra.startswith("Meta DOI") else meta, arred)
    if sug.empty:
        st.info("Sem posição de estoque para calcular. Atualize as bases (02.03.04, Linear e 01.11).")
        return
    comprar = sug[sug["sugestao_cx"] > 0]
    dias = max(1, (alvo - tempo.hoje()).days)
    det_cols = ["cod", "descricao", "marca", "disponivel", "doi", "meta_usada", "cobertura_pct", "sugestao_paletes",
                "sugestao_cx", "sugestao_hl"]
    det_cols = [c for c in det_cols if c in sug.columns]
    baixos = sug[sug["cobertura_pct"] < 50][det_cols].sort_values("cobertura_pct")
    tema.kpis([
        {"titulo": f"Paletes para {alvo:%d/%m}", "valor": ui.numero(comprar["sugestao_paletes"].sum(), 1), "icone": "🧱",
         "status": "info", "detalhe": f"projeção de {dias} dia(s)",
         "dados": comprar[det_cols].sort_values("sugestao_paletes", ascending=False)},
        {"titulo": "Caixas sugeridas", "valor": ui.numero(comprar["sugestao_cx"].sum()), "icone": "📦", "status": "info",
         "dados": comprar[det_cols].sort_values("sugestao_cx", ascending=False)},
        {"titulo": "Volume sugerido", "valor": f"{ui.numero(comprar['sugestao_hl'].sum(), 1)} HL", "icone": "🍺",
         "status": "info", "dados": comprar[det_cols].sort_values("sugestao_hl", ascending=False)},
        {"titulo": "SKUs para marcar", "valor": len(comprar), "icone": "🛒", "dados": comprar[det_cols],
         "status": "atencao" if len(comprar) else "bom", "selo": "precisam de pedido" if len(comprar) else "tudo coberto"},
        {"titulo": "SKUs abaixo de 50% da meta", "valor": len(baixos), "icone": "🔴", "dados": baixos,
         "status": tema.status_contagem(len(baixos), 1, 5)},
    ], key="kp_sug")

    marc = sugestao_service.marcado_por_dia(operacao_id)
    g1, g2 = st.columns(2)
    with g1:
        if not marc.empty:
            dia = marc.groupby("dia", sort=False)["hl_marcado"].sum()
            graficos.mostrar(graficos.barras(dia.index, {"HL marcado": dia.values.round(1)},
                                             titulo="Já marcado por dia (HL)", sufixo=" HL"), key="g_sug_dia",
                             detalhe=(marc, "dia"), titulo="Dia")
        else:
            st.info("Nenhuma puxada marcada de hoje em diante. Envie a **Puxada Marcada** na aba de bases.")
    with g2:
        if not comprar.empty:
            por_marca = comprar.groupby("marca")["sugestao_hl"].sum().sort_values(ascending=False).head(10)
            graficos.mostrar(graficos.barras_h(por_marca.index, por_marca.values, casas=1, sufixo=" HL",
                                               titulo="Sugestão por marca (HL)"), key="g_sug_marca",
                             detalhe=(comprar[det_cols], "marca"), titulo="Marca")

    tema.secao(f"Sugestão de marcação para {alvo:%d/%m/%Y}", "Ordem: menor cobertura primeiro.")
    tab = comprar.assign(prioridade=comprar["cobertura_pct"].map(lambda p: _PRIO[sugestao_service.status_cobertura(p)]))
    cols = ["prioridade", "cod", "descricao", "marca", "disponivel", "marcado_cx", "ja_marcado_alvo", "linear_cx_dia",
            "doi", "meta_usada", "cobertura_pct", "sugestao_paletes", "sugestao_cx", "sugestao_hl", "doi_projetado"]
    ui.tabela(tab[cols], vazio="Nenhum SKU precisa ser marcado para este dia. 🎉", column_config={
        "prioridade": st.column_config.TextColumn("", width="small"),
        "cod": st.column_config.NumberColumn("Código", format="%d"), "descricao": "Produto", "marca": "Marca",
        "disponivel": st.column_config.NumberColumn("Estoque", format="%.0f"),
        "marcado_cx": st.column_config.NumberColumn("Marcado até a véspera", format="%.0f"),
        "ja_marcado_alvo": st.column_config.NumberColumn("Já marcado no dia", format="%.0f"),
        "linear_cx_dia": st.column_config.NumberColumn("Venda/dia", format="%.1f"),
        "doi": st.column_config.NumberColumn("DOI hoje", format="%.1f d"),
        "meta_usada": st.column_config.NumberColumn("Meta", format="%.1f d"),
        "cobertura_pct": st.column_config.ProgressColumn("Cobertura no dia", format="%.0f%%", min_value=0, max_value=100),
        "sugestao_paletes": st.column_config.NumberColumn("Paletes", format="%.1f"),
        "sugestao_cx": st.column_config.NumberColumn("Caixas", format="%.0f"),
        "sugestao_hl": st.column_config.NumberColumn("HL", format="%.1f"),
        "doi_projetado": st.column_config.NumberColumn("DOI após marcar", format="%.1f d"),
    })
    ui.downloads(tab[cols], f"sugestao_marcacao_{alvo:%Y%m%d}", key="dl_sug")

    if not marc.empty:
        with st.expander("🗓️ Marcação por dia — caixas por SKU"):
            piv = marc.pivot_table(index="cod", columns="dia", values="cx_marcadas", aggfunc="sum", fill_value=0)
            piv.insert(0, "descricao", piv.index.map(sug.set_index("cod")["descricao"].to_dict()))
            piv["total"] = piv.drop(columns="descricao").sum(axis=1)
            ui.tabela(piv.reset_index())
