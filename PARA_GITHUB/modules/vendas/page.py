"""Módulo Vendas — curva ABC."""
import streamlit as st

from core import graficos, tema, ui
from modules.componentes.importador import importador
from repositories import estoque_repo
from services import curva_abc_service

_COR_CLASSE = {"A": graficos.CATEGORICAS[0], "B": graficos.CATEGORICAS[1], "C": graficos.CATEGORICAS[2]}


def aba_abc(usuario: dict, operacao_id: int) -> None:
    meses = estoque_repo.meses_curva_abc(operacao_id)
    if not meses:
        st.info("Nenhuma curva ABC calculada. Envie as vendas do mês na aba **Importar Vendas**.")
        return
    c1, c2 = st.columns([1, 3])
    mes = ui.seletor_mes("Mês de referência", meses, key="abc_mes", container=c1)
    df = estoque_repo.curva_abc_df(operacao_id, mes)
    resumo = curva_abc_service.resumo_classes(df).set_index("classe")
    cards = []
    for cl, desc in (("A", "até 80% do volume"), ("B", "80% a 95%"), ("C", "cauda (últimos 5%)")):
        if cl in resumo.index:
            r = resumo.loc[cl]
            cards.append({"titulo": f"Classe {cl} · {desc}", "valor": f"{int(r['skus'])} SKUs", "icone": "🔤",
                          "detalhe": f"{ui.pct(r['pct_volume'])} do volume · {ui.pct(r['pct_skus'])} dos SKUs",
                          "status": "info"})
    tema.kpis(cards)

    g1, g2 = st.columns([1.3, 1])
    with g1:
        top = df.sort_values("total_qtde", ascending=False).head(15)
        graficos.mostrar(graficos.barras_h([f"{c} · {str(d).strip()[:24]}" for c, d in zip(top["cod"], top["descricao"])],
                                           top["total_qtde"], cores=[_COR_CLASSE.get(c) for c in top["classe"]],
                                           titulo="Top 15 SKUs por volume (cor = classe A/B/C)"), key="g_abc_top")
    with g2:
        curva = df.sort_values("pct_acumulado").reset_index(drop=True)
        curva["pct_skus"] = (curva.index + 1) / len(curva) * 100
        fig = graficos.linhas(curva["pct_skus"].round(1), {"% acumulado do volume": curva["pct_acumulado"]},
                              titulo="Curva ABC — % do volume x % dos SKUs", sufixo="%")
        fig.update_xaxes(ticksuffix="%")
        fig.update_yaxes(ticksuffix="%", range=[0, 102])
        graficos.mostrar(fig, key="g_abc_curva")

    classe = st.multiselect("Filtrar classes", ["A", "B", "C"], key="abc_cl", placeholder="Todas")
    vis = df[df["classe"].isin(classe)] if classe else df
    ui.tabela(vis[["cod", "descricao", "total_qtde", "pct_acumulado", "classe"]].round(2), column_config={
        "cod": st.column_config.NumberColumn("Código", format="%d"), "descricao": "Descrição",
        "total_qtde": st.column_config.NumberColumn("Volume", format="%.0f"),
        "pct_acumulado": st.column_config.NumberColumn("% acumulado", format="%.1f%%"), "classe": "Classe"})
    ui.download_csv(vis, f"curva_abc_{mes}", key="dl_abc")


def aba_importar(usuario: dict, operacao_id: int) -> None:
    importador(["curva_abc", "linear"], operacao_id, usuario, key="imp_vd")


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("vendas")
    ui.abas_modulo(usuario, "vendas", {"abc": aba_abc, "importar": aba_importar}, usuario, operacao_id)
