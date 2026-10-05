"""Ressuprimento › Metas mensais por cesta (salvam automaticamente)."""
import pandas as pd
import streamlit as st

from config.settings import CESTAS
from core import tema, tempo, ui
from modules.componentes.autosave import editor_autosave
from repositories import ressuprimento_repo
from services import ressuprimento_service as svc
from services.erros import RegraNegocioError

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]


def render(usuario: dict, operacao_id: int) -> None:
    hoje = tempo.hoje()
    c1, c2, _ = st.columns([1, 1, 2])
    ano = c1.number_input("Ano", min_value=2024, max_value=2035, value=hoje.year, key="meta_ano")
    mes = c2.selectbox("Mês", list(range(1, 13)), index=hoje.month - 1, format_func=lambda m: MESES[m - 1],
                       key="meta_mes")
    mes_ano = f"{int(ano)}-{mes:02d}"
    tema.secao(f"🎯 Metas de {MESES[mes - 1]}/{int(ano)}",
               "Digite a meta em HL — grava sozinho. Nova cesta: use a última linha (+).")
    if ui.somente_leitura(operacao_id):
        ui.tabela(ressuprimento_repo.metas_df(operacao_id, mes_ano))
        return

    existentes = svc.cestas_para_metas(operacao_id, mes_ano)
    base = pd.DataFrame({"cesta": list(CESTAS)}).merge(existentes, on="cesta", how="left")
    base = pd.concat([base, existentes[~existentes["cesta"].isin(list(CESTAS))]], ignore_index=True)
    base["meta_volume_hl"] = pd.to_numeric(base["meta_volume_hl"], errors="coerce").fillna(0.0)
    base["indicador"] = base["cesta"].map(svc.nome_cesta)
    base = base[["indicador", "meta_volume_hl", "cesta"]]

    def alterar(linha, alt):
        nova = (alt.get("cesta") or linha["cesta"]).strip()
        if nova != linha["cesta"]:
            svc.excluir_meta(operacao_id, mes_ano, linha["cesta"])
        svc.salvar_meta(operacao_id, mes_ano, nova, alt.get("meta_volume_hl", linha["meta_volume_hl"]))

    def incluir(nova):
        nome = (nova.get("cesta") or nova.get("indicador") or "").strip()
        if not nome:
            raise RegraNegocioError("Informe o nome da cesta (coluna Código da cesta).")
        svc.salvar_meta(operacao_id, mes_ano, nome, nova.get("meta_volume_hl") or 0)

    editor_autosave(base, f"ed_metas_{operacao_id}_{mes_ano}", ["meta_volume_hl", "cesta"], alterar, incluir,
                    lambda l: svc.excluir_meta(operacao_id, mes_ano, l["cesta"]), column_config={
                        "indicador": "Indicador",
                        "meta_volume_hl": st.column_config.NumberColumn("Meta do mês (HL) ✏️", min_value=0, format="%.0f",
                                                                        step=100),
                        "cesta": st.column_config.TextColumn("Código da cesta (relatório)")})
    anterior = svc.mes_anterior(mes_ano)
    if st.button(f"📋 Copiar metas de {ui.nome_mes(anterior)}", key="meta_copiar"):
        n = svc.copiar_metas(operacao_id, anterior, mes_ano)
        ui.avisar(f"{n} metas copiadas." if n else "O mês anterior não tem metas.", "success" if n else "warning")
        st.rerun()
