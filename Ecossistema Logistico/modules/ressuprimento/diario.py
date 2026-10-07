"""Ressuprimento › Carregamento dia a dia (HL por indicador)."""
import streamlit as st

from core import graficos, tempo, ui
from repositories import ressuprimento_repo
from services import ressuprimento_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    meses = ressuprimento_repo.meses_disponiveis(operacao_id) or [tempo.mes_atual()]
    mes = ui.seletor_mes("Mês", meses, key="dia_mes", container=st.columns([1, 3])[0])
    piv = svc.dia_a_dia(operacao_id, mes)
    if piv.empty:
        st.info("Nenhum carregamento neste mês.")
        return
    indicadores = [c for c in piv.columns if c not in ("Dia", "Total do dia")]
    principais = [c for c in ("Cerveja", "Nab") if c in indicadores] or indicadores[:2]
    graficos.mostrar(graficos.barras(piv["Dia"], {c: piv[c].round(0) for c in principais}, empilhado=True,
                                     titulo="HL carregado por dia", sufixo=" HL"), key="g_dia")
    st.caption("HL do dia = soma da coluna C do relatório na data (coluna F), por indicador (coluna E) e filial (coluna A).")
    vis = piv.copy()
    for c in indicadores + ["Total do dia"]:
        vis[c] = vis[c].map(ui.numero)
    ui.tabela(vis)
    ui.downloads(piv, f"carregamento_dia_a_dia_{mes}", key="dl_dia")
