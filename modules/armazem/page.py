"""Módulo Armazém — ocupação, capacidade e estrutura física."""
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from modules.componentes.autosave import editor_autosave
from repositories import armazem_repo, estoque_repo
from services import armazem_service
from services.erros import RegraNegocioError


def aba_ocupacao(usuario: dict, operacao_id: int) -> None:
    df = armazem_service.posicao_com_indicadores(operacao_id)
    r = armazem_service.resumo(operacao_id, df)
    tem_cap = bool(r["cap_paletes"] or r["cap_hl"])
    tema.kpis([
        {"titulo": "Ocupação em paletes", "valor": ui.pct(r["ocup_paletes"]) if r["cap_paletes"] else "—",
         "detalhe": f"{ui.numero(r['paletes'])} de {ui.numero(r['cap_paletes'])} posições", "icone": "🧱",
         "status": tema.status_ocupacao(r["ocup_paletes"]) if r["cap_paletes"] else "neutro",
         "selo": None if r["cap_paletes"] else "cadastre a capacidade"},
        {"titulo": "Ocupação em HL", "valor": ui.pct(r["ocup_hl"]) if r["cap_hl"] else "—",
         "detalhe": f"{ui.compacto(r['hl'])} de {ui.compacto(r['cap_hl'])} HL", "icone": "🍺",
         "status": tema.status_ocupacao(r["ocup_hl"]) if r["cap_hl"] else "neutro"},
        {"titulo": "Posições livres", "valor": ui.numero(max(r["cap_paletes"] - r["paletes"], 0)), "icone": "⬜",
         "status": "info"},
        {"titulo": "SKUs armazenados", "valor": r["skus"], "icone": "📦", "status": "info"},
    ])
    if not df.empty:
        g1, g2 = st.columns(2)
        with g1:
            por_tipo = df.groupby(df["tipo"].fillna("Sem tipo"))["paletes"].sum().sort_values(ascending=False)
            graficos.mostrar(graficos.barras_h(por_tipo.index, por_tipo.values, titulo="Paletes ocupados por tipo"),
                             key="g_arm_tipo")
        with g2:
            top = df.sort_values("paletes", ascending=False).head(10)
            graficos.mostrar(graficos.barras_h([f"{c} · {str(d)[:22]}" for c, d in zip(top["cod"], top["descricao"])],
                                               top["paletes"], casas=1, titulo="SKUs que mais ocupam (paletes)"),
                             key="g_arm_top")

    tema.secao("Capacidade dos armazéns", "Edite na tabela — salva automaticamente. Nova linha = novo armazém.")
    arms = pd.DataFrame(armazem_repo.listar_armazens(operacao_id), columns=["id", "nome", "cap_hl", "cap_paletes"])

    def _alterar(linha, alt):
        nome = (alt.get("nome", linha["nome"]) or "").strip()
        if not nome:
            raise RegraNegocioError("O armazém precisa de um nome.")
        if nome != linha["nome"]:
            armazem_repo.excluir_armazem(int(linha["id"]))
        armazem_repo.salvar_armazem(operacao_id, nome, float(alt.get("cap_hl", linha["cap_hl"]) or 0),
                                    float(alt.get("cap_paletes", linha["cap_paletes"]) or 0))

    def _incluir(nova):
        if not (nova.get("nome") or "").strip():
            raise RegraNegocioError("Informe o nome do armazém.")
        armazem_repo.salvar_armazem(operacao_id, nova["nome"].strip(), float(nova.get("cap_hl") or 0),
                                    float(nova.get("cap_paletes") or 0))

    editor_autosave(arms, f"ed_arm_{operacao_id}", ["nome", "cap_hl", "cap_paletes"], _alterar, _incluir,
                    lambda l: armazem_repo.excluir_armazem(int(l["id"])), column_config={
                        "id": None, "nome": st.column_config.TextColumn("Armazém", required=True),
                        "cap_hl": st.column_config.NumberColumn("Capacidade (HL) ✏️", min_value=0, format="%.0f"),
                        "cap_paletes": st.column_config.NumberColumn("Capacidade (paletes) ✏️", min_value=0, format="%.0f"),
                    })


def aba_estrutura(usuario: dict, operacao_id: int) -> None:
    armazens = armazem_repo.listar_armazens(operacao_id)
    if not armazens:
        st.info("Cadastre um armazém na aba **Ocupação & Capacidade** primeiro.")
        return
    tema.secao("Áreas do armazém", "Picking, pulmão, docas... Edite na tabela — salva automaticamente.")
    arm = ui.select_registro("Armazém", armazens, permitir_vazio=False, key="est_arm")
    areas = armazem_repo.areas_df(operacao_id)
    areas = areas[areas["armazem"] == next(a["nome"] for a in armazens if a["id"] == arm)] \
        if not areas.empty else pd.DataFrame(columns=["id", "armazem", "area", "cap_paletes", "cap_hl"])
    areas = areas[["id", "area", "cap_paletes", "cap_hl"]]

    def _salvar(linha, alt):
        nome = (alt.get("area", linha["area"]) or "").strip()
        if not nome:
            raise RegraNegocioError("A área precisa de um nome.")
        if nome != linha["area"]:
            armazem_repo.excluir_area(int(linha["id"]))
        armazem_repo.salvar_area(arm, nome, float(alt.get("cap_paletes", linha["cap_paletes"]) or 0),
                                 float(alt.get("cap_hl", linha["cap_hl"]) or 0))

    def _incluir(nova):
        if not (nova.get("area") or "").strip():
            raise RegraNegocioError("Informe o nome da área.")
        armazem_repo.salvar_area(arm, nova["area"].strip(), float(nova.get("cap_paletes") or 0),
                                 float(nova.get("cap_hl") or 0))

    editor_autosave(areas, f"ed_area_{arm}", ["area", "cap_paletes", "cap_hl"], _salvar, _incluir,
                    lambda l: armazem_repo.excluir_area(int(l["id"])), column_config={
                        "id": None, "area": st.column_config.TextColumn("Área", required=True),
                        "cap_paletes": st.column_config.NumberColumn("Paletes ✏️", min_value=0, format="%.0f"),
                        "cap_hl": st.column_config.NumberColumn("HL ✏️", min_value=0, format="%.0f"),
                    })


def aba_produtos(usuario: dict, operacao_id: int) -> None:
    st.caption(f"{ui.numero(estoque_repo.contar_produtos())} produtos no cadastro (Relatório 01.11).")
    f = st.text_input("Buscar por código ou descrição", key="arm_busca")
    ui.tabela(estoque_repo.buscar_produtos_df(f), column_config={
        "cod": st.column_config.NumberColumn("Código", format="%d"), "descricao": "Descrição",
        "fator_hl": st.column_config.NumberColumn("Fator HL", format="%.4f"),
        "cx_pallet": st.column_config.NumberColumn("Cx/palete", format="%.0f"), "tipo": "Tipo", "categoria": "Categoria",
    })


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("armazem")
    ui.abas_modulo(usuario, "armazem", {"ocupacao": aba_ocupacao, "estrutura": aba_estrutura,
                                        "produtos": aba_produtos}, usuario, operacao_id)
