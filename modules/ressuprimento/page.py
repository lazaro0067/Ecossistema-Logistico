"""Módulo Ressuprimento — bases Ambev, estoque, sugestão de compra e cestas & metas."""
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from modules.componentes.autosave import editor_autosave
from modules.componentes.bases import card_base
from repositories import estoque_repo, ressuprimento_repo
from services import armazem_service, ressuprimento_service, sugestao_service
from services.erros import RegraNegocioError

_ICONE_SIT = {"Ruptura": "🔴", "Crítico": "🟠", "Abaixo da meta": "🟡", "OK": "🟢", "Excesso": "🔵", "Sem giro": "⚪"}


# =========================================================================
# 1. Cadastros & atualização de bases
# =========================================================================
def aba_bases(usuario: dict, operacao_id: int) -> None:
    tema.secao("Cadastros e Atualização das Bases Ambev",
               "Envie o arquivo: o sistema reconhece as colunas e grava sozinho. "
               "A cor mostra se a base está em dia.")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        card_base("produtos", operacao_id, usuario, "1. Relatório 01.11", "Cadastro · 1x / quando mudar")
    with c2:
        card_base("linear", operacao_id, usuario, "2. Relatório Linear", "A cada 3 meses")
    with c3:
        card_base("estoque", operacao_id, usuario, "3. Relatório 02.03.04", "Diário")
    with c4:
        card_base("pedidos_marcados", operacao_id, usuario, "4. Puxada Marcada", "D0, D1, D2 · diário")
    with st.expander("Outras bases: metas de DOI e ressuprimento por cesta"):
        o1, o2 = st.columns(2)
        with o1:
            card_base("metas_doi", operacao_id, usuario, "Metas de DOI por SKU", "Quando revisar")
        with o2:
            card_base("ressuprimento", operacao_id, usuario, "Ressuprimento diário por cesta", "Diário")


# =========================================================================
# 2. Gestão de estoque
# =========================================================================
def aba_estoque(usuario: dict, operacao_id: int) -> None:
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

    editor_autosave(tab, "ed_doi", ["doi_meta"], _salvar_doi, altura=420, column_config={
        "cod": st.column_config.NumberColumn("Código", format="%d"),
        "descricao": "Descrição", "tipo": "Tipo", "situacao": "Situação",
        "disponivel": st.column_config.NumberColumn("Disponível (cx)", format="%.0f"),
        "linear_cx_dia": st.column_config.NumberColumn("Linear (cx/dia)"),
        "doi": st.column_config.NumberColumn("DOI atual", format="%.1f d"),
        "doi_meta": st.column_config.NumberColumn("Meta DOI ✏️", format="%.1f d", min_value=0.5, max_value=120, step=0.5),
        "hl": st.column_config.NumberColumn("HL"), "paletes": st.column_config.NumberColumn("Paletes"),
    })
    ui.download_csv(vis, "posicao_estoque", key="dl_est")


