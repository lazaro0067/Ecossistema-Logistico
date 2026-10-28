"""Financeiro › 🎯 Gestão OBZ › 📊 Painel — visão geral → departamento → conta (ou por dono), dinâmico e clicável."""
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from services import obz_service as obz

VERDE, AMARELO, VERMELHO, AZUL, CINZA = "#1baf7a", "#eda100", "#e34948", "#2a78d6", "#9aa3b2"
_CSS = """
<style>
.obz-trilha { display:flex; gap:.4rem; align-items:center; font-size:.92rem; margin:.2rem 0 .6rem; color:#52514e; }
.obz-trilha b { color:#0B1F3A; }
.obz-grade { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:.6rem; margin:.3rem 0 .8rem; }
.obz-card { background:#fff; border:1px solid #dfe5ee; border-radius:14px; padding:.7rem .85rem; border-left:6px solid var(--c); }
.obz-card .t { font-size:.78rem; color:#52514e; font-weight:700; text-transform:uppercase; letter-spacing:.02em; }
.obz-card .v { font-size:1.25rem; font-weight:900; color:#0B1F3A; margin-top:.15rem; }
.obz-card .m { font-size:.78rem; color:#52514e; }
.obz-card .d { font-size:.85rem; font-weight:800; color:var(--c); margin-top:.15rem; }
.obz-bar { height:7px; background:#eef1f6; border-radius:5px; margin:.35rem 0 .1rem; overflow:hidden; }
.obz-bar span { display:block; height:100%; background:var(--c); }
</style>
"""


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _mk(v) -> str:
    """R$ compacto (mil / mi)."""
    if v is None or pd.isna(v):
        return "—"
    a = abs(v)
    if a >= 1e6:
        return f"R$ {v / 1e6:,.2f} mi".replace(",", "X").replace(".", ",").replace("X", ".")
    if a >= 1e3:
        return f"R$ {v / 1e3:,.1f} mil".replace(",", "X").replace(".", ",").replace("X", ".")
    return ui.moeda(v)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+.1f}%".replace(".", ",")


def _cor(desf, plan, limite=10.0) -> str:
    if not plan:
        return CINZA if not desf else (VERMELHO if desf > 0 else VERDE)
    pct = desf / abs(plan) * 100
    return VERMELHO if pct >= limite else AMARELO if pct > 0 else VERDE


def _agrupar(b: pd.DataFrame, chave: str) -> pd.DataFrame:
    g = b.groupby(chave, as_index=False)[["plan", "real", "tend", "fechamento", "disp", "desfavoravel"]].sum()
    g["disp_pct"] = g["disp"] / g["plan"].abs().where(g["plan"] != 0) * 100
    g["contas"] = g[chave].map(b.groupby(chave)["conta"].nunique())
    g["criticas"] = g[chave].map(b[b["critica"] & (b["desfavoravel"] > 0)].groupby(chave)["conta"].nunique()).fillna(0)
    return g.sort_values("desfavoravel", ascending=False).reset_index(drop=True)


def _cartoes(g: pd.DataFrame, chave: str, extra: dict | None = None) -> None:
    html = []
    for _, r in g.iterrows():
        cor = _cor(r["desfavoravel"], r["plan"])
        uso = min(abs(r["fechamento"]) / abs(r["plan"]) * 100, 130) if r["plan"] else 0
        sub = (extra or {}).get(r[chave], "")
        html.append(f'<div class="obz-card" style="--c:{cor}"><div class="t">{r[chave]}</div>'
                    f'<div class="v">{_mk(r["fechamento"])}</div><div class="m">plan {_mk(r["plan"])}'
                    f'{" · " + sub if sub else ""}</div>'
                    f'<div class="obz-bar"><span style="width:{min(uso, 100):.0f}%"></span></div>'
                    f'<div class="d">{_mk(r["disp"])} · {_p(r["disp_pct"])}'
                    f'{" · 🚨 " + str(int(r["criticas"])) if r["criticas"] else ""}</div></div>')
    st.markdown(_CSS + '<div class="obz-grade">' + "".join(html) + "</div>", unsafe_allow_html=True)


def _clicavel(fig: go.Figure, key: str) -> str | None:
    """Mostra o gráfico; devolve o rótulo clicado (barra/fatia)."""
    v = st.session_state.get(f"_obzg_{key}", 0)
    try:
        ev = st.plotly_chart(fig, key=f"{key}_{v}", on_select="rerun", selection_mode=("points",),
                             config={"displayModeBar": False, "locale": "pt-BR"}, **ui.LARGURA)
        pontos = list(ev["selection"]["points"]) if ev else []
    except Exception:
        return None
    if not pontos:
        return None
    p = pontos[0]
    st.session_state[f"_obzg_{key}"] = v + 1
    for k in ("customdata", "label", "y", "x"):
        val = p.get(k)
        if isinstance(val, (list, tuple)):
            val = val[0] if val else None
        if val not in (None, ""):
            return str(val)
    return None


