"""Importador genérico: escolhe a base e usa o cartão de atualização automática."""
import streamlit as st

from modules.componentes.bases import card_base
from services import importacao_service as imp


def importador(layouts: list[str], operacao_id: int, usuario: dict, key: str) -> None:
    layout_key = st.selectbox("Qual base você vai atualizar?", layouts, key=f"{key}_layout",
                              format_func=lambda k: imp.LAYOUTS[k]["rotulo"])
    freq = imp.LAYOUTS[layout_key].get("frequencia_dias", 30)
    card_base(layout_key, operacao_id, usuario, imp.LAYOUTS[layout_key]["rotulo"],
              "Diário" if freq <= 1 else f"A cada {freq} dias")