# =========================================================================
# 3. Sugestão de compra & marcação por dia
# =========================================================================
def aba_sugestao(usuario: dict, operacao_id: int) -> None:
    c1, c2 = st.columns([1, 3])
    arred = c1.toggle("Arredondar para palete fechado", value=True, key="sug_arred")
    sug = sugestao_service.sugestao(operacao_id, arred)
    if sug.empty:
        st.info("Sem posição de estoque para calcular a sugestão. Atualize as bases.")
        return
    comprar = sug[sug["sugestao_cx"] > 0]
    marc = sugestao_service.marcado_por_dia(operacao_id)
    tema.kpis([
        {"titulo": "SKUs a comprar", "valor": len(comprar), "icone": "🛒",
         "status": "atencao" if len(comprar) else "bom", "selo": "precisam de pedido" if len(comprar) else "tudo coberto"},
        {"titulo": "Sugestão", "valor": f"{ui.numero(comprar['sugestao_cx'].sum())} cx",
         "detalhe": f"{ui.numero(comprar['sugestao_paletes'].sum(), 1)} paletes", "icone": "📦", "status": "info"},
        {"titulo": "Volume sugerido", "valor": f"{ui.numero(comprar['sugestao_hl'].sum(), 1)} HL", "icone": "🍺",
         "status": "info"},
        {"titulo": "Já marcado (próximos dias)", "valor": f"{ui.numero(marc['hl_marcado'].sum() if not marc.empty else 0, 1)} HL",
         "detalhe": f"{ui.numero(marc['cx_marcadas'].sum() if not marc.empty else 0)} cx", "icone": "🗓️", "status": "info"},
        {"titulo": "SKUs abaixo de 50% da meta", "valor": int((sug["cobertura_pct"] < 50).sum()), "icone": "🔴",
         "status": tema.status_contagem(int((sug["cobertura_pct"] < 50).sum()), 1, 5)},
    ])

    g1, g2 = st.columns([1, 1])
    with g1:
        if not marc.empty:
            dia = marc.groupby("dia", sort=False)["hl_marcado"].sum()
            graficos.mostrar(graficos.barras(dia.index, {"HL marcado": dia.values.round(1)},
                                             titulo="Marcação por dia (HL)", sufixo=" HL"), key="g_sug_dia")
        else:
            st.info("Nenhuma puxada marcada para hoje em diante. Envie a **Puxada Marcada** na aba de bases.")
    with g2:
        if not comprar.empty:
            por_tipo = comprar.groupby(comprar["tipo"].fillna("Sem tipo"))["sugestao_hl"].sum().sort_values(ascending=False)
            graficos.mostrar(graficos.barras_h(por_tipo.index, por_tipo.values, casas=1, sufixo=" HL",
                                               titulo="Sugestão por tipo (HL)"), key="g_sug_tipo")

    tema.secao("Sugestão de compra por SKU", "Ordenada pela menor cobertura (estoque + marcado ÷ meta).")
    st_cor = {"critico": "🔴", "serio": "🟠", "atencao": "🟡", "bom": "🟢", "neutro": "⚪"}
    tab = comprar.assign(
        prioridade=comprar["cobertura_pct"].map(lambda p: st_cor[sugestao_service.status_cobertura(p)]),
    )[["prioridade", "cod", "descricao", "disponivel", "marcado_cx", "linear_cx_dia", "doi", "doi_meta",
       "cobertura_pct", "sugestao_cx", "sugestao_paletes", "sugestao_hl", "doi_projetado"]]
    ui.tabela(tab, vazio="Nenhum SKU precisa de compra. 🎉", column_config={
        "prioridade": st.column_config.TextColumn("", width="small"),
        "cod": st.column_config.NumberColumn("Código", format="%d"), "descricao": "Descrição",
        "disponivel": st.column_config.NumberColumn("Disponível", format="%.0f"),
        "marcado_cx": st.column_config.NumberColumn("Marcado", format="%.0f"),
        "linear_cx_dia": st.column_config.NumberColumn("Linear/dia", format="%.1f"),
        "doi": st.column_config.NumberColumn("DOI", format="%.1f d"),
        "doi_meta": st.column_config.NumberColumn("Meta", format="%.1f d"),
        "cobertura_pct": st.column_config.ProgressColumn("Cobertura", format="%.0f%%", min_value=0, max_value=100),
        "sugestao_cx": st.column_config.NumberColumn("Sugestão (cx)", format="%.0f"),
        "sugestao_paletes": st.column_config.NumberColumn("Paletes", format="%.1f"),
        "sugestao_hl": st.column_config.NumberColumn("HL", format="%.1f"),
        "doi_projetado": st.column_config.NumberColumn("DOI após compra", format="%.1f d"),
    })
    ui.download_csv(tab, "sugestao_compra", key="dl_sug")

    if not marc.empty:
        tema.secao("Marcação por dia (caixas por SKU)")
        piv = marc.pivot_table(index="cod", columns="dia", values="cx_marcadas", aggfunc="sum", fill_value=0)
        piv.insert(0, "descricao", piv.index.map(sug.set_index("cod")["descricao"].to_dict()))
        piv["total"] = piv.drop(columns="descricao").sum(axis=1)
        ui.tabela(piv.reset_index())


