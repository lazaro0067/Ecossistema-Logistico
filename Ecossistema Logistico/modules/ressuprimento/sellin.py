"""Ressuprimento › 📈 Acompanhamento › 📥 Volume Sell-in.

Sell-in = HL que entrou comprado da Ambev (03.02.37 compra, operações de HL de compra, data = coluna F).
Compara com a meta do mês (🎯 Metas Mensais do ressuprimento), com o HL puxado (relatório de ressuprimento) e com o
sell-out (03.02.37 vendas, venda + bonificação). Sell-in − sell-out = quanto o estoque cresceu (ou caiu) em HL."""
import calendar
import datetime as dt

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core import graficos, tema, tempo, ui
from repositories import ressuprimento_repo
from services import faturamento_service as fs

_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
AZUL, VERDE, VERMELHO, AMARELO, ESCURO = "#2a78d6", "#1baf7a", "#e34948", "#eda100", "#0B1F3A"


def _n(v, casas=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, casas)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%".replace(".", ",")


@st.cache_data(ttl=300, show_spinner=False)
def _diario(op: int, de: str, ate: str, versao: str) -> pd.DataFrame:
    """HL por dia: sell-in (compra) e sell-out (venda)."""
    c = fs.dia_df(op, "compra", de, ate, fs.STATUS_PADRAO["compra"])
    v = fs.dia_df(op, "venda", de, ate, fs.STATUS_PADRAO["venda"])
    ci = c[c["operacao_cod"].astype(str).isin(fs.operacoes_do_setor("hl_compra"))] if not c.empty else c
    cr = c[c["operacao_cod"].astype(str).isin(fs.operacoes_do_setor("compra"))] if not c.empty else c
    vo = v[v["operacao_cod"].astype(str).isin(fs.operacoes_do_setor("hl_venda"))] if not v.empty else v
    out = pd.DataFrame({"data": pd.date_range(de, ate).strftime("%Y-%m-%d")})
    for nome, x, col in (("sellin", ci, "hl"), ("sellin_rs", cr, "valor"), ("sellout", vo, "hl")):
        g = x.groupby("data")[col].sum() if not x.empty else pd.Series(dtype=float)
        out[nome] = out["data"].map(g).fillna(0.0)
    return out


def _puxado(op: int, mes: str) -> float | None:
    try:
        from services import ressuprimento_service as rs

        real, _, _ = rs.real_do_mes(op, mes)
        return float(real.sum()) if len(real) else None
    except Exception:  # noqa: BLE001
        return None


def _meta(op: int, mes: str) -> float:
    m = ressuprimento_repo.metas_df(op, mes)
    return float(pd.to_numeric(m["meta_volume_hl"], errors="coerce").sum()) if not m.empty else 0.0


