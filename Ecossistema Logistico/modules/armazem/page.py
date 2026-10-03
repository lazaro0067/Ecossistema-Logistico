"""Módulo Armazém — posição de estoque, DOI, ocupação e estrutura física."""
import pandas as pd
import streamlit as st

from core import session, ui
from modules.componentes.importador import importador
from repositories import armazem_repo, estoque_repo
from services import armazem_service as svc

_CORES = {"Ruptura": "🔴", "Crítico": "🟠", "Abaixo da meta": "🟡", "OK": "🟢", "Excesso": "🔵", "Sem giro": "⚪"}


def _aba_posicao(operacao_id: int) -> None:
    df = svc.posicao_com_indicadores(operacao_id)
    if df.empty:
        st.info("Sem posição de estoque. Importe a planilha na aba **Importar**.")
        return
    r = svc.resumo(operacao_id, df)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("SKUs", r["skus"])
    c2.metric("Estoque (HL)", ui.numero(r["hl"], 1))
    c3.metric("Paletes", ui.numero(r["paletes"]))
    c4.metric("DOI médio", f"{ui.numero(r['doi_medio'], 1)} dias")
    c5.metric("Rupturas / Críticos", f"{r['rupturas']} / {r['criticos']}")

    if r["cap_paletes"] or r["cap_hl"]:
        o1, o2 = st.columns(2)
        o1.write(f"**Ocupação paletes:** {ui.pct(r['ocup_paletes'])} de {ui.numero(r['cap_paletes'])}")
        o1.progress(min(r["ocup_paletes"] / 100, 1.0))
        o2.write(f"**Ocupação HL:** {ui.pct(r['ocup_hl'])} de {ui.numero(r['cap_hl'])}")
        o2.progress(min(r["ocup_hl"] / 100, 1.0))
    else:
        st.caption("Cadastre a capacidade dos armazéns para ver a ocupação.")

    filtro = st.multiselect("Situação", list(_CORES), default=[], key="arm_sit", placeholder="Todas")
    vis = df[df["situacao"].isin(filtro)] if filtro else df
    vis = vis.assign(situacao=vis["situacao"].map(lambda s: f"{_CORES.get(s, '')} {s}"))
    ui.tabela(vis[["cod", "descricao", "tipo", "disponivel", "linear_cx_dia", "doi", "doi_meta",
                   "situacao", "sugestao_cx", "hl", "paletes", "dt_atualizacao"]].round(2))
    ui.download_csv(vis, "posicao_estoque")
    st.bar_chart(df["situacao"].value_counts())


def _aba_metas_doi(operacao_id: int) -> None:
    st.caption("Meta de dias de estoque por SKU (padrão: 7 dias). Para muitos SKUs, use a importação.")
    with st.form("f_doi", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cod = c1.number_input("Código do produto", min_value=0, step=1)
        doi = c2.number_input("Meta DOI (dias)", min_value=0.0, value=7.0)
        if st.form_submit_button("Salvar"):
            estoque_repo.salvar_meta_doi(operacao_id, int(cod), doi)
            ui.avisar("Meta salva!")
            st.rerun()


def _aba_estrutura(operacao_id: int) -> None:
    st.subheader("Armazéns")
    with st.form("f_arm", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nome = c1.text_input("Nome do armazém", value="Armazém Principal")
        hl = c2.number_input("Capacidade (HL)", min_value=0.0, step=100.0)
        pal = c3.number_input("Capacidade (paletes)", min_value=0.0, step=10.0)
        if st.form_submit_button("Salvar armazém") and nome.strip():
            armazem_repo.salvar_armazem(operacao_id, nome.strip(), hl, pal)
            ui.avisar("Armazém salvo!")
            st.rerun()
    armazens = armazem_repo.listar_armazens(operacao_id)
    ui.tabela(pd.DataFrame(armazens).drop(columns=["operacao_id"], errors="ignore"))

    st.subheader("Áreas")
    if not armazens:
        st.info("Cadastre um armazém primeiro.")
        return
    with st.form("f_area", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        arm = ui.select_registro("Armazém", armazens, container=c1, permitir_vazio=False)
        nome = c2.text_input("Área (ex.: Picking, Pulmão)")
        pal = c3.number_input("Paletes", min_value=0.0)
        hl = c4.number_input("HL", min_value=0.0)
        if st.form_submit_button("Salvar área") and nome.strip():
            armazem_repo.salvar_area(arm, nome.strip(), pal, hl)
            ui.avisar("Área salva!")
            st.rerun()
    ui.tabela(armazem_repo.areas_df(operacao_id))


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("📦 Armazém", session.operacao_nome())
    abas = st.tabs(["📊 Posição & DOI", "🎯 Metas DOI", "🏗️ Estrutura física", "🔎 Produtos", "📥 Importar"])
    with abas[0]:
        _aba_posicao(operacao_id)
    with abas[1]:
        _aba_metas_doi(operacao_id)
    with abas[2]:
        _aba_estrutura(operacao_id)
    with abas[3]:
        st.caption(f"{ui.numero(estoque_repo.contar_produtos())} produtos cadastrados.")
        f = st.text_input("Buscar por código ou descrição", key="arm_busca")
        ui.tabela(estoque_repo.buscar_produtos_df(f))
    with abas[4]:
        importador(["estoque", "produtos", "linear", "metas_doi"], operacao_id, key="imp_arm")
