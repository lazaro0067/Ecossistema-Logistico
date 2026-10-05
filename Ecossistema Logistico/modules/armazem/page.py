"""Módulo Armazém & Estoque — saúde DPO, Book DPO (fundamentos/manter/melhorar), pátio e capacidade."""
import pandas as pd
import streamlit as st

from config import dpo
from core import graficos, tema, tempo, ui
from modules.componentes import padrao_dpo
from modules.componentes.autosave import editor_autosave
from modules.puxada import descarga
from repositories import armazem_repo, dpo_repo, estoque_repo, operacoes_repo
from services import armazem_service, curva_abc_service
from services.erros import RegraNegocioError

MODULO = "Armazém"


# --- Saúde & ocupação ---------------------------------------------------------
def aba_saude(usuario: dict, operacao_id: int) -> None:
    df = armazem_service.posicao_com_indicadores(operacao_id)
    s = armazem_service.saude_dpo(df)
    r = armazem_service.resumo(operacao_id, df)
    cols = [c for c in ["cod", "descricao", "tipo", "situacao", "disponivel", "linear_cx_dia", "doi", "doi_meta", "hl",
                        "paletes"] if c in df.columns]
    doi = df["doi"].fillna(999) if not df.empty else pd.Series(dtype=float)
    fora = df[(doi < 3) | (doi > 15)][cols] if not df.empty else df
    tema.kpis([
        {"titulo": "Saúde do estoque DPO", "valor": ui.pct(s["pct"]), "icone": "🏥", "detalhe": "meta DPO ≥ 85%",
         "status": "bom" if s["pct"] >= 85 else "atencao" if s["pct"] >= 70 else "critico",
         "dados": fora, "ver": "SKUs fora da faixa"},
        {"titulo": "SKUs saudáveis (DOI 3–15)", "valor": s["saudaveis"], "icone": "🟢", "status": "bom",
         "dados": df[(doi >= 3) & (doi <= 15)][cols] if not df.empty else df},
        {"titulo": "Em risco / ruptura (DOI < 3)", "valor": s["risco"], "icone": "🔴",
         "status": tema.status_contagem(s["risco"], 1, 10),
         "dados": df[doi < 3][cols].sort_values("doi") if not df.empty else df},
        {"titulo": "Em excesso (DOI > 15)", "valor": s["excesso"], "icone": "🔵",
         "status": "atencao" if s["excesso"] else "bom",
         "dados": df[doi > 15][cols].sort_values("doi", ascending=False) if not df.empty else df},
        {"titulo": "Ocupação (paletes)", "valor": ui.pct(r["ocup_paletes"]) if r["cap_paletes"] else "—", "icone": "🧱",
         "detalhe": f"{ui.numero(r['paletes'])} de {ui.numero(r['cap_paletes'])}" if r["cap_paletes"] else "cadastre a capacidade",
         "status": tema.status_ocupacao(r["ocup_paletes"]) if r["cap_paletes"] else "neutro"},
        {"titulo": "Ocupação (HL)", "valor": ui.pct(r["ocup_hl"]) if r["cap_hl"] else "—", "icone": "🍺",
         "detalhe": f"{ui.compacto(r['hl'])} de {ui.compacto(r['cap_hl'])} HL" if r["cap_hl"] else "",
         "status": tema.status_ocupacao(r["ocup_hl"]) if r["cap_hl"] else "neutro"},
    ], key="kp_arm_saude")
    if df.empty:
        st.info("Sem posição de estoque. Atualize o Relatório 02.03.04 no Ressuprimento.")
        return
    g1, g2 = st.columns(2)
    with g1:
        faixas = pd.cut(df["doi"].fillna(999), [-1, 0.0001, 3, 7, 15, 30, 10_000],
                        labels=["Zerado", "< 3 dias", "3–7 dias", "7–15 dias", "15–30 dias", "> 30 dias ou sem giro"])
        cont = faixas.value_counts().reindex(faixas.cat.categories).fillna(0)
        com_faixa = df.assign(faixa=faixas.astype(str))
        cores = [tema.STATUS[c][0] for c in ("critico", "serio", "bom", "bom", "atencao", "info")]
        graficos.mostrar(graficos.barras_h(cont.index.astype(str), cont.values, cores=cores,
                                           titulo="SKUs por faixa de cobertura (DOI)"), key="g_saude_faixa",
                         detalhe=lambda rot: com_faixa[com_faixa["faixa"] == rot][cols], titulo="Faixa")
    with g2:
        por_tipo = df.groupby("tipo")["paletes"].sum().sort_values(ascending=False)
        graficos.mostrar(graficos.barras_h(por_tipo.index, por_tipo.values, titulo="Paletes ocupados por tipo"),
                         key="g_saude_tipo", detalhe=(df[cols].sort_values("paletes", ascending=False), "tipo"),
                         titulo="Tipo")
    top = df.sort_values("paletes", ascending=False).head(10)
    top = top.assign(rotulo=[f"{c} · {str(d)[:26]}" for c, d in zip(top["cod"], top["descricao"])])
    graficos.mostrar(graficos.barras_h(top["rotulo"], top["paletes"], casas=1,
                                       titulo="SKUs que mais ocupam espaço (paletes)"),
                     key="g_saude_top", detalhe=(top[cols + ["rotulo"]], "rotulo"), titulo="SKU")


