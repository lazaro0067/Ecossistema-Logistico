"""Financeiro › 🎯 Gestão OBZ › 💲 R$/HL por departamento — quanto cada departamento gasta por HL vendido."""
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from modules.financeiro.obz_painel import AZUL, CINZA, VERDE, VERMELHO, _clicavel, _mk
from services import obz_service as obz


def _rs(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _div(a, b):
    return a / b if b else None


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+.1f}%".replace(".", ",")


def render(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "obz_rshl")
    meses_obz = obz.meses(op)
    if not meses_obz:
        st.info("Suba a Base OBZ ou o 16.03.01 (⚙️ OBZ: bases & cadastros) e a 03.02.37 vendas (Gestão Corporativa › "
                "📥 Relatórios) para ver o gasto por HL.")
        return
    anos = sorted({m[:4] for m in meses_obz}, reverse=True)
    c1, c2, c3 = st.columns([1, 1, 1.6])
    ano = c1.selectbox("Ano", anos, key="rshl_ano")
    g = obz.gastos_ano(op, ano)
    hl = obz.hl_mensal(op, ano)
    meses_real = sorted(m for m in g.loc[g["real"] != 0, "mes"].unique() if hl.get(m))
    if not meses_real:
        st.warning(f"Em {ano} não há mês com realizado do OBZ **e** HL vendido (03.02.37 vendas) ao mesmo tempo.")
        return
    mes = c2.selectbox("Mês", meses_real[::-1], key="rshl_mes", format_func=ui.nome_mes)
    with c3:
        per = ui._escolha("rshl_per", ["mes", "ytd"], "mes", pills=True,
                          formatar={"mes": "🗓️ Mês", "ytd": "📆 Acumulado do ano"}.get)
    lista = [m for m in meses_real if m <= mes] if per == "ytd" else [mes]
    rot = f"jan a {ui.nome_mes(mes)}" if per == "ytd" else ui.nome_mes(mes)
    hl_p = sum(hl.get(m, 0.0) for m in lista)
    sel = g[g["mes"].isin(lista)]
    real, plan = float(sel["real"].sum()), float(sel["plan"].sum())
    # mês anterior (para comparação)
    ant = [m for m in meses_real if m < lista[0]]
    rs_ant = None
    if ant and per == "mes":
        a = ant[-1]
        rs_ant = _div(float(g.loc[g["mes"] == a, "real"].sum()), hl.get(a, 0.0))
    rs_real, rs_plan = _div(real, hl_p), _div(plan, hl_p)
    tema.kpis([
        {"titulo": f"HL vendido · {rot}", "valor": ui.numero(hl_p), "icone": "🍺", "status": "info",
         "detalhe": "venda + bonificação"},
        {"titulo": "Gasto OBZ (real)", "valor": _mk(real), "icone": "💸", "status": "info",
         "detalhe": f"plan {_mk(plan)}"},
        {"titulo": "R$/HL real", "valor": _rs(rs_real), "icone": "💲",
         "status": "neutro" if not rs_plan else "bom" if rs_real <= rs_plan else "critico",
         "detalhe": f"plan {_rs(rs_plan)}/HL" + (f" · mês anterior {_rs(rs_ant)}" if rs_ant else "")},
        {"titulo": "Diferença por HL", "valor": _rs((rs_real or 0) - (rs_plan or 0)) if rs_plan else "—",
         "icone": "⚖️", "status": "neutro" if not rs_plan else "bom" if rs_real <= rs_plan else "critico",
         "detalhe": f"{_p(_div((rs_real or 0) - rs_plan, rs_plan) * 100 if rs_plan else None)} sobre o plan"},
    ], key="kp_rshl")

    ar = sel.groupby("area", as_index=False)[["real", "plan"]].sum()
    ar["rs_real"] = ar["real"] / hl_p
    ar["rs_plan"] = ar["plan"] / hl_p
    ar["dif"] = ar["rs_real"] - ar["rs_plan"]
    ar = ar.sort_values("rs_real", ascending=False).reset_index(drop=True)
    tema.secao(f"🏢 R$/HL por departamento · {rot}", "Clique numa barra para abrir as contas do departamento.")
    fig = go.Figure()
    fig.add_bar(y=ar["area"], x=ar["rs_plan"], name="Plan R$/HL", orientation="h", marker_color="#c9d3e3",
                customdata=ar["area"], hovertemplate="<b>%{y}</b><br>Plan: R$ %{x:,.2f}/HL<extra></extra>")
    fig.add_bar(y=ar["area"], x=ar["rs_real"], name="Real R$/HL", orientation="h", customdata=ar["area"],
                marker_color=[VERMELHO if d > 0.005 and p else VERDE if p else AZUL
                              for d, p in zip(ar["dif"], ar["plan"])],
                hovertemplate="<b>%{y}</b><br>Real: R$ %{x:,.2f}/HL<extra></extra>")
    fig.update_layout(barmode="group")
    fig.update_yaxes(autorange="reversed")
    clic = _clicavel(graficos._layout(fig, "Real × plan por HL vendido", max(280, 44 * len(ar) + 80)), "rshl_bar")
    if clic in set(ar["area"]):
        st.session_state["rshl_area"] = clic
    vis = pd.DataFrame({"": ["🔴" if d > 0.005 and p else "🟢" if p else "⚪" for d, p in zip(ar["dif"], ar["plan"])],
                        "Departamento": ar["area"], "Gasto real": ar["real"].map(_rs), "Gasto plan": ar["plan"].map(_rs),
                        "R$/HL real": ar["rs_real"].map(_rs), "R$/HL plan": ar["rs_plan"].map(_rs),
                        "Dif. R$/HL": ar["dif"].map(_rs),
                        "% do gasto": (ar["real"] / real * 100 if real else 0).map(lambda v: f"{v:.1f}%".replace(".", ","))})
    vis.loc[len(vis)] = ["Σ", "TOTAL", _rs(real), _rs(plan), _rs(rs_real), _rs(rs_plan),
                         _rs((rs_real or 0) - (rs_plan or 0)) if rs_plan else "—", "100%"]
    ui.tabela(vis, baixar=f"rs_hl_departamentos_{mes}")

    # evolução no ano: R$/HL total e por departamento
    tema.secao(f"📈 Evolução do R$/HL em {ano}")
    piv = g.groupby(["mes", "area"])["real"].sum().unstack(fill_value=0.0)
    ms = [m for m in sorted(piv.index) if hl.get(m)]
    if ms:
        x = [ui.nome_mes(m) for m in ms]
        tot_r = [float(g.loc[g["mes"] == m, "real"].sum()) / hl[m] for m in ms]
        tot_p = [float(g.loc[g["mes"] == m, "plan"].sum()) / hl[m] for m in ms]
        fig = go.Figure()
        fig.add_bar(x=x, y=tot_r, name="Real R$/HL", marker_color=[VERMELHO if r > p > 0 else VERDE if p else CINZA
                                                                    for r, p in zip(tot_r, tot_p)])
        fig.add_scatter(x=x, y=tot_p, name="Plan R$/HL", mode="lines+markers", line=dict(color="#0B1F3A", dash="dot"))
        graficos.mostrar(graficos._layout(fig, "R$/HL total por mês", 320), key="rshl_lin")
        heat = pd.DataFrame({"Departamento": list(piv.columns)})
        for m, rx in zip(ms, x):
            heat[rx] = [_rs(piv.at[m, a] / hl[m]) for a in piv.columns]
        heat["Média"] = [_rs(sum(piv.at[m, a] for m in ms) / sum(hl[m] for m in ms)) for a in piv.columns]
        heat.loc[len(heat)] = ["TOTAL", *[_rs(v) for v in tot_r],
                               _rs(sum(float(g.loc[g["mes"] == m, "real"].sum()) for m in ms) / sum(hl[m] for m in ms))]
        ui.tabela(heat, baixar=f"rs_hl_mensal_{ano}")

    # contas do departamento
    areas = ar["area"].tolist()
    if not areas:
        return
    atual = st.session_state.get("rshl_area")
    area = st.selectbox("🔎 Contas do departamento", areas, index=areas.index(atual) if atual in areas else 0,
                        key="rshl_area_sel")
    st.session_state["rshl_area"] = area
    ct = sel[sel["area"] == area].groupby(["conta", "nome_conta"], as_index=False)[["real", "plan"]].sum()
    ct["rs_real"], ct["rs_plan"] = ct["real"] / hl_p, ct["plan"] / hl_p
    ct = ct.sort_values("real", ascending=False)
    t = pd.DataFrame({"": ["🔴" if r > p and p else "🟢" if p else "⚪" for r, p in zip(ct["real"], ct["plan"])],
                      "Conta": ct["conta"].astype(str) + " · " + ct["nome_conta"].fillna(""),
                      "Gasto real": ct["real"].map(_rs), "Gasto plan": ct["plan"].map(_rs),
                      "R$/HL real": ct["rs_real"].map(_rs), "R$/HL plan": ct["rs_plan"].map(_rs),
                      "Dif. R$/HL": (ct["rs_real"] - ct["rs_plan"]).map(_rs)}).reset_index(drop=True)
    ui.tabela(t, baixar=f"rs_hl_{area}_{mes}")
    st.caption("R$/HL = despesa líquida do OBZ (16.03.01 / Base OBZ, sem bonificação) ÷ HL vendido no período "
               "(03.02.37 vendas, operações de HL: venda + bonificação). Plan por HL usa o mesmo HL vendido.")