def _barras_plan_real(g: pd.DataFrame, chave: str, titulo: str, rotulos=None) -> go.Figure:
    rot = list(rotulos if rotulos is not None else g[chave])
    fig = go.Figure()
    fig.add_bar(y=rot, x=g["plan"], name="Plan", orientation="h", marker_color="#c9d3e3", customdata=g[chave],
                hovertemplate="<b>%{y}</b><br>Plan: R$ %{x:,.0f}<extra></extra>")
    fig.add_bar(y=rot, x=g["fechamento"], name="Real", orientation="h", customdata=g[chave],
                marker_color=[_cor(d, p) for d, p in zip(g["desfavoravel"], g["plan"])],
                hovertemplate="<b>%{y}</b><br>Real: R$ %{x:,.0f}<extra></extra>")
    fig.update_layout(barmode="group")
    fig.update_yaxes(autorange="reversed")
    return graficos._layout(fig, titulo, max(260, 46 * len(rot) + 80))


def _sunburst(b: pd.DataFrame, raiz: str) -> go.Figure:
    b = b[b["plan"].abs() + b["fechamento"].abs() > 0]
    ids, labels, parents, values, cores, hover = [raiz], [raiz], [""], [0.0], [CINZA], [""]
    for (area, vbz), g in b.groupby(["area", "vbz"]):
        if f"A|{area}" not in ids:
            ga = b[b["area"] == area]
            ids.append(f"A|{area}"), labels.append(area), parents.append(raiz)
            values.append(float(ga["fechamento"].abs().sum()))
            cores.append(_cor(ga["desfavoravel"].sum(), ga["plan"].sum()))
            hover.append(f"Plan {_mk(ga['plan'].sum())} · Real {_mk(ga['fechamento'].sum())}")
        ids.append(f"V|{area}|{vbz}"), labels.append(vbz), parents.append(f"A|{area}")
        values.append(float(g["fechamento"].abs().sum()))
        cores.append(_cor(g["desfavoravel"].sum(), g["plan"].sum()))
        hover.append(f"Plan {_mk(g['plan'].sum())} · Real {_mk(g['fechamento'].sum())}")
    fig = go.Figure(go.Sunburst(ids=ids, labels=labels, parents=parents, values=values, branchvalues="remainder",
                                marker=dict(colors=cores, line=dict(color="#fff", width=2)), hovertext=hover,
                                hovertemplate="<b>%{label}</b><br>%{hovertext}<extra></extra>", maxdepth=2,
                                insidetextorientation="radial"))
    return graficos._layout(fig, "Mapa: departamento → VBZ (cor = dispersão)", 420, legenda=False)


def _linha_mes(op: int, ano: str, area: str | None = None) -> go.Figure | None:
    s = obz.serie_mensal(op, ano)
    if s.empty:
        return None
    if area:
        s = s[s["area"] == area]
    p = s.pivot_table(index="mes", columns="tipo", values="valor", aggfunc="sum").reindex(
        [f"{ano}-{m:02d}" for m in range(1, 13)])
    if "real" in p:  # mês sem real carregado fica vazio (não é zero)
        p["real"] = p["real"].where(p["real"].abs() > 0.004)
    x = [obz.nome_mes(m)[:3] for m in p.index]
    fig = go.Figure()
    if "plan" in p:
        fig.add_scatter(x=x, y=p["plan"], name="Plan", mode="lines+markers", line=dict(color="#0B1F3A", dash="dot"))
    if "real" in p:
        fig.add_bar(x=x, y=p["real"], name="Real", marker_color=[
            (VERMELHO if (r or 0) > (pl or 0) else VERDE) if pd.notna(r) else CINZA
            for r, pl in zip(p["real"], p["plan"] if "plan" in p else [0] * len(p))])
    return graficos._layout(fig, f"Plan × Real por mês — {area or 'todos os departamentos'}", 320)


