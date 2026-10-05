"""Tela padrão "painel + lançamentos" para áreas de registro.

Cada módulo simples só descreve seus campos, indicadores e gráfico;
o desenho da tela (e o respeito às permissões por aba) é feito aqui.
"""
import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
import streamlit as st

from core import graficos, tema, tempo, ui
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
    icone: str = ""
    # devolve "bom" | "atencao" | "serio" | "critico" | "info" a partir do valor
    status: Callable[[object], str] | None = None


@dataclass
class Grafico:
    titulo: str
    agrupar_por: str                # coluna do eixo X / categoria
    valor: str                      # coluna somada / média
    agregacao: str = "sum"          # sum | mean | count
    horizontal: bool = True
    sufixo: str = ""


def _widget(c: Campo, container, key: str):
    if c.tipo == "data":
        return container.date_input(c.rotulo, value=c.padrao or tempo.hoje(), format="DD/MM/YYYY", key=key)
    if c.tipo in ("numero", "percentual"):
        return container.number_input(c.rotulo, min_value=0.0, value=float(c.padrao or 0),
                                      max_value=100.0 if c.tipo == "percentual" else None, key=key)
    if c.tipo == "inteiro":
        return container.number_input(c.rotulo, min_value=0, value=int(c.padrao or 0), step=1, key=key)
    if c.tipo == "opcao":
        return container.selectbox(c.rotulo, c.opcoes, key=key)
    return container.text_input(c.rotulo, value=c.padrao or "", key=key)


def tela_registros(*, modulo: str, usuario: dict, tabela: str, operacao_id: int, campos: list[Campo],
                   coluna_data: str | None = "data", indicadores: list[Indicador] | None = None,
                   graficos_: list[Grafico] | None = None,
                   calculados: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
                   grafico_extra: Callable[[pd.DataFrame], None] | None = None,
                   extras: dict[str, Callable[[], None]] | None = None) -> None:

    def painel(*_):
        mes = None
        if coluna_data:
            c1, _c = st.columns([1, 3])
            mes = c1.text_input("Mês (AAAA-MM) — vazio mostra tudo", value=ui.mes_atual(), key=f"{tabela}_mes")
        df = registros_repo.listar_df(tabela, operacao_id, coluna_data, mes or None)
        if calculados is not None and not df.empty:
            df = calculados(df)
        if df.empty:
            st.info("Nenhum lançamento neste período.")
            return

        if indicadores:
            cards = []
            for ind in indicadores:
                v = ind.calcular(df)
                cards.append({"titulo": ind.rotulo, "valor": ind.formato(v), "icone": ind.icone,
                              "status": ind.status(v) if ind.status else "info"})
            tema.kpis(cards)

        if grafico_extra is not None:
            grafico_extra(df)
        if graficos_:
            cols = st.columns(len(graficos_))
            for i, (col, g) in enumerate(zip(cols, graficos_)):
                serie = df.groupby(df[g.agrupar_por].fillna("—"))[g.valor].agg(g.agregacao)
                with col:
                    if g.horizontal:
                        serie = serie.sort_values(ascending=False).head(10)
                        fig = graficos.barras_h(serie.index, serie.values, titulo=g.titulo, sufixo=g.sufixo,
                                                casas=1 if g.agregacao == "mean" else 0)
                    else:
                        serie = serie.sort_index()
                        fig = graficos.barras(serie.index, {g.titulo: serie.values}, titulo=g.titulo, sufixo=g.sufixo)
                    graficos.mostrar(fig, key=f"g_{tabela}_{i}")

        ui.tabela(df.drop(columns=["operacao_id"], errors="ignore"))
        c1, c2 = st.columns([1, 3])
        with c1:
            ui.download_csv(df, tabela, key=f"dl_{tabela}")
        with c2.popover("🗑️ Excluir lançamento"):
            rid = st.selectbox("ID", df["id"].tolist(), key=f"{tabela}_del")
            if st.button("Confirmar exclusão", key=f"{tabela}_delbtn"):
                registros_repo.excluir(tabela, int(rid), operacao_id)
                ui.avisar("Lançamento excluído.", "info")
                st.rerun()

    def lancamentos(*_):
        if ui.somente_leitura(operacao_id):
            return
        with st.form(f"form_{tabela}", clear_on_submit=True):
            valores, cols = {}, st.columns(3)
            for i, c in enumerate(campos):
                valores[c.nome] = _widget(c, cols[i % 3], f"{tabela}_{c.nome}")
            if st.form_submit_button("💾 Salvar lançamento", type="primary"):
                faltando = [c.rotulo for c in campos if c.obrigatorio and not str(valores[c.nome]).strip()]
                if faltando:
                    st.error("Preencha: " + ", ".join(faltando))
                else:
                    dados = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in valores.items()}
                    registros_repo.inserir(tabela, {"operacao_id": operacao_id, **dados})
                    ui.avisar("Lançamento salvo!")
                    st.rerun()

    ui.abas_modulo(usuario, modulo, {"painel": painel, "lancamentos": lancamentos, **(extras or {})})
