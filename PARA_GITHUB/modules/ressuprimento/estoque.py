"""Ressuprimento › Gestão de estoque: visão comercial (D0/D1/D2) e gestão por meta de DOI."""
import streamlit as st

from core import graficos, tema, ui
from modules.componentes import estoque_dia
from modules.componentes.autosave import editor_autosave
from repositories import estoque_repo, operacoes_repo
from services import armazem_service
from services.erros import RegraNegocioError

_ICONE_SIT = {"Ruptura": "🔴", "Crítico": "🟠", "Abaixo da meta": "🟡", "OK": "🟢", "Excesso": "🔵", "Sem giro": "⚪"}


def render(usuario: dict, operacao_id: int) -> None:
    visao = st.radio("Visão", ["🛍️ Estoque do dia (D0, D1, D2)", "🎯 Gestão por meta de DOI"], horizontal=True,
                     key="ress_est_visao")
    if visao.startswith("🛍️"):
        estoque_dia.render(operacao_id, key="ress_est")
    else:
        _gestao_doi(usuario, operacao_id)


def _gestao_doi(usuario: dict, operacao_id: int) -> None:
    df = armazem_service.posicao_com_indicadores(operacao_id)
    if df.empty:
        st.info("Sem posição de estoque. Atualize o **Relatório 02.03.04** na aba de bases.")
        return
    r = armazem_service.resumo(operacao_id, df)
    meta_media = float(df.loc[df["linear_cx_dia"] > 0, "doi_meta"].mean() or 7)
    tema.kpis([
        {"titulo": "SKUs em estoque", "valor": r["skus"], "icone": "📦", "status": "info"},
        {"titulo": "Estoque", "valor": f"{ui.compacto(r['hl'])} HL", "detalhe": f"{ui.numero(r['paletes'])} paletes",
         "icone": "🍺", "status": "info"},
        {"titulo": "DOI médio", "valor": f"{ui.numero(r['doi_medio'], 1)} dias", "detalhe": f"meta média {ui.numero(meta_media, 1)} dias",
         "icone": "⏱️", "status": "bom" if r["doi_medio"] >= meta_media else "atencao" if r["doi_medio"] >= meta_media * .7 else "critico"},
        {"titulo": "Rupturas", "valor": r["rupturas"], "detalhe": "SKUs com giro e sem estoque", "icone": "⛔",
         "status": tema.status_contagem(r["rupturas"], 1, 3), "selo": "Sem ruptura" if not r["rupturas"] else "Agir hoje"},
        {"titulo": "Críticos (< 50% da meta)", "valor": r["criticos"], "icone": "⚠️",
         "status": tema.status_contagem(r["criticos"], 1, 10)},
        {"titulo": "Em excesso (> 2× meta)", "valor": int((df["situacao"] == "Excesso").sum()), "icone": "📈",
         "status": "atencao" if (df["situacao"] == "Excesso").any() else "bom", "selo": "capital parado"},
    ])

    f1, f2, f3 = st.columns([1, 2, 2])
    tipos = sorted(t for t in df["tipo"].dropna().unique())
    tipo = f1.selectbox("Tipo", ["Todos"] + tipos, key="est_tipo")
    sits = f2.multiselect("Situação", list(_ICONE_SIT), key="est_sit", placeholder="Todas")
    busca = f3.text_input("Buscar SKU (código ou descrição)", key="est_busca")
    vis = df
    if tipo != "Todos":
        vis = vis[vis["tipo"] == tipo]
    if sits:
        vis = vis[vis["situacao"].isin(sits)]
    if busca:
        vis = vis[vis["descricao"].fillna("").str.contains(busca, case=False) | vis["cod"].astype(str).str.contains(busca)]

    g1, g2 = st.columns([1, 1.4])
    with g1:
        cont = vis["situacao"].value_counts().reindex(list(_ICONE_SIT)).dropna()
        graficos.mostrar(graficos.barras_h(
            [f"{_ICONE_SIT[s]} {s}" for s in cont.index], cont.values,
            cores=[graficos.COR_SITUACAO[s] for s in cont.index], titulo="SKUs por situação"), key="g_est_sit")
    with g2:
        risco = vis[vis["linear_cx_dia"] > 0].assign(cob=lambda d: d["doi"] / d["doi_meta"] * 100) \
            .sort_values("cob").head(12)
        if not risco.empty:
            rot = [f"{c} · {str(d)[:22]}" for c, d in zip(risco["cod"], risco["descricao"])]
            graficos.mostrar(graficos.barras_h(
                rot, risco["doi"].round(1), casas=1, sufixo=" d",
                cores=[graficos.COR_SITUACAO.get(s, "#2a78d6") for s in risco["situacao"]],
                titulo="Menor cobertura — DOI atual (dias)"), key="g_est_risco")

    tema.secao("Posição por SKU", "Edite a coluna “Meta DOI” direto na tabela — salva na hora.")
    tab = vis[["cod", "descricao", "tipo", "situacao", "disponivel", "linear_cx_dia", "doi", "doi_meta",
               "hl", "paletes"]].copy()
    tab["situacao"] = tab["situacao"].map(lambda s: f"{_ICONE_SIT.get(s, '')} {s}")
    tab = tab.round({"doi": 1, "hl": 1, "paletes": 1, "linear_cx_dia": 1})

    def _salvar_doi(linha, alt):
        if "doi_meta" in alt:
            v = float(alt["doi_meta"] or 0)
            if v <= 0 or v > 120:
                raise RegraNegocioError("Meta de DOI deve ficar entre 0,5 e 120 dias.")
            estoque_repo.salvar_meta_doi(operacao_id, int(linha["cod"]), v)

    if operacoes_repo.e_consolidada(operacao_id):
        ui.tabela(tab)
        return
    editor_autosave(tab, f"ed_doi_{operacao_id}", ["doi_meta"], _salvar_doi, altura=420, column_config={
        "cod": st.column_config.NumberColumn("Código", format="%d"),
        "descricao": "Descrição", "tipo": "Tipo", "situacao": "Situação",
        "disponivel": st.column_config.NumberColumn("Disponível (cx)", format="%.0f"),
        "linear_cx_dia": st.column_config.NumberColumn("Linear (cx/dia)"),
        "doi": st.column_config.NumberColumn("DOI atual", format="%.1f d"),
        "doi_meta": st.column_config.NumberColumn("Meta DOI ✏️", format="%.1f d", min_value=0.5, max_value=120, step=0.5),
        "hl": st.column_config.NumberColumn("HL"), "paletes": st.column_config.NumberColumn("Paletes"),
    })
    ui.download_csv(vis, "posicao_estoque", key="dl_est")