# =========================================================================
# 4. Gestão ressuprimento (cestas & metas)
# =========================================================================
def aba_cestas(usuario: dict, operacao_id: int) -> None:
    meses = ressuprimento_repo.meses_disponiveis(operacao_id)
    if ui.mes_atual() not in meses:
        meses = [ui.mes_atual()] + meses
    c1, c2 = st.columns([1, 3])
    mes = ui.seletor_mes("Mês", meses, key="ces_mes", container=c1)
    df = ressuprimento_service.aderencia_mensal(operacao_id, mes)

    real, meta, proj = df["real_hl"].sum(), df["meta_hl"].sum(), df["projecao_hl"].sum()
    ating_proj = proj / meta * 100 if meta else None
    tema.kpis([
        {"titulo": "Realizado no mês", "valor": f"{ui.compacto(real)} HL", "icone": "🍺", "status": "info",
         "detalhe": f"até dia {ressuprimento_service.dia_referencia(operacao_id, mes) or '—'}"},
        {"titulo": "Meta do mês", "valor": f"{ui.compacto(meta)} HL" if meta else "Sem meta", "icone": "🎯",
         "status": "info" if meta else "neutro"},
        {"titulo": "Projeção de fechamento", "valor": f"{ui.compacto(proj)} HL", "icone": "🔮",
         "detalhe": ui.pct(ating_proj) + " da meta" if ating_proj is not None else "defina as metas abaixo",
         "status": tema.status_atingimento(ating_proj)},
        {"titulo": "Cestas no alvo", "icone": "✅",
         "valor": f"{int((df['atingimento_proj'] >= 100).sum())} de {int((df['meta_hl'] > 0).sum())}",
         "status": "info"},
    ])

    if not df.empty and (df["meta_hl"] > 0).any():
        com_meta = df[df["meta_hl"] > 0].sort_values("atingimento_proj")
        g1, g2 = st.columns([1, 1])
        with g1:
            cores = [tema.STATUS[tema.status_atingimento(p)][0] for p in com_meta["atingimento_proj"]]
            graficos.mostrar(graficos.barras_h(com_meta["cesta"], com_meta["atingimento_proj"].fillna(0), cores=cores,
                                               casas=0, sufixo="%", titulo="Projeção de atingimento por cesta (%)"),
                             key="g_ces_ating")
        with g2:
            cesta = st.selectbox("Evolução da cesta", com_meta["cesta"].tolist(), key="ces_cesta")
            evo = ressuprimento_service.evolucao_diaria(operacao_id, mes, cesta)
            if not evo.empty:
                graficos.mostrar(graficos.linhas(evo["data"], {"Real acumulado": evo["real_acum"],
                                                               "Meta proporcional": evo["meta_acum"]},
                                                 titulo=f"{cesta} — acumulado no mês", sufixo=" HL",
                                                 tracejadas=("Meta proporcional",)), key="g_ces_evo")
    elif not df.empty:
        st.info("Defina as metas por cesta na tabela abaixo para ver o atingimento e a projeção.")

    if not df.empty:
        tab = df.assign(status=df["atingimento_proj"].map(
            lambda p: {"bom": "🟢", "atencao": "🟡", "serio": "🟠", "critico": "🔴"}.get(tema.status_atingimento(p), "⚪")
            if pd.notna(p) else "⚪"))
        ui.tabela(tab[["status", "cesta", "real_hl", "sellin_hl", "aderencia_sellin", "meta_hl", "atingimento",
                       "projecao_hl", "atingimento_proj"]], column_config={
            "status": st.column_config.TextColumn("", width="small"), "cesta": "Cesta",
            "real_hl": st.column_config.NumberColumn("Real (HL)", format="%.0f"),
            "sellin_hl": st.column_config.NumberColumn("Sell-in (HL)", format="%.0f"),
            "aderencia_sellin": st.column_config.NumberColumn("Real/Sell-in", format="%.1f%%"),
            "meta_hl": st.column_config.NumberColumn("Meta (HL)", format="%.0f"),
            "atingimento": st.column_config.NumberColumn("Ating. atual", format="%.1f%%"),
            "projecao_hl": st.column_config.NumberColumn("Projeção (HL)", format="%.0f"),
            "atingimento_proj": st.column_config.ProgressColumn("Ating. projetado", format="%.0f%%",
                                                                min_value=0, max_value=120),
        })

    tema.secao(f"🎯 Metas de {ui.nome_mes(mes)}",
               "Digite a meta na tabela — grava automaticamente. Para nova cesta, use a última linha (+).")
    metas = ressuprimento_service.cestas_para_metas(operacao_id, mes)

    def _alterar(linha, alt):
        if "cesta" in alt and alt["cesta"] != linha["cesta"]:
            ressuprimento_service.excluir_meta(operacao_id, mes, linha["cesta"])
        ressuprimento_service.salvar_meta(operacao_id, mes, alt.get("cesta", linha["cesta"]),
                                          alt.get("meta_volume_hl", linha["meta_volume_hl"]))

    def _incluir(nova):
        if not (nova.get("cesta") or "").strip():
            raise RegraNegocioError("Informe o nome da cesta.")
        ressuprimento_service.salvar_meta(operacao_id, mes, nova["cesta"], nova.get("meta_volume_hl") or 0)

    def _excluir(linha):
        ressuprimento_service.excluir_meta(operacao_id, mes, linha["cesta"])

    editor_autosave(metas, f"ed_metas_{operacao_id}_{mes}", ["cesta", "meta_volume_hl"], _alterar, _incluir, _excluir,
                    column_config={"cesta": st.column_config.TextColumn("Cesta", required=True),
                                   "meta_volume_hl": st.column_config.NumberColumn("Meta do mês (HL) ✏️", min_value=0,
                                                                                   format="%.0f", step=100)})
    anterior = ressuprimento_service.mes_anterior(mes)
    if st.button(f"📋 Copiar metas de {ui.nome_mes(anterior)}", key="ces_copiar"):
        n = ressuprimento_service.copiar_metas(operacao_id, anterior, mes)
        ui.avisar(f"{n} metas copiadas de {ui.nome_mes(anterior)}." if n else "O mês anterior não tem metas.",
                  "success" if n else "warning")
        st.rerun()


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("ressuprimento")
    ui.abas_modulo(usuario, "ressuprimento", {
        "bases": aba_bases, "estoque": aba_estoque, "sugestao": aba_sugestao, "cestas": aba_cestas,
    }, usuario, operacao_id)