def render(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "sellin")
    meses = fs.meses(op, "compra")
    if not meses:
        st.info("Para o sell-in, suba a **03.02.37 compra** em Gestão Corporativa › 📥 Relatórios (pode ser o ano "
                "inteiro em .zip).")
        return
    c1, c2, _ = st.columns([1.2, 1, 2])
    with c1:
        modo = ui._escolha("si_modo", ["mes", "ano"], "mes", pills=True, formatar={"mes": "🗓️ Mês", "ano": "📆 Ano"}.get)
    ult = fs.ultimas(op)
    versao = f"{ult.get('notas_compra')}|{ult.get('entregas_notas')}"  # muda quando sobe compra/venda nova
    if modo == "ano":
        ano = c2.selectbox("Ano", sorted({m[:4] for m in meses}, reverse=True), key="si_ano")
        _ano(op, ano, versao)
        return
    mes = ui.seletor_mes("Mês", meses, key="si_mes", container=c2)
    de, ate = fs.periodo_mes(mes)
    d = _diario(op, de, ate, versao)
    hoje = tempo.hoje()
    dias_mes = calendar.monthrange(int(mes[:4]), int(mes[5:]))[1]
    aberto = mes == hoje.strftime("%Y-%m")
    corridos = hoje.day if aberto else dias_mes
    si, so, rs = float(d["sellin"].sum()), float(d["sellout"].sum()), float(d["sellin_rs"].sum())
    meta = _meta(op, mes)
    proj = si / corridos * dias_mes if aberto and corridos else si
    pux = _puxado(op, mes)
    ating = si / meta * 100 if meta else None
    tema.kpis([
        {"titulo": f"Sell-in · {ui.nome_mes(mes)}", "valor": f"{_n(si)} HL", "icone": "📥", "status": "info",
         "detalhe": f"{ui.moeda(rs)} comprados · {ui.moeda(rs / si if si else None)}/HL"},
        {"titulo": "Meta do mês", "valor": f"{_n(meta)} HL" if meta else "sem meta", "icone": "🎯",
         "status": "neutro" if not meta else "bom" if (ating or 0) >= 100 else "atencao" if (ating or 0) >= 90
         else "critico", "detalhe": f"atingido {_p(ating)}" if meta else "cadastre em 🎯 Metas Mensais"},
        {"titulo": "Projeção do mês", "valor": f"{_n(proj)} HL", "icone": "🔮",
         "status": "neutro" if not meta else "bom" if proj >= meta else "critico",
         "detalhe": (f"ritmo de {corridos} de {dias_mes} dias · {_p(proj / meta * 100) if meta else ''} da meta"
                     if aberto else "mês fechado")},
        {"titulo": "Sell-out (vendas)", "valor": f"{_n(so)} HL", "icone": "📤", "status": "info",
         "detalhe": "venda + bonificação"},
        {"titulo": "Sell-in − sell-out", "valor": f"{_n(si - so)} HL", "icone": "📦",
         "status": "atencao" if si - so > 0.1 * max(so, 1) else "bom",
         "detalhe": "estoque subiu" if si > so else "estoque caiu"},
        {"titulo": "HL puxado (ressuprimento)", "valor": f"{_n(pux)} HL" if pux is not None else "—", "icone": "🚛",
         "status": "info", "detalhe": f"sell-in ÷ puxado {_p(si / pux * 100) if pux else '—'}"},
    ], key="kp_sellin")

    x = [dt.date.fromisoformat(v).strftime("%d") for v in d["data"]]
    fig = go.Figure()
    fig.add_bar(x=x, y=d["sellin"], name="Sell-in do dia (HL)", marker_color=AZUL)
    fig.add_scatter(x=x, y=d["sellin"].cumsum(), name="Sell-in acumulado", mode="lines", line=dict(color=ESCURO,
                                                                                                   width=3))
    fig.add_scatter(x=x, y=d["sellout"].cumsum(), name="Sell-out acumulado", mode="lines",
                    line=dict(color=VERDE, width=2))
    if meta:
        fig.add_scatter(x=x, y=[meta / dias_mes * (i + 1) for i in range(len(x))], name="Meta linear", mode="lines",
                        line=dict(color=VERMELHO, dash="dot"))
    graficos.mostrar(graficos._layout(fig, f"Sell-in × sell-out dia a dia — {ui.nome_mes(mes)}", 360), key="si_g_dia")

    tema.secao("📦 Sell-in por embalagem", "HL comprado × HL vendido no mês, por categoria de produto.")
    _por_categoria(op, mes, mes, versao)


@st.cache_data(ttl=300, show_spinner=False)
def _cat(op: int, de: str, ate: str, versao: str) -> pd.DataFrame:
    from services import produtos_service as ps

    c = fs.produto_df(op, "compra", de, ate, fs.STATUS_PADRAO["compra"], fs.operacoes_do_setor("hl_compra"))
    v = fs.produto_df(op, "venda", de, ate, fs.STATUS_PADRAO["venda"], fs.operacoes_do_setor("hl_venda"))
    for x in (c, v):
        if not x.empty:
            x["cat"] = [ps.categoria_detalhada(dsc) for dsc in x["descricao"]]
    gc = c.groupby("cat")["hl"].sum() if not c.empty else pd.Series(dtype=float)
    gv = v.groupby("cat")["hl"].sum() if not v.empty else pd.Series(dtype=float)
    idx = sorted(set(gc.index) | set(gv.index))
    out = pd.DataFrame({"cat": idx, "sellin": [float(gc.get(i, 0.0)) for i in idx],
                        "sellout": [float(gv.get(i, 0.0)) for i in idx]})
    return out.sort_values("sellin", ascending=False).reset_index(drop=True)


