"""Tela padrão "formulário + histórico + indicadores" para áreas de registro.

Cada módulo simples só descreve seus campos (Campo) e indicadores;
o desenho da tela é feito aqui, uma vez só.
"""
import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
import streamlit as st

from core import ui
from repositories import registros_repo


@dataclass
class Campo:
    nome: str                       # coluna no banco
    rotulo: str
    tipo: str = "texto"             # texto | numero | inteiro | data | opcao | percentual
    opcoes: list[str] = field(default_factory=list)
    obrigatorio: bool = False
    padrao: object = None


@dataclass
class Indicador:
    rotulo: str
    calcular: Callable[[pd.DataFrame], object]
    formato: Callable[[object], str] = ui.numero


def _widget(c: Campo, container, key: str):
    if c.tipo == "data":
        return container.date_input(c.rotulo, value=c.padrao or dt.date.today(), format="DD/MM/YYYY", key=key)
    if c.tipo in ("numero", "percentual"):
        return container.number_input(c.rotulo, min_value=0.0, value=float(c.padrao or 0),
                                      max_value=100.0 if c.tipo == "percentual" else None, key=key)
    if c.tipo == "inteiro":
        return container.number_input(c.rotulo, min_value=0, value=int(c.padrao or 0), step=1, key=key)
    if c.tipo == "opcao":
        return container.selectbox(c.rotulo, c.opcoes, key=key)
    return container.text_input(c.rotulo, value=c.padrao or "", key=key)


def tela_registros(*, tabela: str, operacao_id: int, campos: list[Campo], titulo_form: str,
                   coluna_data: str | None = "data", indicadores: list[Indicador] | None = None,
                   calculados: Callable[[pd.DataFrame], pd.DataFrame] | None = None) -> None:
    aba_painel, aba_novo = st.tabs(["📊 Painel", f"➕ {titulo_form}"])

    with aba_novo:
        with st.form(f"form_{tabela}", clear_on_submit=True):
            valores, cols = {}, st.columns(3)
            for i, c in enumerate(campos):
                valores[c.nome] = _widget(c, cols[i % 3], f"{tabela}_{c.nome}")
            if st.form_submit_button("Salvar", type="primary"):
                faltando = [c.rotulo for c in campos if c.obrigatorio and not str(valores[c.nome]).strip()]
                if faltando:
                    st.error("Preencha: " + ", ".join(faltando))
                else:
                    dados = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in valores.items()}
                    registros_repo.inserir(tabela, {"operacao_id": operacao_id, **dados})
                    ui.avisar("Registro salvo!")
                    st.rerun()

    with aba_painel:
        mes = None
        if coluna_data:
            mes = st.text_input("Mês (AAAA-MM) — vazio mostra tudo", value=ui.mes_atual(), key=f"{tabela}_mes")
        df = registros_repo.listar_df(tabela, operacao_id, coluna_data, mes or None)
        if calculados is not None and not df.empty:
            df = calculados(df)

        if indicadores:
            cols = st.columns(len(indicadores))
            for col, ind in zip(cols, indicadores):
                col.metric(ind.rotulo, ind.formato(ind.calcular(df)) if not df.empty else "—")

        ui.tabela(df.drop(columns=["operacao_id"], errors="ignore"))
        c1, c2 = st.columns([1, 3])
        with c1:
            ui.download_csv(df, tabela)
        if not df.empty:
            with c2.popover("🗑️ Excluir registro"):
                rid = st.selectbox("ID", df["id"].tolist(), key=f"{tabela}_del")
                if st.button("Confirmar exclusão", key=f"{tabela}_delbtn"):
                    registros_repo.excluir(tabela, int(rid), operacao_id)
                    ui.avisar("Registro excluído.", "info")
                    st.rerun()
