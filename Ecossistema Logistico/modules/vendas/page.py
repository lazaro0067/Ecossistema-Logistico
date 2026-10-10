"""Módulo Vendas — estoque do dia para o comercial, metas, curva ABC."""
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from modules.componentes import estoque_dia
from modules.componentes.autosave import editor_autosave
from repositories import estoque_repo, financeiro_repo
from services import curva_abc_service
from services.erros import RegraNegocioError

_COR_CLASSE = {"A": graficos.CATEGORICAS[0], "B": graficos.CATEGORICAS[1], "C": graficos.CATEGORICAS[2]}
CATEGORIAS_PADRAO = ["Cerveja", "NAB", "Marketplace"]


def aba_comercial(usuario: dict, operacao_id: int) -> None:
    st.markdown(
        '<div class="eco-base" style="border-left:5px solid #2a78d6;margin-bottom:.8rem"><h4>📱 Portal Comercial</h4>'
        '<div class="freq">Link de consulta para o time de vendas (sem login, somente leitura).</div></div>',
        unsafe_allow_html=True)
    from repositories import operacoes_repo
    from services import links_service

    if not operacoes_repo.e_consolidada(operacao_id):
        link = links_service.obter(operacao_id)
        if int(link.get("ativo") or 0):
            st.link_button("🔗 Abrir Portal Comercial desta revenda", links_service.url(operacao_id))
        else:
            st.caption("🔒 O link do Portal Comercial desta revenda está desativado pelo Master.")
    estoque_dia.render(operacao_id, key="vend_est")


def aba_metas(usuario: dict, operacao_id: int) -> None:
    c1, _ = st.columns([1, 3])
    mes = c1.text_input("Mês (AAAA-MM)", value=ui.mes_atual(), key="mv_mes")
    df = financeiro_repo.metas_vendas_df(operacao_id, mes)
    base = pd.DataFrame({"categoria": CATEGORIAS_PADRAO}).merge(df, on="categoria", how="left")
    base = pd.concat([base, df[~df["categoria"].isin(CATEGORIAS_PADRAO)]], ignore_index=True).fillna(0.0)
    base["atingimento"] = (base["realizado_hl"] / base["meta_hl"].where(base["meta_hl"] > 0) * 100).round(1)
    meta, real = base["meta_hl"].sum(), base["realizado_hl"].sum()
    abaixo = base[(base["meta_hl"] > 0) & (base["realizado_hl"] < base["meta_hl"])]
    tema.kpis([
        {"titulo": "Meta de vendas", "valor": f"{ui.compacto(meta)} HL", "icone": "🎯", "status": "info",
         "dados": base.sort_values("meta_hl", ascending=False)},
        {"titulo": "Realizado", "valor": f"{ui.compacto(real)} HL", "icone": "📈", "status": "info",
         "dados": base.sort_values("realizado_hl", ascending=False)},
        {"titulo": "Atingimento", "valor": ui.pct(real / meta * 100) if meta else "—", "icone": "🏁",
         "status": tema.status_atingimento(real / meta * 100 if meta else None),
         "dados": abaixo.sort_values("atingimento"), "ver": "categorias abaixo da meta"},
    ], key="kp_mv")
    com = base[base["meta_hl"] > 0]
    if not com.empty:
        graficos.mostrar(graficos.real_x_meta(com, "categoria", "realizado_hl", "meta_hl", "Realizado x meta (HL)", "HL"),
                         key="g_mv", detalhe=(com, "categoria"), titulo="Categoria")
    if ui.somente_leitura(operacao_id):
        ui.tabela(base)
        return

    def alterar(l, alt):
        financeiro_repo.salvar_meta_venda(operacao_id, mes, l["categoria"], float(alt.get("meta_hl", l["meta_hl"]) or 0),
                                          float(alt.get("realizado_hl", l["realizado_hl"]) or 0))

    def incluir(n):
        if not (n.get("categoria") or "").strip():
            raise RegraNegocioError("Informe a categoria.")
        financeiro_repo.salvar_meta_venda(operacao_id, mes, n["categoria"].strip(), float(n.get("meta_hl") or 0),
                                          float(n.get("realizado_hl") or 0))

    editor_autosave(base, f"ed_mv_{operacao_id}_{mes}", ["meta_hl", "realizado_hl", "categoria"], alterar, incluir,
                    lambda l: financeiro_repo.excluir_meta_venda(operacao_id, mes, l["categoria"]), column_config={
                        "categoria": st.column_config.TextColumn("Categoria", required=True),
                        "meta_hl": st.column_config.NumberColumn("Meta (HL) ✏️", min_value=0, format="%.0f"),
                        "realizado_hl": st.column_config.NumberColumn("Realizado (HL) ✏️", min_value=0, format="%.0f"),
                        "atingimento": st.column_config.NumberColumn("Atingimento", format="%.1f%%")})


def aba_abc(usuario: dict, operacao_id: int) -> None:
    meses = estoque_repo.meses_curva_abc(operacao_id)
    if not meses:
        st.info("Nenhuma curva ABC calculada. Envie as vendas do mês na aba **Importar Vendas**.")
        return
    c1, _ = st.columns([1, 3])
    mes = ui.seletor_mes("Mês de referência", meses, key="abc_mes", container=c1)
    df = estoque_repo.curva_abc_df(operacao_id, mes)
    resumo = curva_abc_service.resumo_classes(df).set_index("classe")
    cards = []
    for cl, desc in (("A", "até 80% do volume"), ("B", "80% a 95%"), ("C", "cauda (últimos 5%)")):
        if cl in resumo.index:
            r = resumo.loc[cl]
            cards.append({"titulo": f"Classe {cl} · {desc}", "valor": f"{int(r['skus'])} SKUs", "icone": "🔤",
                          "detalhe": f"{ui.pct(r['pct_volume'])} do volume · {ui.pct(r['pct_skus'])} dos SKUs",
                          "status": "info", "ver": "SKUs",
                          "dados": df[df["classe"] == cl][["cod", "descricao", "total_qtde", "pct_acumulado", "classe"]]})
    tema.kpis(cards, key="kp_abc")
    g1, g2 = st.columns([1.3, 1])
    with g1:
        top = df.sort_values("total_qtde", ascending=False).head(15).copy()
        top["rotulo"] = [f"{c} · {str(d).strip()[:24]}" for c, d in zip(top["cod"], top["descricao"])]
        graficos.mostrar(graficos.barras_h(top["rotulo"], top["total_qtde"], cores=[_COR_CLASSE.get(c) for c in top["classe"]],
                                           titulo="Top 15 SKUs por volume (cor = classe A/B/C)"), key="g_abc_top",
                         detalhe=(top.drop(columns=["rotulo"]).assign(rotulo=top["rotulo"]), "rotulo"), titulo="SKU")
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
    ui.downloads(vis, f"curva_abc_{mes}", key="dl_abc")



def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("vendas")
    ui.abas_modulo(usuario, "vendas", {"comercial": aba_comercial, "metas": aba_metas, "abc": aba_abc}, usuario, operacao_id)