def _kpis(b: pd.DataFrame, rotulo: str, chave: str) -> None:
    t = b[["plan", "real", "tend", "fechamento", "disp", "desfavoravel"]].sum()
    crit = b[b["critica"] & (b["desfavoravel"] > 0)]
    pend = b[b["status"] == "aguardando"]
    pct = t["disp"] / abs(t["plan"]) * 100 if t["plan"] else None
    tema.kpis([
        {"titulo": f"Plan · {rotulo}", "valor": _mk(t["plan"]), "icone": "🎯", "status": "info"},
        {"titulo": "Real", "valor": _mk(t["real"]), "icone": "📥", "status": "info",
         "detalhe": "16.03.01 / Base OBZ"},
        {"titulo": "Real ÷ Plan", "valor": f"{t['real'] / t['plan'] * 100:.1f}%".replace(".", ",") if t["plan"] else "—",
         "icone": "📏", "status": "info", "detalhe": "quanto do plan foi gasto"},
        {"titulo": "Dispersão", "valor": _mk(t["disp"]), "icone": "⚖️",
         "status": "critico" if t["desfavoravel"] > 0 and (pct or 0) >= 10 else "atencao" if t["desfavoravel"] > 0
         else "bom", "detalhe": f"{_p(pct)} sobre o plan"},
        {"titulo": "Contas críticas", "valor": ui.numero(crit["conta"].nunique()), "icone": "🚨",
         "status": "critico" if len(crit) else "bom", "detalhe": "acima do limite",
         "dados": _tabela(crit) if len(crit) else None},
        {"titulo": "Justificativas p/ aprovar", "valor": ui.numero(len(pend)), "icone": "⏳",
         "status": "atencao" if len(pend) else "bom"},
    ], key=f"kp_{chave}")


def _tabela(b: pd.DataFrame) -> pd.DataFrame:
    b = b.sort_values("desfavoravel", ascending=False)
    return pd.DataFrame({
        "": [("🔴" if c and d > 0 else "🟡" if d > 0 else "🟢") for c, d in zip(b["critica"], b["desfavoravel"])],
        "Conta": b["conta"].astype(str) + " · " + b["nome_conta"].fillna(""), "Departamento": b["area"],
        "VBZ": b["vbz"], "Responsável": b["responsavel"], "Plan": b["plan"].map(_m), "Real": b["real"].map(_m),
        "Dispersão": b["disp"].map(_m), "Disp. %": b["disp_pct"].map(_p),
        "Status": b["status"].map(obz.STATUS).fillna(""), "Justificativa": b["justificativa"].fillna("")}) \
        .reset_index(drop=True)


def _trilha(nivel: list[str]) -> None:
    cols = st.columns([1] + [1.6] * (len(nivel)) + [6 - len(nivel)])
    if cols[0].button("🏠 Geral", key="obz_nav_home", type="secondary" if nivel else "primary"):
        st.session_state["obz_nivel"] = []
        st.rerun()
    for i, n in enumerate(nivel):
        if cols[i + 1].button(f"› {n[:22]}", key=f"obz_nav_{i}", type="primary" if i == len(nivel) - 1 else "secondary"):
            st.session_state["obz_nivel"] = nivel[: i + 1]
            st.rerun()


def _abrir(*nivel: str) -> None:
    st.session_state["obz_nivel"] = list(nivel)
    st.rerun()


def _ir_conta(chave: str, grupo: str) -> None:
    v = st.session_state.get(chave)
    if v:
        st.session_state["obz_nivel"] = [grupo, v]
    if chave == "obz_d_sel":
        st.session_state[chave] = ""


def _busca_conta(sel: pd.DataFrame, grupo: str, atual: str | None) -> None:
    """Seletor de conta que fica visível também dentro da conta — para pesquisar outra sem voltar."""
    ct = sel.groupby(["conta", "nome_conta"], as_index=False)["desfavoravel"].sum()
    ct = ct.sort_values("desfavoravel", ascending=False)
    nomes = dict(zip(ct["conta"].astype(str), ct["nome_conta"].fillna("")))
    chave = "obz_c_sel" if atual else "obz_d_sel"
    opcoes = list(nomes) if atual else [""] + list(nomes)
    if atual and st.session_state.get(chave) != atual and atual in nomes:
        st.session_state[chave] = atual
    st.selectbox("🔎 Pesquisar conta" if atual else "🔎 Abrir conta", opcoes, key=chave,
                 format_func=lambda c: "— escolha —" if not c else f"{c} · {nomes.get(c, '')}",
                 on_change=_ir_conta, args=(chave, grupo))


