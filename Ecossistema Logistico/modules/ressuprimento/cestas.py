"""Ressuprimento › Acompanhamento mensal por cesta (META x REAL x TENDÊNCIA)."""
import pandas as pd
import streamlit as st

from core import graficos, tema, tempo, ui
from services import ressuprimento_service as svc

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]
_COR = {"bom": "🟢", "atencao": "🟡", "serio": "🟠", "critico": "🔴", "neutro": "⚪"}


def links_estaticos() -> None:
    from repositories import operacoes_repo

    with st.expander("🔗 Links de visualização direta (somente leitura, sem login)"):
        st.caption("Compartilhe com quem só precisa acompanhar. A página abre direto no acompanhamento da filial.")
        cols = st.columns(4)
        for i, op in enumerate(operacoes_repo.listar(apenas_ativas=True)):
            cols[i % 4].link_button(f"🔗 {op['nome']}", f"?visualizacao=ressuprimento&op={op['id']}", **ui.LARGURA)


def _legivel(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela no formato do relatório: HL inteiro com ponto de milhar (1.307) e '—' quando não há meta."""
    if df.empty:
        return pd.DataFrame(columns=["", "Indicador", "Meta (HL)", "Real (HL)", "Tendência (HL)", "Ating. real",
                                     "Ating. tendência", "Pendência (HL)"])
    tem_meta = df["meta"] > 0
    num = ui.numero  # ponto de milhar a partir de mil: 5.025 · 189.312
    real = df["real"].map(num)
    return pd.DataFrame({
        "": df["ating_tend"].map(lambda p: _COR[tema.status_atingimento(p if pd.notna(p) else None)]),
        "Indicador": df["indicador"],
        "Meta (HL)": [num(m) if t else "—" for m, t in zip(df["meta"], tem_meta)],
        "Real (HL)": real,
        "Tendência (HL)": df["tendencia"].map(num),
        "Ating. real": [ui.pct(a) if t and pd.notna(a) else "—" for a, t in zip(df["ating_real"], tem_meta)],
        "Ating. tendência": [float(a) if t and pd.notna(a) else None for a, t in zip(df["ating_tend"], tem_meta)],
        "Pendência (HL)": [num(p) if t else "—" for p, t in zip(df["pendencia"], tem_meta)],
    }).reset_index(drop=True)


_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _farol(p) -> str:
    return _COR[tema.status_atingimento(p if p is not None and pd.notna(p) else None)]


def acompanhamento_dia(operacao_id: int, mes_ano: str, chave: str = "ces") -> None:
    """📅 Cesta diária: o dia escolhido (real × meta do dia e acumulado) + a grade dia × cesta."""
    tema.secao("📅 Acompanhamento diário da cesta",
               "Meta do dia = meta do mês ÷ dias de puxada (dias marcados “sem puxada” em 📅 Gestão do dia não "
               "têm meta). O acumulado compara o realizado até o dia com a meta proporcional até o dia.")
    d = svc.acompanhamento_diario(operacao_id, mes_ano)
    if d.empty:
        st.info("Ainda não há carregamento lançado neste mês.")
        return
    datas = sorted(d.loc[d["dia"] > 0, "data"].unique().tolist()) or sorted(d["data"].unique().tolist())
    dia = st.selectbox("Dia", datas[::-1], format_func=lambda x: f"{x:%d/%m/%Y} ({_SEMANA[x.weekday()]})",
                       key=f"{chave}_dia_sel")
    hoje = d[d["data"] == dia]
    tot = hoje[hoje["cesta"] == "TOTAL"].iloc[0]
    num = ui.numero
    hl = lambda v: f"{num(v)} HL"  # noqa: E731
    tem_meta = bool(tot["meta_acum"])
    tema.kpis([
        {"titulo": f"Real do dia · {dia:%d/%m}", "valor": hl(tot["dia"]), "icone": "🍺", "status": "info",
         "detalhe": "Cerveja + Nab" + ("" if tot["puxada"] else " · dia sem puxada")},
        {"titulo": "Meta do dia", "valor": hl(tot["meta_dia"]) if tot["meta_dia"] else "—", "icone": "🎯",
         "status": tema.status_atingimento(tot["ating_dia"]) if tot["meta_dia"] else "neutro",
         "detalhe": f"{ui.pct(tot['ating_dia'])} atingido" if tot["meta_dia"] else "sem meta neste dia"},
        {"titulo": "Acumulado no mês", "valor": hl(tot["acum"]), "icone": "📈",
         "status": tema.status_atingimento(tot["ating_acum"]) if tem_meta else "neutro",
         "detalhe": f"{ui.pct(tot['ating_acum'])} da meta até o dia" if tem_meta else "defina as metas"},
        {"titulo": "Diferença acumulada", "valor": hl(tot["dif_acum"]) if tem_meta else "—", "icone": "⚖️",
         "status": ("bom" if tot["dif_acum"] >= 0 else "critico") if tem_meta else "neutro",
         "detalhe": "acima da meta proporcional" if tem_meta and tot["dif_acum"] >= 0 else
                    "abaixo da meta proporcional" if tem_meta else ""},
    ], key=f"kp_{chave}_dia")
    vis = pd.DataFrame({
        "": hoje["ating_acum"].map(_farol),
        "Indicador": hoje["indicador"],
        "Meta do dia": [num(v) if v else "—" for v in hoje["meta_dia"]],
        "Real do dia": hoje["dia"].map(num),
        "Ating. dia": [float(v) if v is not None and pd.notna(v) else None for v in hoje["ating_dia"]],
        "Acumulado": hoje["acum"].map(num),
        "Meta acumulada": [num(v) if v else "—" for v in hoje["meta_acum"]],
        "Ating. acumulado": [float(v) if v is not None and pd.notna(v) else None for v in hoje["ating_acum"]],
        "Diferença": [num(v) if v is not None and pd.notna(v) else "—" for v in hoje["dif_acum"]],
    }).reset_index(drop=True)
    barra = lambda t: st.column_config.ProgressColumn(t, format="%.0f%%", min_value=0, max_value=120)  # noqa: E731
    ui.tabela(vis, column_config={"": st.column_config.TextColumn("", width="small"),
                                  "Ating. dia": barra("Ating. dia"), "Ating. acumulado": barra("Ating. acumulado")})

    with st.expander("🗓️ Grade do mês — % da meta do dia, por cesta", expanded=False):
        grade = d.copy()
        def _txt(r) -> str:
            if not r["puxada"]:
                return f"{num(r['dia'])} HL · sem puxada" if r["dia"] else "sem puxada"
            if not r["meta_dia"]:
                return f"{num(r['dia'])} HL"
            return f"{_farol(r['ating_dia'])} {r['ating_dia']:.0f}%"

        grade["txt"] = grade.apply(_txt, axis=1)
        ordem = grade["indicador"].drop_duplicates().tolist()
        piv = grade.pivot_table(index="data", columns="indicador", values="txt", aggfunc="first")[ordem]
        piv.index = [f"{x:%d/%m} ({_SEMANA[x.weekday()]})" for x in piv.index]
        ui.tabela(piv.reset_index(names="Dia"))
        st.caption("🟢 ≥ 100% da meta do dia · 🟡 90–99% · 🟠 75–89% · 🔴 abaixo de 75%")
    ui.downloads(d.drop(columns=["cesta"]), f"cesta_diaria_{mes_ano}", key=f"dl_{chave}_dia")


_CSS_GRADE = """
<style>
.vc-grade { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:.7rem; margin:.4rem 0 1rem; }
.vc-card { background:#fff; border:1px solid #dfe5ee; border-radius:14px; padding:.75rem .9rem; border-top:5px solid var(--c); }
.vc-card .t { font-size:.74rem; color:#52514e; font-weight:700; text-transform:uppercase; letter-spacing:.02em;
    min-height:2.1em; }
.vc-card .v { font-size:1.45rem; font-weight:900; color:#0B1F3A; line-height:1.1; margin-top:.2rem; }
.vc-card .v small { font-size:.8rem; color:#6b6a65; font-weight:600; }
.vc-card .m { font-size:.8rem; color:#52514e; margin-top:.15rem; }
.vc-bar { height:9px; background:#eef1f6; border-radius:6px; margin:.5rem 0 .25rem; overflow:hidden; }
.vc-bar span { display:block; height:100%; background:var(--c); border-radius:6px; }
.vc-card .p { display:flex; justify-content:space-between; font-size:.78rem; font-weight:700; color:var(--c); }
</style>
"""


def grade_cestas(df: pd.DataFrame) -> None:
    """Um cartão por cesta: real, meta, barra da tendência e pendência — leitura rápida."""
    import html

    cards = []
    for _, r in df.iterrows():
        tem = r["meta"] > 0
        p = float(r["ating_tend"]) if tem and pd.notna(r["ating_tend"]) else None
        cor = tema.STATUS[tema.status_atingimento(p)][0] if p is not None else "#9aa3b2"
        cards.append(
            f'<div class="vc-card" style="--c:{cor}"><div class="t">{html.escape(str(r["indicador"]))}</div>'
            f'<div class="v">{ui.numero(r["real"])} <small>HL</small></div>'
            f'<div class="m">meta {ui.numero(r["meta"]) if tem else "—"} · tendência {ui.numero(r["tendencia"])}</div>'
            f'<div class="vc-bar"><span style="width:{min(p or 0, 100):.0f}%"></span></div>'
            f'<div class="p"><span>{ui.pct(p) if p is not None else "sem meta"}</span>'
            f'<span>{(ui.numero(r["pendencia"]) + " HL") if tem else ""}</span></div></div>')
    st.markdown(_CSS_GRADE + '<div class="vc-grade">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def acompanhamento(operacao_id: int, chave: str = "ces", com_graficos: bool = True, grade: bool = False) -> None:
    hoje = tempo.hoje()
    c1, c2 = st.columns([1, 3])
    ano = c1.number_input("Ano", min_value=2024, max_value=2035, value=hoje.year, key=f"{chave}_ano")
    meses = c2.multiselect("Meses (vazio = ano inteiro)", list(range(1, 13)), default=[hoje.month],
                           format_func=lambda m: MESES[m - 1], key=f"{chave}_meses")
    df = svc.acompanhamento(operacao_id, int(ano), meses)
    tot = df[df["cesta"] == "TOTAL"].iloc[0]
    det = _legivel(df[df["cesta"] != "TOTAL"])
    neg = _legivel(df[(df["cesta"] != "TOTAL") & (df["meta"] > 0) & (df["pendencia"] < 0)].sort_values("pendencia"))
    preench, periodo = df.attrs.get("dias_preenchidos", 0), df.attrs.get("dias_periodo", 0)
    hl = lambda v: f"{ui.numero(v)} HL"  # noqa: E731 — número inteiro como no relatório (1.307 = mil trezentos e sete)
    tema.kpis([
        {"titulo": "Total Cerveja + Nab — real", "valor": hl(tot["real"]), "icone": "🍺",
         "status": "info", "detalhe": f"{preench} dia(s) com dado no período", "dados": det},
        {"titulo": "Meta do período", "valor": hl(tot["meta"]) if tot["meta"] else "Sem meta",
         "icone": "🎯", "status": "info" if tot["meta"] else "neutro", "dados": det},
        {"titulo": "Tendência de fechamento", "valor": hl(tot["tendencia"]), "icone": "🔮",
         "detalhe": f"{ui.pct(tot['ating_tend'])} da meta" if tot["meta"] else "defina as metas",
         "status": tema.status_atingimento(tot["ating_tend"] if tot["meta"] else None), "dados": det},
        {"titulo": "Pendência (real − meta)", "valor": hl(tot["pendencia"]) if tot["meta"] else "—", "icone": "⚖️",
         "status": ("bom" if tot["pendencia"] >= 0 else "critico") if tot["meta"] else "neutro",
         "detalhe": "cestas abaixo da meta: clique" if len(neg) else "", "dados": neg},
    ], key=f"kp_{chave}")
    if grade:
        grade_cestas(df)
    ui.tabela(_legivel(df), column_config={
        "": st.column_config.TextColumn("", width="small"),
        "Ating. tendência": st.column_config.ProgressColumn("Ating. tendência", format="%.0f%%", min_value=0,
                                                             max_value=120)})
    st.caption("🟢 tendência ≥ 100% da meta · 🟡 90–99% · 🟠 75–89% · 🔴 abaixo de 75%")
    ui.downloads(df.drop(columns=["cesta"]), f"acompanhamento_{ano}", key=f"dl_{chave}")
    if len(meses) == 1:
        acompanhamento_dia(operacao_id, f"{int(ano)}-{meses[0]:02d}", chave)

    if not com_graficos:
        return
    com_meta = df[(df["meta"] > 0) & (df["cesta"] != "TOTAL")].sort_values("ating_tend")
    g1, g2 = st.columns(2)
    with g1:
        if not com_meta.empty:
            cores = [tema.STATUS[tema.status_atingimento(p)][0] for p in com_meta["ating_tend"]]
            graficos.mostrar(graficos.barras_h(com_meta["indicador"], com_meta["ating_tend"].fillna(0), cores=cores,
                                               sufixo="%", titulo="Tendência de atingimento por cesta"),
                             key=f"g_{chave}_ating", detalhe=(det, "Indicador"), titulo="Cesta")
        else:
            st.info("Cadastre as metas em **🎯 Metas Mensais** para ver o atingimento.")
    with g2:
        if len(meses) == 1:
            mes_ano = f"{int(ano)}-{meses[0]:02d}"
            opcoes = df[df["cesta"] != "TOTAL"]["cesta"].tolist()
            if opcoes:
                cesta = st.selectbox("Evolução da cesta", opcoes, format_func=svc.nome_cesta, key=f"{chave}_cesta")
                evo = svc.evolucao_diaria(operacao_id, mes_ano, cesta)
                if not evo.empty:
                    graficos.mostrar(graficos.linhas(evo["data"], {"Real acumulado": evo["real_acum"],
                                                                   "Meta proporcional": evo["meta_acum"]},
                                                     titulo=f"{svc.nome_cesta(cesta)} — acumulado no mês", sufixo=" HL",
                                                     tracejadas=("Meta proporcional",)), key=f"g_{chave}_evo")


def render(usuario: dict, operacao_id: int) -> None:
    links_estaticos()
    acompanhamento(ui.visao_acompanhamento(usuario, operacao_id, "cestas"))
