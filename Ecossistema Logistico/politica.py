"""Ressuprimento › Política de estoque (mínimo / objetivo / máximo por SKU)."""
import datetime as dt

import numpy as np
import streamlit as st

from core import graficos, tema, ui
from repositories import dpo_repo

STATUS = {"🎯 No objetivo": "bom", "🟢 Dentro da política": "bom", "🔴 Abaixo da política": "critico",
          "🔵 Acima da política": "info"}


def render(usuario: dict, operacao_id: int) -> None:
    datas = dpo_repo.datas_politica(operacao_id)
    if not datas:
        st.info("Nenhuma política importada. Envie a planilha em **📁 Atualização de Bases › 6. Política de estoque**.")
        return
    c1, _ = st.columns([1, 3])
    data = c1.selectbox("Data da política", datas, format_func=lambda d: dt.date.fromisoformat(d).strftime("%d/%m/%Y"),
                        key="pol_data")
    df = dpo_repo.politica_df(operacao_id, data)
    df["status"] = np.select(
        [df["doi_atual"] < df["pe_min_dias"], df["doi_atual"] > df["pe_max_dias"],
         (df["doi_atual"] - df["pe_obj_dias"]).abs() <= 2],
        ["🔴 Abaixo da política", "🔵 Acima da política", "🎯 No objetivo"], default="🟢 Dentro da política")
    cont = df["status"].value_counts()
    filtro_k = "pol_filtro"
    st.session_state.setdefault(filtro_k, None)
    def _filtrar(rot):
        def acao():
            st.session_state[filtro_k] = None if st.session_state[filtro_k] == rot else rot
            st.rerun()
        return acao

    tema.kpis([{"titulo": rot, "valor": f"{int(cont.get(rot, 0))} SKUs", "status": cor,
                "detalhe": ui.pct(cont.get(rot, 0) / len(df) * 100),
                "selo": "✓ filtrando" if st.session_state[filtro_k] == rot else None,
                "ver": "limpar filtro" if st.session_state[filtro_k] == rot else "filtrar a tabela",
                "ao_clicar": _filtrar(rot)} for rot, cor in STATUS.items()], key="kp_pol")
    f1, f2 = st.columns(2)
    tipo = f1.selectbox("Tipo", ["Todos"] + sorted(df["tipo"].dropna().unique()), key="pol_tipo")
    cat = f2.selectbox("Categoria", ["Todas"] + sorted(df["categoria"].dropna().unique()), key="pol_cat")
    vis = df
    if st.session_state[filtro_k]:
        vis = vis[vis["status"] == st.session_state[filtro_k]]
    if tipo != "Todos":
        vis = vis[vis["tipo"] == tipo]
    if cat != "Todas":
        vis = vis[vis["categoria"] == cat]

    abaixo = df[df["status"] == "🔴 Abaixo da política"].assign(falta=lambda d: d["pe_min_dias"] - d["doi_atual"]) \
        .sort_values("falta", ascending=False).head(12)
    if not abaixo.empty:
        graficos.mostrar(graficos.barras_h([f"{c} · {str(d)[:24]}" for c, d in zip(abaixo["cod"], abaixo["descricao"])],
                                           abaixo["falta"].round(1), casas=1, sufixo=" d",
                                           cores=[tema.STATUS["critico"][0]] * len(abaixo),
                                           titulo="Mais abaixo do mínimo (dias faltando)"), key="g_pol")
    cols_v = ["status", "cod", "descricao", "tipo", "categoria", "estoque", "demanda", "doi_atual", "pe_min_dias",
              "pe_obj_dias", "pe_max_dias", "pe_obj_hl"]
    ui.tabela(vis[cols_v], column_config={
        "cod": st.column_config.NumberColumn("Código", format="%d"),
        "doi_atual": st.column_config.NumberColumn("DOI atual", format="%.1f"),
        "pe_min_dias": st.column_config.NumberColumn("Mín (d)", format="%.1f"),
        "pe_obj_dias": st.column_config.NumberColumn("Obj (d)", format="%.1f"),
        "pe_max_dias": st.column_config.NumberColumn("Máx (d)", format="%.1f"),
        "pe_obj_hl": st.column_config.NumberColumn("Obj (HL)", format="%.1f")})
    ui.downloads(vis[cols_v], f"politica_estoque_{data}", key="dl_pol")
