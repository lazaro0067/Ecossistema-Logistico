"""Financeiro › 🎯 Gestão OBZ › 📈 L.E — projeção do fechamento do ano na curva atual.

Meses com realizado carregado = real. Meses que faltam = projeção (por padrão: a eficiência dos últimos 3 meses — real
÷ plan — aplicada ao plan de cada mês que falta; sem plan, a média recente). O mês aberto usa a tendência lançada, se
houver. Valores líquidos (receita reduz a despesa)."""
import html as _h

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import graficos, tema, tempo, ui
from modules.financeiro.obz_painel import AMARELO, AZUL, CINZA, VERDE, VERMELHO, _clicavel, _mk, _m, _p
from services import obz_service as obz

_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_CSS = """<style>
.le-fx{display:flex;gap:.5rem;flex-wrap:wrap;margin:.2rem 0 .7rem}
.le-fx div{flex:1 1 150px;border-radius:12px;padding:.5rem .7rem;border:1px solid #dfe5ee;background:#fff}
.le-fx b{display:block;font-size:1.05rem;color:#0B1F3A}
.le-fx span{font-size:.75rem;color:#52514e}
.le-fx .r{border-left:5px solid #0B1F3A}.le-fx .p{border-left:5px solid #2a78d6}.le-fx .t{border-left:5px solid #eda100}
</style>"""


def _cor(d: float, plan: float) -> str:
    if not plan:
        return CINZA
    pct = d / abs(plan) * 100
    return VERMELHO if pct >= 3 else AMARELO if pct > 0 else VERDE