def _por_categoria(op: int, de: str, ate: str, versao: str) -> None:
    g = _cat(op, de, ate, versao)
    if g.empty:
        st.info("Sem produtos no período.")
        return
    tot_si, tot_so = g["sellin"].sum(), g["sellout"].sum()
    vis = pd.DataFrame({"Embalagem / categoria": g["cat"], "Sell-in (HL)": g["sellin"].map(_n),
                        "Sell-out (HL)": g["sellout"].map(_n), "Diferença (HL)": (g["sellin"] - g["sellout"]).map(_n),
                        "Sell-in ÷ sell-out": [(_p(a / b * 100) if b else "—") for a, b in zip(g["sellin"], g["sellout"])],
                        "% do sell-in": (g["sellin"] / tot_si * 100 if tot_si else g["sellin"] * 0).map(_p)})
    vis.loc[len(vis)] = ["TOTAL", _n(tot_si), _n(tot_so), _n(tot_si - tot_so),
                         _p(tot_si / tot_so * 100) if tot_so else "—", "100%"]
    ui.tabela(vis, baixar=f"sellin_categoria_{de}_{ate}")


def _ano(op: int, ano: str, versao: str) -> None:
    d = _diario(op, f"{ano}-01-01", f"{ano}-12-31", versao)
    d["mes"] = d["data"].str[:7]
    g = d.groupby("mes")[["sellin", "sellout", "sellin_rs"]].sum()
    g = g[(g["sellin"] > 0) | (g["sellout"] > 0)]
    if g.empty:
        st.info(f"Sem compras em {ano}.")
        return
    g["meta"] = [_meta(op, m) for m in g.index]
    g["puxado"] = [_puxado(op, m) for m in g.index]
    si, so, mt = g["sellin"].sum(), g["sellout"].sum(), g["meta"].sum()
    tema.kpis([
        {"titulo": f"Sell-in {ano}", "valor": f"{_n(si)} HL", "icone": "📥", "status": "info",
         "detalhe": f"{ui.moeda(g['sellin_rs'].sum())} comprados"},
        {"titulo": "Meta acumulada", "valor": f"{_n(mt)} HL" if mt else "sem meta", "icone": "🎯",
         "status": "neutro" if not mt else "bom" if si >= mt else "critico",
         "detalhe": f"atingido {_p(si / mt * 100)}" if mt else "cadastre em 🎯 Metas Mensais"},
        {"titulo": f"Sell-out {ano}", "valor": f"{_n(so)} HL", "icone": "📤", "status": "info"},
        {"titulo": "Sell-in − sell-out", "valor": f"{_n(si - so)} HL", "icone": "📦", "status": "info",
         "detalhe": "variação de estoque no ano"},
    ], key="kp_sellin_ano")
    x = [_MESES[int(m[5:]) - 1] for m in g.index]
    fig = go.Figure()
    fig.add_bar(x=x, y=g["sellin"], name="Sell-in (HL)", marker_color=AZUL)
    fig.add_bar(x=x, y=g["sellout"], name="Sell-out (HL)", marker_color=VERDE)
    if mt:
        fig.add_scatter(x=x, y=g["meta"].where(g["meta"] > 0), name="Meta", mode="lines+markers",
                        line=dict(color=VERMELHO, dash="dot"))
    fig.update_layout(barmode="group")
    graficos.mostrar(graficos._layout(fig, f"Sell-in × sell-out × meta — {ano}", 360), key="si_g_ano")
    vis = pd.DataFrame({"Mês": x, "Sell-in (HL)": g["sellin"].map(_n), "Meta (HL)": g["meta"].map(lambda v: _n(v) if v
                                                                                                 else "—"),
                        "% meta": [(_p(a / b * 100) if b else "—") for a, b in zip(g["sellin"], g["meta"])],
                        "Sell-out (HL)": g["sellout"].map(_n), "Diferença (HL)": (g["sellin"] - g["sellout"]).map(_n),
                        "HL puxado": g["puxado"].map(_n), "R$ comprado": g["sellin_rs"].map(ui.moeda)})
    vis.loc[len(vis)] = ["TOTAL", _n(si), _n(mt) if mt else "—", _p(si / mt * 100) if mt else "—", _n(so), _n(si - so),
                         _n(g["puxado"].dropna().sum()), ui.moeda(g["sellin_rs"].sum())]
    ui.tabela(vis, baixar=f"sellin_{ano}")
    tema.secao(f"📦 Sell-in por embalagem — {ano}")
    _por_categoria(op, g.index.min(), g.index.max(), versao)