# --- Book DPO ---------------------------------------------------------------
def _layouts(operacao_id: int) -> None:
    tema.secao("🗺️ Plantas e layouts por área", "Anexe imagens das áreas (picking, pulmão, vasilhame, pátio).")
    if not ui.somente_leitura(operacao_id):
        with st.form("f_layout", clear_on_submit=True):
            c1, c2 = st.columns(2)
            area = c1.text_input("Área", placeholder="Ex.: Picking, Pulmão 01, Vasilhame, Pátio")
            imgs = c2.file_uploader("Imagens", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
            if st.form_submit_button("🖼️ Anexar"):
                if not area.strip() or not imgs:
                    st.error("Informe a área e escolha ao menos uma imagem.")
                else:
                    for img in imgs:
                        dpo_repo.salvar_layout(operacao_id, area.strip(), img.name, img.type, img.getvalue())
                    ui.avisar(f"{len(imgs)} imagem(ns) anexada(s) em {area}.")
                    st.rerun()
    lays = dpo_repo.layouts(operacao_id)
    if not lays:
        st.caption("Nenhuma planta anexada ainda.")
        return
    areas = sorted({l["area"] for l in lays})
    filtro = st.selectbox("Área", ["Todas"] + areas, key="lay_area")
    vis = [l for l in lays if filtro == "Todas" or l["area"] == filtro]
    cols = st.columns(2)
    for i, l in enumerate(vis):
        with cols[i % 2].container(border=True):
            st.markdown(f"**📍 {l['area']}** · {l['nome_arquivo']} · {l['dt_atualizacao']}")
            try:
                st.image(l["conteudo"], **ui.LARGURA)
            except Exception:
                st.caption("Não foi possível mostrar esta imagem.")
            if st.button("🗑️ Excluir", key=f"del_lay_{l['id']}"):
                dpo_repo.excluir_layout(l["id"])
                ui.avisar("Imagem removida.", "info")
                st.rerun()


def _abc_layout(operacao_id: int) -> None:
    meses = estoque_repo.meses_curva_abc(operacao_id)
    if not meses:
        st.caption("Sem curva ABC calculada (Vendas › Importar Vendas).")
        return
    abc = estoque_repo.curva_abc_df(operacao_id, meses[0])
    resumo = curva_abc_service.resumo_classes(abc)
    if not resumo.empty:
        tema.kpis([{"titulo": f"Classe {r.classe} ({ui.nome_mes(meses[0])})", "valor": f"{r.skus} SKUs",
                    "detalhe": f"{ui.pct(r.pct_volume)} do volume — perto da expedição" if r.classe == "A"
                    else f"{ui.pct(r.pct_volume)} do volume", "status": "info", "icone": "🔤", "ver": "SKUs",
                    "dados": abc[abc["classe"] == r.classe][["cod", "descricao", "total_qtde", "pct_acumulado", "classe"]]}
                   for r in resumo.itertuples()], key="kp_arm_abc")


def _capacidade(operacao_id: int) -> None:
    r = armazem_service.resumo(operacao_id)
    tema.kpis([{"titulo": "Ocupação (paletes)", "valor": ui.pct(r["ocup_paletes"]) if r["cap_paletes"] else "—",
                "status": tema.status_ocupacao(r["ocup_paletes"]) if r["cap_paletes"] else "neutro", "icone": "🧱",
                "detalhe": "edite a capacidade em 🏗️ Capacidade & Áreas"}])


def _book(usuario, operacao_id, grupo, chave, extras=None):
    if operacoes_repo.e_consolidada(operacao_id):
        st.info("O Book DPO é por filial. Escolha uma filial no menu.")
        return
    padrao_dpo.progresso_book(operacao_id, MODULO, dpo.ARMAZEM, chave)
    padrao_dpo.book(operacao_id, usuario, MODULO, dpo.ARMAZEM[grupo], chave, extras)


def aba_fundamentos(usuario: dict, operacao_id: int) -> None:
    _book(usuario, operacao_id, "fundamentos", "arm_fund", {
        "1.1 - Otimização do Layout": lambda: _layouts(operacao_id),
        "1.2 - Layout Reflete ABC": lambda: _abc_layout(operacao_id),
        "1.3 - Gestão de Capacidade": lambda: _capacidade(operacao_id),
    })


def aba_manter(usuario: dict, operacao_id: int) -> None:
    _book(usuario, operacao_id, "manter", "arm_man")


def aba_melhorar(usuario: dict, operacao_id: int) -> None:
    _book(usuario, operacao_id, "melhorar", "arm_mel")


def aba_patio(usuario: dict, operacao_id: int) -> None:
    c1, _ = st.columns([1, 3])
    dia = c1.date_input("Dia", value=tempo.hoje(), format="DD/MM/YYYY", key="arm_patio_dia")
    descarga.painel_dia(operacao_id, dia, editar=not ui.somente_leitura(operacao_id), key="arm")


# --- Capacidade & áreas -----------------------------------------------------
def aba_estrutura(usuario: dict, operacao_id: int) -> None:
    if ui.somente_leitura(operacao_id):
        return
    tema.secao("Capacidade dos armazéns", "Edite na tabela — salva automaticamente. Nova linha = novo armazém.")
    arms = pd.DataFrame(armazem_repo.listar_armazens(operacao_id), columns=["id", "nome", "cap_hl", "cap_paletes"])

    def alterar(linha, alt):
        nome = (alt.get("nome", linha["nome"]) or "").strip()
        if not nome:
            raise RegraNegocioError("O armazém precisa de um nome.")
        if nome != linha["nome"]:
            armazem_repo.excluir_armazem(int(linha["id"]))
        armazem_repo.salvar_armazem(operacao_id, nome, float(alt.get("cap_hl", linha["cap_hl"]) or 0),
                                    float(alt.get("cap_paletes", linha["cap_paletes"]) or 0))

    def incluir(nova):
        if not (nova.get("nome") or "").strip():
            raise RegraNegocioError("Informe o nome do armazém.")
        armazem_repo.salvar_armazem(operacao_id, nova["nome"].strip(), float(nova.get("cap_hl") or 0),
                                    float(nova.get("cap_paletes") or 0))

    editor_autosave(arms, f"ed_arm_{operacao_id}", ["nome", "cap_hl", "cap_paletes"], alterar, incluir,
                    lambda l: armazem_repo.excluir_armazem(int(l["id"])), column_config={
                        "id": None, "nome": st.column_config.TextColumn("Armazém ✏️", required=True),
                        "cap_hl": st.column_config.NumberColumn("Capacidade (HL) ✏️", min_value=0, format="%.0f"),
                        "cap_paletes": st.column_config.NumberColumn("Capacidade (paletes) ✏️", min_value=0, format="%.0f")})

    armazens = armazem_repo.listar_armazens(operacao_id)
    if not armazens:
        return
    tema.secao("Áreas do armazém", "Picking, pulmão, docas...")
    arm = ui.select_registro("Armazém", armazens, permitir_vazio=False, key="est_arm")
    areas = armazem_repo.areas_df(operacao_id)
    nome_arm = next(a["nome"] for a in armazens if a["id"] == arm)
    areas = areas[areas["armazem"] == nome_arm] if not areas.empty else pd.DataFrame(
        columns=["id", "armazem", "area", "cap_paletes", "cap_hl"])
    areas = areas[["id", "area", "cap_paletes", "cap_hl"]]

    def salvar_area(linha, alt):
        nome = (alt.get("area", linha["area"]) or "").strip()
        if not nome:
            raise RegraNegocioError("A área precisa de um nome.")
        if nome != linha["area"]:
            armazem_repo.excluir_area(int(linha["id"]))
        armazem_repo.salvar_area(arm, nome, float(alt.get("cap_paletes", linha["cap_paletes"]) or 0),
                                 float(alt.get("cap_hl", linha["cap_hl"]) or 0))

    def incluir_area(nova):
        if not (nova.get("area") or "").strip():
            raise RegraNegocioError("Informe o nome da área.")
        armazem_repo.salvar_area(arm, nova["area"].strip(), float(nova.get("cap_paletes") or 0),
                                 float(nova.get("cap_hl") or 0))

    editor_autosave(areas, f"ed_area_{arm}", ["area", "cap_paletes", "cap_hl"], salvar_area, incluir_area,
                    lambda l: armazem_repo.excluir_area(int(l["id"])), column_config={
                        "id": None, "area": st.column_config.TextColumn("Área ✏️", required=True),
                        "cap_paletes": st.column_config.NumberColumn("Paletes ✏️", min_value=0, format="%.0f"),
                        "cap_hl": st.column_config.NumberColumn("HL ✏️", min_value=0, format="%.0f")})


def aba_produtos(usuario: dict, operacao_id: int) -> None:
    st.caption(f"{ui.numero(estoque_repo.contar_produtos())} produtos no cadastro (Relatório 01.11).")
    f = st.text_input("Buscar por código ou descrição", key="arm_busca")
    df = estoque_repo.buscar_produtos_df(f)
    ui.tabela(df, column_config={
        "cod": st.column_config.NumberColumn("Código", format="%d"), "descricao": "Descrição",
        "fator_hl": st.column_config.NumberColumn("Fator HL", format="%.4f"),
        "cx_pallet": st.column_config.NumberColumn("Cx/palete", format="%.0f"), "tipo": "Tipo", "categoria": "Categoria"})
    ui.downloads(df, "produtos", key="dl_prod")


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("armazem")
    ui.abas_modulo(usuario, "armazem", {
        "saude": aba_saude, "fundamentos": aba_fundamentos, "manter": aba_manter, "melhorar": aba_melhorar,
        "patio": aba_patio, "estrutura": aba_estrutura, "produtos": aba_produtos,
    }, usuario, operacao_id)
