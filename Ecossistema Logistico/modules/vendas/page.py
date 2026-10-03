"""Módulo Vendas — curva ABC e linear de vendas."""
import streamlit as st

from core import session, ui
from modules.componentes.importador import importador
from repositories import estoque_repo
from services import curva_abc_service


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("📈 Vendas", session.operacao_nome())
    aba_abc, aba_i = st.tabs(["🔤 Curva ABC", "📥 Importar"])

    with aba_abc:
        meses = estoque_repo.meses_curva_abc(operacao_id)
        if not meses:
            st.info("Nenhuma curva ABC calculada. Importe as vendas do mês na aba **Importar**.")
        else:
            mes = st.selectbox("Mês de referência", meses, key="abc_mes")
            df = estoque_repo.curva_abc_df(operacao_id, mes)
            resumo = curva_abc_service.resumo_classes(df)
            cols = st.columns(len(resumo))
            for col, r in zip(cols, resumo.itertuples()):
                col.metric(f"Classe {r.classe}", f"{r.skus} SKUs", f"{ui.pct(r.pct_volume)} do volume",
                           delta_color="off")
            classe = st.multiselect("Filtrar classes", ["A", "B", "C"], default=[], key="abc_cl", placeholder="Todas")
            vis = df[df["classe"].isin(classe)] if classe else df
            ui.tabela(vis[["cod", "descricao", "total_qtde", "pct_acumulado", "classe"]].round(2))
            ui.download_csv(vis, f"curva_abc_{mes}")

    with aba_i:
        importador(["curva_abc", "linear"], operacao_id, key="imp_vd")
