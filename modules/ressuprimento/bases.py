"""Ressuprimento › Cadastros e atualização das bases Ambev."""
import streamlit as st

from core import tema
from modules.componentes.bases import card_base


def render(usuario: dict, operacao_id: int) -> None:
    tema.secao("Cadastros e Atualização das Bases Ambev",
               "Envie o arquivo: o sistema reconhece as colunas (inclusive pela posição, como nos relatórios Ambev) "
               "e grava sozinho. A cor mostra se a base está em dia.")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        card_base("produtos", operacao_id, usuario, "1. Relatório 01.11", "Cadastro · 1x / quando mudar")
    with c2:
        card_base("linear", operacao_id, usuario, "2. Relatório Linear", "A cada 3 meses")
    with c3:
        card_base("estoque", operacao_id, usuario, "3. Relatório 02.03.04", "Diário")
    with c4:
        card_base("pedidos_marcados", operacao_id, usuario, "4. Puxada Marcada", "D0, D1, D2 · diário")
    st.write("")
    c5, c6, c7 = st.columns(3)
    with c5:
        card_base("ressuprimento", operacao_id, usuario, "5. Ressuprimento diário",
                  "Diário · um arquivo com todas as filiais (colunas A, C, E, F)")
    with c6:
        card_base("politica", operacao_id, usuario, "6. Política de estoque", "Semanal · estoque médio/mín/obj/máx")
    with c7:
        card_base("metas_doi", operacao_id, usuario, "7. Metas de DOI por SKU", "Quando revisar")