def render(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "obz_painel")
    if obz.contas().empty:
        st.info("Suba a **Base OBZ** (ou o 16.03.01) em ⚙️ OBZ: bases & cadastros › 📥 Realizado & Base.")
        return
    meses = obz.meses_real(op)
    if not meses:
        st.info("Ainda não há realizado carregado. Suba o 16.03.01 ou a Base OBZ em ⚙️ OBZ: bases & cadastros. "
                "A projeção do ano fica na aba 📈 L.E.")
        return
    c1, c2, c3 = st.columns([1.3, 1, 1.6])
    with c1:
        per = ui._escolha("obz_p_per", ["mes", "ytd"], "mes", pills=True,
                          formatar={"mes": "🗓️ Mês", "ytd": "📆 Acumulado do ano"}.get)
    mes = ui.seletor_mes("Mês", meses, key="obz_p_mes", container=c2)
    with c3:
        visao = ui._escolha("obz_p_visao", ["area", "dono"], "area", pills=True,
                            formatar={"area": "🏢 Por departamento", "dono": "👤 Por dono"}.get)
    lista = [m for m in meses if m[:4] == mes[:4] and m <= mes] if per == "ytd" else [mes]
    rotulo = f"jan a {obz.nome_mes(mes).lower()}" if per == "ytd" else obz.nome_mes(mes)
    with st.spinner("Calculando o OBZ..."):
        b = obz.painel(op, lista, so_real=True)
    st.caption("📥 Só o **realizado** (meses com 16.03.01 / Base OBZ carregados) contra o plan — sem tendência nem "
               "projeção. A projeção do fechamento do ano está em **📈 L.E**.")
    if b.empty:
        st.info(f"Sem plan/real em {rotulo}.")
        return
    nivel = st.session_state.get("obz_nivel", [])
    if nivel and visao == "area" and nivel[0] not in set(b["area"]):
        nivel = []
    if nivel and visao == "dono" and nivel[0] not in set(b["responsavel"]):
        nivel = []
    _trilha(nivel)
    campo = "area" if visao == "area" else "responsavel"

    if not nivel:  # ---------------- Geral
        _kpis(b, rotulo, "obz_geral")
        g = _agrupar(b, campo)
        donos = dict(zip(b["area"], b["dono_area"].fillna(""))) if visao == "area" else {}
        st.markdown("**Clique num departamento** (no gráfico ou nos botões) para abrir as contas."
                    if visao == "area" else "**Clique num dono** para ver as contas dele.")
        _cartoes(g, campo, {k: f"👤 {v}" for k, v in donos.items() if v})
        bcols = st.columns(min(len(g), 6) or 1)
        for i, nome in enumerate(g[campo]):
            if bcols[i % len(bcols)].button(f"🔎 {nome[:24]}", key=f"obz_ab_{i}"):
                _abrir(nome)
        a1, a2 = st.columns([1.3, 1])
        with a1:
            clic = _clicavel(_barras_plan_real(g, campo, f"Plan × real por {'departamento' if visao == 'area' else 'dono'}"),
                             "obz_g_bar")
            if clic in set(g[campo]):
                _abrir(clic)
        with a2:
            if visao == "area":
                clic = _clicavel(_sunburst(b, "OBZ"), "obz_g_sun")
                if clic in set(g[campo]):
                    _abrir(clic)
            else:
                vb = _agrupar(b, "vbz")
                fig = go.Figure(go.Pie(labels=vb["vbz"], values=vb["fechamento"].abs(), hole=.55,
                                       marker=dict(colors=graficos.CATEGORICAS, line=dict(color="#fff", width=2))))
                graficos.mostrar(graficos._layout(fig, "Real por VBZ", 340), key="obz_g_pie")
        fig = _linha_mes(op, mes[:4])
        if fig is not None:
            graficos.mostrar(fig, key="obz_g_lin")
        vis = pd.DataFrame({"": [("🔴" if r["criticas"] else "🟡" if r["desfavoravel"] > 0 else "🟢")
                                 for _, r in g.iterrows()], ("Departamento" if visao == "area" else "Dono"): g[campo],
                            "Contas": g["contas"], "Plan": g["plan"].map(_m), "Real": g["real"].map(_m),
                            "Dispersão": g["disp"].map(_m), "Disp. %": g["disp_pct"].map(_p),
                            "Críticas": g["criticas"].astype(int)})
        t = b[["plan", "real", "disp"]].sum()
        vis.loc[len(vis)] = ["Σ", "TOTAL", b["conta"].nunique(), _m(t["plan"]), _m(t["real"]), _m(t["disp"]), _p(t["disp"] / abs(t["plan"]) * 100 if t["plan"] else None),
                             int(g["criticas"].sum())]
        ui.tabela(vis, baixar=f"obz_geral_{mes}")
        return

    sel = b[b[campo] == nivel[0]]
    if len(nivel) == 1:  # ---------------- Departamento / dono
        dono = sel["dono_area"].dropna().unique() if visao == "area" else []
        st.markdown(f"### {'🏢' if visao == 'area' else '👤'} {nivel[0]}"
                    + (f" · dono: **{', '.join(dono)}**" if len(dono) else ""))
        _kpis(sel, rotulo, "obz_dep")
        vb = _agrupar(sel, "vbz")
        _cartoes(vb, "vbz")
        ct = sel.groupby(["conta", "nome_conta"], as_index=False)[["plan", "real", "tend", "fechamento", "disp",
                                                                   "desfavoravel"]].sum()
        ct = ct.sort_values("desfavoravel", ascending=False).reset_index(drop=True)
        rot = (ct["conta"].astype(str) + " · " + ct["nome_conta"].fillna("").str[:26]).tolist()
        a1, a2 = st.columns([1.5, 1])
        with a1:
            top = ct.head(15)
            clic = _clicavel(_barras_plan_real(top, "conta", "Contas — plan × real (clique para abrir)",
                                               rot[:15]), "obz_d_bar")
            if clic in set(ct["conta"].astype(str)):
                _abrir(nivel[0], clic)
        with a2:
            fig = go.Figure(go.Pie(labels=vb["vbz"], values=vb["fechamento"].abs(), hole=.55,
                                   marker=dict(colors=[_cor(d, p) for d, p in zip(vb["desfavoravel"], vb["plan"])],
                                               line=dict(color="#fff", width=2))))
            graficos.mostrar(graficos._layout(fig, "Real por VBZ (cor = dispersão)", 360), key="obz_d_pie")
        if visao == "area":
            fig = _linha_mes(op, mes[:4], nivel[0])
            if fig is not None:
                graficos.mostrar(fig, key="obz_d_lin")
        _busca_conta(sel, nivel[0], None)
        ui.tabela(_tabela(sel), baixar=f"obz_{nivel[0]}_{mes}")
        return

    # ---------------- Conta
    conta = nivel[1]
    c = sel[sel["conta"].astype(str) == conta]
    nome = c["nome_conta"].iloc[0] if not c.empty else ""
    _busca_conta(sel, nivel[0], conta)
    st.markdown(f"### 🧾 {conta} · {nome}  \n{nivel[0]} · VBZ **{c['vbz'].iloc[0] if not c.empty else '—'}** · "
                f"responsável **{c['responsavel'].iloc[0] if not c.empty else '—'}**")
    _kpis(c, rotulo, "obz_ct")
    ano = mes[:4]
    pl = obz.plan_df(op, f"{ano}-01", f"{ano}-12")
    rl = obz.real_df(op, f"{ano}-01", f"{ano}-12")
    deps = set(c["depto"])
    pl = pl[(pl["conta"] == conta) & pl["depto"].isin(deps)].groupby("mes")["valor"].sum() if not pl.empty else pd.Series(dtype=float)
    rl = rl[(rl["conta"] == conta) & rl["depto"].isin(deps)].groupby("mes")["valor"].sum() if not rl.empty else pd.Series(dtype=float)
    ms = [f"{ano}-{m:02d}" for m in range(1, 13)]
    fig = go.Figure()
    fig.add_scatter(x=[obz.nome_mes(m)[:3] for m in ms], y=[pl.get(m) for m in ms], name="Plan",
                    mode="lines+markers", line=dict(color="#0B1F3A", dash="dot"))
    fig.add_bar(x=[obz.nome_mes(m)[:3] for m in ms], y=[rl.get(m) for m in ms], name="Real",
                marker_color=[(VERMELHO if (rl.get(m) or 0) > (pl.get(m) or 0) else VERDE) for m in ms])
    graficos.mostrar(graficos._layout(fig, f"{conta} · {nome} — plan × real {ano}", 320), key="obz_c_lin")
    ui.tabela(_tabela(c), baixar=f"obz_{conta}_{mes}")
    tema.secao("📒 Lançamentos (16.03.01)")
    lan = pd.concat([obz.lancamentos(op, m, conta) for m in lista], ignore_index=True)
    lan = lan[lan["depto"].isin(deps)] if not lan.empty else lan
    if lan.empty:
        st.info("Sem lançamentos detalhados no período (meses vindos do histórico da Base OBZ não têm o razão).")
    else:
        nd = obz.nomes_deptos()
        ui.tabela(pd.DataFrame({"Data": pd.to_datetime(lan["data"]).dt.strftime("%d/%m/%Y"),
                                "Depto": lan["depto"].map(lambda d: obz.rotulo_depto(d, nd)),
                                "Histórico": lan["historico"], "Débito (H)": lan["debito"].map(_m),
                                "Crédito (I)": lan["credito"].map(_m)}), baixar=f"lancamentos_{conta}")
