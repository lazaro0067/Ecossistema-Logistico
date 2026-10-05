"""Gráficos (Plotly) com um único padrão visual.

Regras: um eixo só (nunca eixo duplo), cores categóricas em ordem fixa,
cores de status só para estado, rótulos em tinta neutra, grade discreta.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.tema import STATUS, TINTA, TINTA_2, TINTA_3  # noqa: F401
from core.ui import LARGURA

CATEGORICAS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
COR_META = "#0B1F3A"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"
FONTE = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

# situação de estoque -> status
COR_SITUACAO = {
    "Ruptura": STATUS["critico"][0], "Crítico": STATUS["serio"][0], "Abaixo da meta": STATUS["atencao"][0],
    "OK": STATUS["bom"][0], "Excesso": "#2a78d6", "Sem giro": "#c3c2b7",
}


def _layout(fig: go.Figure, titulo: str = "", altura: int = 340, legenda: bool = True) -> go.Figure:
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=15, color=TINTA), x=0, xanchor="left", y=0.97) if titulo else None,
        height=altura, margin=dict(l=8, r=8, t=48 if titulo else 12, b=8),
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        font=dict(family=FONTE, size=12, color=TINTA_2),
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title=None,
                    font=dict(size=12, color=TINTA_2)),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=EIXO, font=dict(family=FONTE, color=TINTA, size=12)),
        bargap=0.28, barcornerradius=4,
    )
    fig.update_xaxes(showgrid=False, linecolor=EIXO, tickfont=dict(color=TINTA_3), title=None, zeroline=False)
    fig.update_yaxes(gridcolor=GRADE, gridwidth=1, zeroline=False, linecolor=EIXO,
                     tickfont=dict(color=TINTA_3), title=None, separatethousands=True)
    return fig


def mostrar(fig: go.Figure, key: str | None = None, detalhe=None, colunas: dict | None = None,
            titulo: str | None = None) -> None:
    """Desenha o gráfico. Com `detalhe`, clicar numa barra/ponto abre os registros dela:
       detalhe = (df, "coluna")  → filtra df[coluna] == rótulo clicado
       detalhe = função(rótulo) → devolve o DataFrame a mostrar."""
    config = {"displayModeBar": False, "locale": "pt-BR"}
    if detalhe is None or not key:
        st.plotly_chart(fig, key=key, config=config, **LARGURA)
        return
    versao = st.session_state.get(f"_gv_{key}", 0)
    try:
        ev = st.plotly_chart(fig, key=f"{key}__{versao}", config=config, on_select="rerun",
                             selection_mode=("points",), **LARGURA)
    except TypeError:  # versão sem seleção
        st.plotly_chart(fig, key=key, config=config, **LARGURA)
        return
    try:
        pontos = list(ev["selection"]["points"]) if ev else []
    except (KeyError, TypeError, AttributeError):
        pontos = []
    if not pontos:
        return
    p = pontos[0]
    candidatos = [str(p.get(k)) for k in ("y", "x", "label", "customdata") if p.get(k) is not None]
    if callable(detalhe):
        horizontal = bool(fig.data) and getattr(fig.data[0], "orientation", None) == "h"
        rotulo = str(p.get("y") if horizontal else p.get("x", p.get("label", "")))
        df = detalhe(rotulo)
    else:
        base, coluna = detalhe
        valores = base[coluna].astype(str)
        rotulo = next((c for c in candidatos if c in set(valores)), None)
        if rotulo is None:
            return
        df = base[valores == rotulo]
    st.session_state[f"_gv_{key}"] = versao + 1  # limpa a seleção no próximo carregamento
    from core.tema import detalhe as abrir

    abrir(f"{titulo + ': ' if titulo else ''}{rotulo}", df, colunas)


def real_x_meta(df: pd.DataFrame, x: str, real: str, meta: str, titulo: str = "",
                unidade: str = "", invertido: bool = False, rotulos_x=None) -> go.Figure:
    """Barras do realizado (cor = status vs meta) + marcador da meta. Mesmo eixo/unidade."""
    from core.tema import status_atingimento

    pcts = [(r / m * 100) if m else None for r, m in zip(df[real], df[meta])]
    cores = [STATUS[status_atingimento(p, invertido)][0] if p is not None else "#2a78d6" for p in pcts]
    xs = rotulos_x if rotulos_x is not None else df[x]
    fig = go.Figure()
    fig.add_bar(x=xs, y=df[real], name="Realizado", marker_color=cores, showlegend=False,
                customdata=[f"{p:.0f}% da meta" if p is not None else "sem meta" for p in pcts],
                hovertemplate=f"<b>%{{x}}</b><br>Realizado: %{{y:,.0f}} {unidade}<br>%{{customdata}}<extra></extra>")
    fig.add_scatter(x=xs, y=df[meta], name="Meta", mode="markers+lines",
                    line=dict(color=COR_META, width=2, dash="dot"),
                    marker=dict(symbol="line-ew-open", size=22, line=dict(width=3, color=COR_META)),
                    hovertemplate=f"Meta: %{{y:,.0f}} {unidade}<extra></extra>")
    return _layout(fig, titulo)


def barras_h(rotulos, valores, cores=None, titulo: str = "", casas: int = 0,
             sufixo: str = "", altura: int | None = None, textos=None) -> go.Figure:
    from core.ui import numero

    rotulos, valores = list(rotulos), list(valores)
    formato = f",.{casas}f"
    fig = go.Figure(go.Bar(
        y=rotulos, x=valores, orientation="h",
        marker_color=cores or CATEGORICAS[0],
        text=textos if textos is not None else [f"{numero(v, casas)}{sufixo}" for v in valores],
        textposition="outside", textfont=dict(color=TINTA_2, size=12), cliponaxis=False,
        hovertemplate=f"<b>%{{y}}</b><br>%{{x:{formato}}}{sufixo}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    maximo = max([v for v in valores if v == v] or [0])
    fig.update_xaxes(showgrid=False, showticklabels=False, range=[0, maximo * 1.18 if maximo > 0 else 1])
    return _layout(fig, titulo, altura or max(220, 40 * len(rotulos) + 70), legenda=False)


def barras(x, series: dict[str, list], titulo: str = "", sufixo: str = "", empilhado: bool = False,
           cores: list[str] | None = None) -> go.Figure:
    fig = go.Figure()
    for i, (nome, ys) in enumerate(series.items()):
        fig.add_bar(x=list(x), y=list(ys), name=nome, marker_color=(cores or CATEGORICAS)[i % 8],
                    marker_line=dict(color="#ffffff", width=2) if empilhado else None,
                    hovertemplate=f"<b>%{{x}}</b><br>{nome}: %{{y:,.1f}}{sufixo}<extra></extra>")
    if empilhado:
        fig.update_layout(barmode="stack")
    return _layout(fig, titulo, legenda=len(series) > 1)


def linhas(x, series: dict[str, list], titulo: str = "", sufixo: str = "",
           tracejadas: tuple[str, ...] = ()) -> go.Figure:
    fig = go.Figure()
    for i, (nome, ys) in enumerate(series.items()):
        trac = nome in tracejadas
        fig.add_scatter(x=list(x), y=list(ys), name=nome, mode="lines",
                        line=dict(color=COR_META if trac else CATEGORICAS[i % 8], width=2, dash="dot" if trac else None),
                        hovertemplate=f"{nome}: %{{y:,.1f}}{sufixo}<extra></extra>")
    fig.update_layout(hovermode="x unified")
    return _layout(fig, titulo, legenda=len(series) > 1)
