"""Componente de importação de planilhas com de/para de colunas."""
import streamlit as st

from core import ui
from services import importacao_service as imp
from services.erros import RegraNegocioError


def importador(layouts: list[str], operacao_id: int, key: str) -> None:
    layout_key = st.selectbox(
        "O que você vai importar?", layouts, key=f"{key}_layout",
        format_func=lambda k: imp.LAYOUTS[k]["rotulo"],
    )
    layout = imp.LAYOUTS[layout_key]

    with st.expander("Campos esperados"):
        st.markdown("\n".join(
            f"- **{rot}**{' *(obrigatório)*' if obrig else ''}"
            for rot, _, obrig, _ in layout["campos"].values()
        ))
        if layout["modo"] == "substituir_operacao":
            st.caption("⚠️ Esta importação substitui toda a posição atual desta operação.")
        if layout["modo"] == "substituir_data":
            st.caption("⚠️ As datas presentes no arquivo são substituídas.")

    arquivo = st.file_uploader("Planilha (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"],
                               key=f"{key}_arq_{layout_key}")
    if not arquivo:
        return

    try:
        df = imp.ler_arquivo(arquivo.name, arquivo)
    except Exception as e:  # arquivo corrompido/formato estranho
        st.error(f"Não consegui ler o arquivo: {e}")
        return

    st.caption(f"{len(df)} linhas lidas. Prévia:")
    ui.tabela(df.head(5))

    st.markdown("**De/para das colunas**")
    sugestao = imp.sugerir_mapeamento(layout_key, list(df.columns))
    opcoes = [None] + list(df.columns)
    mapa, cols = {}, st.columns(3)
    for i, (campo, (rotulo, _, obrig, _)) in enumerate(layout["campos"].items()):
        mapa[campo] = cols[i % 3].selectbox(
            rotulo + (" *" if obrig else ""), opcoes,
            index=opcoes.index(sugestao[campo]) if sugestao[campo] in opcoes else 0,
            format_func=lambda c: "— não importar —" if c is None else c,
            key=f"{key}_{layout_key}_{campo}",
        )

    mes_ano = None
    if layout.get("pede_mes"):
        mes_ano = st.text_input("Mês de referência (AAAA-MM)", value=ui.mes_atual(), key=f"{key}_mes")

    if st.button("📥 Importar", type="primary", key=f"{key}_btn"):
        try:
            dados = imp.preparar(layout_key, df, mapa)
            n = imp.gravar(layout_key, dados, operacao_id, mes_ano)
        except RegraNegocioError as e:
            st.error(str(e))
            return
        ui.avisar(f"{n} registros importados em '{layout['rotulo']}'.")
        st.rerun()