def render(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "obz_le")
    hoje = tempo.hoje()
    anos = sorted({m[:4] for m in obz.meses(op)} | {str(hoje.year)}, reverse=True)
    c1, c2, c3 = st.columns([0.8, 3, 1.2])
    ano = c1.selectbox("Ano", anos, key="obz_le_ano")
    metodo = c2.selectbox("Como projetar os meses que faltam", list(obz.METODOS_LE), format_func=obz.METODOS_LE.get,
                          key="obz_le_met")
    with c3:
        st.write("")
        usar_tend = st.toggle("Usar tendência lançada no mês aberto", value=True, key="obz_le_tend")
    with st.spinner("Projetando o ano..."):
        d = obz.le_projecao(op, ano, metodo, usar_tend)
    if d.empty:
        st.info(f"Sem plan/real em {ano}. Suba a Base OBZ / 16.03.01 em ⚙️ OBZ: bases & cadastros.")
        return
    ms = [f"{ano}-{m:02d}" for m in range(1, 13)]
    fonte_mes = d.groupby("mes")["fonte"].agg(lambda x: "real" if (x == "real").all() else
                                               "tend" if (x == "tend").any() else "proj").reindex(ms).fillna("proj")
    n_real = int((fonte_mes == "real").sum())
    t = d[["plan", "real", "le"]].sum()
    real_ytd = float(d.loc[d["fonte"] == "real", "le"].sum())
    plan_ytd = float(d.loc[d["mes"].isin(fonte_mes[fonte_mes == "real"].index), "plan"].sum())
    proj = float(t["le"] - real_ytd)
    disp = float(t["le"] - t["plan"])
    st.markdown(_CSS, unsafe_allow_html=True)
    ult = fonte_mes[fonte_mes == "real"].index.max() if n_real else None
    st.markdown(
        '<div class="le-fx">'
        f'<div class="r"><b>📥 {n_real} mês(es) realizados</b><span>{"jan a " + obz.nome_mes(ult).lower() if ult else "nenhum ainda"}'
        f' — valem o real</span></div>'
        f'<div class="t"><b>📝 {int((fonte_mes == "tend").sum())} mês aberto com tendência</b><span>tendência lançada '
        f'pelos donos</span></div>'
        f'<div class="p"><b>📈 {int((fonte_mes == "proj").sum())} mês(es) projetados</b>'
        f'<span>{_h.escape(obz.METODOS_LE[metodo].split(" — ")[0])}</span></div></div>', unsafe_allow_html=True)
    tema.kpis([
        {"titulo": f"Plan {ano}", "valor": _mk(t["plan"]), "icone": "🎯", "status": "info", "detalhe": "orçamento do ano"},
        {"titulo": "Real acumulado", "valor": _mk(real_ytd), "icone": "📥", "status": "info",
         "detalhe": f"plan no período {_mk(plan_ytd)} · {_p((real_ytd / plan_ytd - 1) * 100 if plan_ytd else None)}"},
        {"titulo": "Projeção dos meses que faltam", "valor": _mk(proj), "icone": "📈", "status": "info",
         "detalhe": f"plan restante {_mk(t['plan'] - plan_ytd)}"},
        {"titulo": f"L.E {ano} (fechamento)", "valor": _mk(t["le"]), "icone": "🔮",
         "status": "critico" if disp > 0 and t["plan"] and disp / abs(t["plan"]) >= .03 else "atencao" if disp > 0
         else "bom", "detalhe": "real + projeção"},
        {"titulo": "L.E − Plan", "valor": _mk(disp), "icone": "⚖️",
         "status": "critico" if disp > 0 else "bom",
         "detalhe": f"{_p(disp / abs(t['plan']) * 100 if t['plan'] else None)} · "
                    + ("estoura o orçamento" if disp > 0 else "dentro do orçamento")},
    ], key="kp_obz_le")

    # mês a mês: real (barras cheias), projeção (barras claras), plan (linha) + acumulados
    m = d.groupby("mes")[["plan", "le"]].sum().reindex(ms).fillna(0.0)
    x = [_MESES[i] for i in range(12)]
    cores = {"real": "#0B1F3A", "tend": AMARELO, "proj": "#9cc3ef"}
    a1, a2 = st.columns([1.25, 1])
    with a1:
        fig = go.Figure()
        for f, nome in (("real", "Real"), ("tend", "Tendência"), ("proj", "Projeção")):
            ys = [v if fonte_mes[mm] == f else None for mm, v in zip(ms, m["le"])]
            if any(y is not None for y in ys):
                fig.add_bar(x=x, y=ys, name=nome, marker_color=cores[f],
                            hovertemplate=f"<b>%{{x}}</b><br>{nome}: R$ %{{y:,.0f}}<extra></extra>")
        fig.add_scatter(x=x, y=m["plan"], name="Plan", mode="lines+markers", line=dict(color=VERMELHO, dash="dot"))
        fig.update_layout(barmode="overlay")
        graficos.mostrar(graficos._layout(fig, f"Mês a mês — {ano}", 340), key="obz_le_g_mes")
    with a2:
        fig = go.Figure()
        fig.add_scatter(x=x, y=m["plan"].cumsum(), name="Plan acumulado", mode="lines",
                        line=dict(color=VERMELHO, dash="dot"))
        acum = m["le"].cumsum()
        fig.add_scatter(x=x[:n_real], y=acum.iloc[:n_real], name="Real acumulado", mode="lines+markers",
                        line=dict(color="#0B1F3A", width=3))
        fig.add_scatter(x=x[max(n_real - 1, 0):], y=acum.iloc[max(n_real - 1, 0):], name="L.E (curva)",
                        mode="lines+markers", line=dict(color=AZUL, dash="dash", width=3))
        graficos.mostrar(graficos._layout(fig, "Curva do ano (acumulado)", 340), key="obz_le_g_acum")

    # por departamento → contas
    tema.secao("🏢 L.E por departamento", "Clique numa barra (ou escolha abaixo) para abrir as contas do departamento.")
    g = d.groupby("area", as_index=False)[["plan", "le"]].sum()
    g["real"] = g["area"].map(d[d["fonte"] == "real"].groupby("area")["le"].sum()).fillna(0.0)
    g["proj"] = g["le"] - g["real"]
    g["disp"] = g["le"] - g["plan"]
    g = g.sort_values("disp", ascending=False).reset_index(drop=True)
    fig = go.Figure()
    fig.add_bar(y=g["area"], x=g["plan"], name="Plan ano", orientation="h", marker_color="#c9d3e3",
                customdata=g["area"])
    fig.add_bar(y=g["area"], x=g["le"], name="L.E", orientation="h", customdata=g["area"],
                marker_color=[_cor(dd, p) for dd, p in zip(g["disp"], g["plan"])])
    fig.update_layout(barmode="group")
    fig.update_yaxes(autorange="reversed")
    clic = _clicavel(graficos._layout(fig, "Plan × L.E por departamento", max(280, 44 * len(g) + 80)), "obz_le_g_area")
    if clic in set(g["area"]):
        st.session_state["obz_le_area"] = clic
    ui.tabela(_tabela(g, "Departamento", "area"), baixar=f"LE_{ano}_departamentos")
    areas = g["area"].tolist()
    atual = st.session_state.get("obz_le_area")
    area = st.selectbox("🔎 Abrir departamento", areas, index=areas.index(atual) if atual in areas else 0,
                        key="obz_le_area_box")
    st.session_state["obz_le_area"] = area
    da = d[d["area"] == area].assign(rot=lambda z: z["conta"] + " · " + z["nome_conta"].fillna("").str[:34])
    c = da.groupby("rot", as_index=False)[["plan", "le"]].sum()
    c["real"] = c["rot"].map(da[da["fonte"] == "real"].groupby("rot")["le"].sum()).fillna(0.0)
    c["proj"] = c["le"] - c["real"]
    c["disp"] = c["le"] - c["plan"]
    c = c.sort_values("disp", ascending=False).reset_index(drop=True)
    tema.secao(f"🧾 {area} — contas")
    ui.tabela(_tabela(c, "Conta", "rot"), baixar=f"LE_{ano}_{area}")
    with st.expander(f"📅 {area} — mês a mês por conta"):
        pv = da.pivot_table(index="rot", columns="mes", values="le", aggfunc="sum").reindex(columns=ms).fillna(0.0)
        pv = pv.loc[pv.sum(axis=1).abs().sort_values(ascending=False).index]
        out = pd.DataFrame({"Conta": list(pv.index)})
        for mm in ms:
            marca = "" if fonte_mes[mm] == "real" else " 📈" if fonte_mes[mm] == "proj" else " 📝"
            out[_MESES[int(mm[5:]) - 1] + marca] = [_mk(v) for v in pv[mm]]
        out["L.E"] = [_m(v) for v in pv.sum(axis=1)]
        ui.tabela(out, baixar=f"LE_{ano}_{area}_mensal")
        st.caption("📈 = projeção · 📝 = tendência lançada · sem marca = real.")


def _tabela(g: pd.DataFrame, nome: str, col: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "": ["🔴" if dd > 0 and p and dd / abs(p) >= .03 else "🟡" if dd > 0 else "🟢" for dd, p in zip(g["disp"], g["plan"])],
        nome: g[col], "Plan ano": g["plan"].map(_m), "Real acumulado": g["real"].map(_m),
        "Projeção restante": g["proj"].map(_m), "L.E": g["le"].map(_m), "L.E − Plan": g["disp"].map(_m),
        "%": [_p(dd / abs(p) * 100) if p else "—" for dd, p in zip(g["disp"], g["plan"])]})
    t = g[["plan", "real", "proj", "le", "disp"]].sum()
    out.loc[len(out)] = ["Σ", "TOTAL", _m(t["plan"]), _m(t["real"]), _m(t["proj"]), _m(t["le"]), _m(t["disp"]),
                         _p(t["disp"] / abs(t["plan"]) * 100) if t["plan"] else "—"]
    return out
