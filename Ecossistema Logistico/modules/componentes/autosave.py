"""Tabela editável com salvamento automático (sem botão "Salvar").

Cada alteração de célula é gravada no banco na hora; a tabela é então
recarregada do banco, então o que aparece na tela é sempre o que está salvo.
"""
from typing import Callable

import pandas as pd
import streamlit as st

from core import ui
from services.erros import RegraNegocioError


def editor_autosave(df: pd.DataFrame, key: str, editaveis: list[str],
                    ao_alterar: Callable[[dict, dict], None],
                    ao_incluir: Callable[[dict], None] | None = None,
                    ao_excluir: Callable[[dict], None] | None = None,
                    column_config: dict | None = None, altura: int | None = None) -> None:
    versao = st.session_state.get(f"{key}__v", 0)
    k = f"{key}__{versao}"
    base = df.reset_index(drop=True)

    def _salvar():
        estado = st.session_state.get(k, {})
        try:
            for idx, alt in estado.get("edited_rows", {}).items():
                ao_alterar(base.iloc[int(idx)].to_dict(), alt)
            if ao_incluir:
                for nova in estado.get("added_rows", []):
                    if any(v not in (None, "") for v in nova.values()):
                        ao_incluir(nova)
            if ao_excluir:
                for idx in estado.get("deleted_rows", []):
                    ao_excluir(base.iloc[int(idx)].to_dict())
        except RegraNegocioError as e:
            ui.avisar(str(e), "error")
        except Exception as e:  # nunca perder a tela por um valor inválido
            from database.connection import tipo_violacao
            tipo = tipo_violacao(e)
            msg = ("Já existe um registro com esse nome/código." if tipo == "unica" else
                   "Este registro está em uso e não pode ser apagado." if tipo == "fk" else f"Não foi possível salvar: {e}")
            ui.avisar(msg, "error")
        else:
            ui.avisar("Salvo automaticamente", "success")
        st.session_state[f"{key}__v"] = versao + 1

    extra = {"height": altura} if altura else {}
    st.data_editor(
        base, key=k, on_change=_salvar, hide_index=True,
        disabled=[c for c in base.columns if c not in editaveis],
        num_rows="dynamic" if ao_incluir else "fixed",
        column_config=column_config, **ui.LARGURA, **extra,
    )
    st.caption("💾 As alterações são salvas automaticamente.")
    if not base.empty:
        vis = base.drop(columns=[c for c, v in (column_config or {}).items() if v is None and c in base.columns])
        ui._baixar_tabela(vis, "relatorio")
