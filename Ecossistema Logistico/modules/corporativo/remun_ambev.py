"""Gestão Corporativa › 🚚 Logística › 💰 Remuneração Ambev.

🚚 Carreto (entrega): caixas entregues (03.02.37 vendas) × carreto (coluna P da tabela Ambev) vigente no dia.
🏭 Frete (puxada): caixas compradas de cada fábrica (03.02.37 compra, coluna M) × frete puxada (coluna N) da fábrica.
⚖️ Comparação OBZ: remuneração × gasto real dos departamentos (entrega / puxada).
📥 Tabelas Ambev: sobe um arquivo por fábrica (unidade fornecedora) e liga a unidade à fábrica do 03.02.37.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import graficos, tema, ui
from repositories import operacoes_repo
from services import remun_ambev_service as rs
from services.erros import RegraNegocioError

_TELAS = {"carreto": "🚚 Carreto", "frete": "🏭 Frete", "obz": "⚖️ Comparação OBZ", "tabelas": "📥 Tabelas Ambev"}
VERDE, VERMELHO, AZUL, LARANJA, CINZA = "#1baf7a", "#e34948", "#2a78d6", "#eda100", "#9aa4b2"


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _n(v, c=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, c)


def _t(v) -> str:  # tarifa R$/cx
    return "—" if v is None or pd.isna(v) else "R$ " + ui.numero(v, 4)


def _div(a, b):
    return a / b if b else None


def render(usuario: dict, operacao_id: int) -> None:
    tema.secao("💰 Remuneração Ambev",
               "Quanto a Ambev paga pela logística: carreto na entrega (coluna P) e frete da puxada por fábrica "
               "(coluna N), comparado com o OBZ.")
    tela = ui._escolha("ra_tela", list(_TELAS), "carreto", pills=True, formatar=_TELAS.get)
    if tela == "tabelas":
        _tabelas(usuario, operacao_id)
        return
    if rs.unidades(operacao_id).empty:
        st.info("Ainda não há tabela da Ambev. Suba o relatório de remuneração de cada fábrica em **📥 Tabelas Ambev**.")
        return
    meses = rs.meses_disponiveis(operacao_id)
    if not meses:
        st.info("Suba o 03.02.37 de vendas e de compra em 📥 Relatórios para calcular a remuneração.")
        return
    c1, c2, _ = st.columns([1, 1, 2])
    ate = c2.selectbox("Até", meses, key="ra_ate", format_func=ui.nome_mes)
    opc = [m for m in meses if m <= ate]
    de = c1.selectbox("De", opc, key="ra_de", format_func=ui.nome_mes, index=0)
    if de > ate:
        de = ate
    ini, fim = f"{de}-01", pd.Period(ate).end_time.strftime("%Y-%m-%d")
    lista = [m for m in meses if de <= m <= ate]
    origem = {"carreto": "venda", "frete": "compra"}.get(tela)
    faltam = []
    for o in ([origem] if origem else ["venda", "compra"]):
        faltam += [f"{ui.nome_mes(m)} ({'vendas' if o == 'venda' else 'compra'})"
                   for m in rs.sem_base_dia(operacao_id, o, ini, fim)]
    if faltam:
        st.warning("Para calcular pelo produto e dia, suba de novo o 03.02.37 destes meses em 📥 Relatórios: "
                   + ", ".join(faltam) + ".")
    {"carreto": lambda: _carreto(operacao_id, ini, fim),
     "frete": lambda: _frete(operacao_id, ini, fim),
     "obz": lambda: _obz(usuario, operacao_id, lista)}[tela]()


# --- 🚚 Carreto --------------------------------------------------------------------------------------------------------
def _carreto(op: int, ini: str, fim: str) -> None:
    c = rs.carreto(op, ini, fim)
    if c.empty:
        st.info("Nenhuma entrega no período (03.02.37 vendas, operações de venda + bonificação).")
        return
    com = c[c["tarifa"].notna()]
    sem = c[c["tarifa"].isna()]
    tot, cx, hl = c["valor"].sum(), com["qtde"].sum(), com["hl"].sum()
    c["qtde_com"] = c["qtde"].where(c["tarifa"].notna(), 0.0)
    por_prod = (c.groupby("produto", as_index=False)
                 .agg(descricao=("descricao", "first"), qtde=("qtde", "sum"), hl=("hl", "sum"),
                      valor=("valor", "sum"), qtde_com=("qtde_com", "sum"), unidades=("unidades", _juntar),
                      tem=("tarifa", lambda s: s.notna().any())))
    por_prod["tarifa"] = [_div(v, q) if t else None for v, q, t in
                          zip(por_prod["valor"], por_prod["qtde_com"], por_prod["tem"])]
    por_prod = por_prod.sort_values("valor", ascending=False)
    sem_p = por_prod[~por_prod["tem"]]
    tema.kpis([
        {"titulo": "Remuneração carreto", "valor": _m(tot), "icone": "💰", "status": "bom",
         "detalhe": f"{c['data'].nunique()} dia(s) de entrega"},
        {"titulo": "Caixas entregues (com tarifa)", "valor": _n(cx), "icone": "📦", "status": "info",
         "detalhe": f"{_n(hl, 1)} HL"},
        {"titulo": "Carreto médio", "valor": _t(_div(tot, cx)) + "/cx", "icone": "🧮", "status": "info",
         "detalhe": f"{_m(_div(tot, hl))} por HL"},
        {"titulo": "Produtos sem tarifa", "valor": _n(len(sem_p)), "icone": "⚠️",
         "status": "atencao" if len(sem_p) else "bom", "detalhe": f"{_n(sem['qtde'].sum())} cx sem remuneração",
         "dados": _tab_prod(sem_p) if len(sem_p) else None},
    ], key="kp_ra_car")
    dia = c.groupby("data", as_index=False)[["valor", "qtde"]].sum()
    fig = go.Figure(go.Bar(x=pd.to_datetime(dia["data"]).dt.strftime("%d/%m"), y=dia["valor"], marker_color=VERDE,
                           text=[ui.compacto(v) for v in dia["valor"]], textposition="outside",
                           customdata=dia["qtde"], hovertemplate="%{x}<br>R$ %{y:,.2f}<br>%{customdata:,.0f} cx"
                                                                 "<extra></extra>"))
    graficos.mostrar(graficos._layout(fig, "Carreto por dia (R$)", 320, legenda=False), key="ra_g_car_dia")
    if c["fora_vig"].any():
        st.caption("ℹ️ Alguns dias usaram a última tarifa conhecida (a vigência da tabela já tinha terminado) — suba a "
                   "tabela mais nova da Ambev.")
    tema.secao("📦 Carreto por produto", "Caixas entregues × carreto da Ambev (R$/cx) vigente em cada dia.")
    ui.tabela(_tab_prod(por_prod[por_prod["tem"]]), baixar="remun_carreto_produto")
    if len(sem_p):
        with st.expander(f"⚠️ {len(sem_p)} produto(s) entregues sem tarifa de carreto"):
            st.caption("Produto que não está em nenhuma tabela da Ambev subida (ex.: não Ambev, ou fábrica que falta).")
            ui.tabela(_tab_prod(sem_p), baixar="remun_carreto_sem_tarifa")


def _juntar(s) -> str:
    return ", ".join(sorted({x for v in s for x in str(v).split(", ") if x and x != "nan"}))


def _tab_prod(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"Código": df["produto"], "Produto": df["descricao"], "Caixas": df["qtde"].map(_n),
                        "HL": df["hl"].map(lambda v: _n(v, 1)), "R$/cx (médio)": df["tarifa"].map(_t),
                        "Remuneração": df["valor"].map(_m)})
    if "unidades" in df:
        out["Tabela (unidade Ambev)"] = df["unidades"]
    return out.reset_index(drop=True)


# --- 🏭 Frete ----------------------------------------------------------------------------------------------------------
def _frete(op: int, ini: str, fim: str) -> None:
    f = rs.frete(op, ini, fim)
    if f.empty:
        st.info("Nenhuma compra no período (03.02.37 compra, operações de compra).")
        return
    nomes = rs.nomes_fornecedores(op)
    f["fab"] = [f"{c} · {nomes.get(c, '') or 'Fábrica'}" for c in f["fornecedor"]]
    fab = (f.groupby(["fab", "fornecedor"], as_index=False)
            .agg(unidade=("unidade_nome", "first"), unidade_cod=("unidade_cod", "first"), qtde=("qtde", "sum"),
                 hl=("hl", "sum"), valor=("valor", "sum")))
    fab["tarifa"] = [_div(v, q) if u else None for v, q, u in zip(fab["valor"], fab["qtde"], fab["unidade_cod"])]
    fab = fab.sort_values("valor", ascending=False)
    ok = fab[fab["unidade_cod"] != ""]
    sem = fab[fab["unidade_cod"] == ""]
    tot = f["valor"].sum()
    cx = ok["qtde"].sum()
    tema.kpis([
        {"titulo": "Remuneração frete", "valor": _m(tot), "icone": "💰", "status": "bom",
         "detalhe": f"{len(ok)} fábrica(s) com tabela"},
        {"titulo": "Caixas puxadas (com tabela)", "valor": _n(cx), "icone": "🏭", "status": "info",
         "detalhe": f"{_n(ok['hl'].sum(), 1)} HL"},
        {"titulo": "Frete médio", "valor": _t(_div(tot, cx)) + "/cx", "icone": "🧮", "status": "info",
         "detalhe": f"{_m(_div(tot, ok['hl'].sum()))} por HL"},
        {"titulo": "Fábricas sem tabela", "valor": _n(len(sem)), "icone": "⚠️",
         "status": "atencao" if len(sem) else "bom", "detalhe": f"{_n(sem['qtde'].sum())} cx sem remuneração",
         "dados": _tab_fab(sem) if len(sem) else None},
    ], key="kp_ra_fre")
    if not ok.empty:
        g = ok.iloc[::-1]
        fig = go.Figure(go.Bar(y=g["fab"].str[:34], x=g["valor"], orientation="h", marker_color=AZUL,
                               text=[f"{ui.compacto(v)} · {_t(t)}/cx" for v, t in zip(g["valor"], g["tarifa"])],
                               textposition="outside"))
        graficos.mostrar(graficos._layout(fig, "Frete por fábrica (R$)", max(260, 40 * len(g) + 90), legenda=False),
                         key="ra_g_fre_fab")
    tema.secao("🏭 Remuneração por fábrica", "Caixas compradas da fábrica (coluna M do 03.02.37) × frete puxada.")
    ui.tabela(_tab_fab(fab), baixar="remun_frete_fabrica")
    if len(sem):
        st.caption("⚠️ Fábrica sem tabela: suba o arquivo da Ambev dessa unidade e ligue em 📥 Tabelas Ambev.")
    tema.secao("📦 Por fábrica e produto")
    opcs = ok["fab"].tolist() or fab["fab"].tolist()
    esc = st.selectbox("Fábrica", opcs, key="ra_fre_fab")
    fp = f[f["fab"] == esc]
    pp = (fp.groupby("produto", as_index=False)
            .agg(descricao=("descricao", "first"), qtde=("qtde", "sum"), hl=("hl", "sum"), valor=("valor", "sum"),
                 tem=("tarifa", lambda s: s.notna().any())))
    pp["tarifa"] = [_div(v, q) if t else None for v, q, t in zip(pp["valor"], pp["qtde"], pp["tem"])]
    ui.tabela(_tab_prod(pp.sort_values("valor", ascending=False)), baixar="remun_frete_produto")


def _tab_fab(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Fábrica (03.02.37)": df["fab"],
                         "Tabela Ambev": [f"{c} · {n}" if c else "— sem tabela" for c, n in
                                          zip(df["unidade_cod"], df["unidade"])],
                         "Caixas": df["qtde"].map(_n), "HL": df["hl"].map(lambda v: _n(v, 1)),
                         "R$/cx (médio)": df["tarifa"].map(_t), "Remuneração": df["valor"].map(_m)}).reset_index(
        drop=True)


# --- ⚖️ Comparação OBZ -------------------------------------------------------------------------------------------------
def _obz(usuario: dict, op: int, meses: list[str]) -> None:
    r = rs.comparar_obz(op, meses)
    m, dep, cfg = r["mensal"], r["deptos"], r["cfg"]
    from services import obz_service as obz

    nomes = obz.nomes_deptos()
    ligados = {t: ", ".join(obz.rotulo_depto(d, nomes) for d in cfg[f"deptos_{t}"]) or "nenhum" for t in rs.TIPOS}
    cards = []
    for t in rs.TIPOS:
        x = m[m["tipo"] == t]
        rem, real = x["remuneracao"].sum(), x["real"].sum()
        res = rem - real
        cards.append({"titulo": f"{'Carreto' if t == 'carreto' else 'Frete'} × OBZ", "valor": _m(res), "icone":
                      "🚚" if t == "carreto" else "🏭", "status": "bom" if res >= 0 else "critico",
                      "detalhe": f"recebe {ui.compacto(rem)} · gasta {ui.compacto(real)}"
                                 + (f" · cobre {ui.pct(rem / real * 100, 0)}" if real else "")})
    rem_t, real_t = m["remuneracao"].sum(), m["real"].sum()
    cards.append({"titulo": "Resultado logístico", "valor": _m(rem_t - real_t), "icone": "⚖️",
                  "status": "bom" if rem_t >= real_t else "critico",
                  "detalhe": f"remuneração {ui.compacto(rem_t)} − gasto OBZ {ui.compacto(real_t)}"})
    tema.kpis(cards, key="kp_ra_obz")
    st.caption(f"🚚 Carreto comparado com: **{ligados['carreto']}** · 🏭 Frete comparado com: **{ligados['frete']}** "
               "— ajuste em ⚙️ abaixo.")
    if real_t == 0:
        st.info("Sem gasto real do OBZ nos departamentos ligados neste período — confira o ⚙️ (departamentos) ou suba "
                "o realizado do OBZ.")
    fig = go.Figure()
    for t, cor_r, cor_g in (("carreto", VERDE, VERMELHO), ("frete", AZUL, LARANJA)):
        x = m[m["tipo"] == t]
        rot = "Carreto" if t == "carreto" else "Frete"
        meses_x = [ui.nome_mes(v) for v in x["mes"]]
        fig.add_bar(x=meses_x, y=x["remuneracao"], name=f"{rot} Ambev", marker_color=cor_r, offsetgroup=t + "r")
        fig.add_bar(x=meses_x, y=x["real"], name=f"Gasto OBZ ({rot.lower()})", marker_color=cor_g,
                    offsetgroup=t + "g", opacity=0.75)
    fig.update_layout(barmode="group")
    graficos.mostrar(graficos._layout(fig, "Remuneração Ambev × gasto real OBZ por mês", 340), key="ra_g_obz")
    tema.secao("📅 Mês a mês")
    vis = pd.DataFrame({
        "Mês": m["mes"].map(ui.nome_mes), "Tipo": m["tipo"].map(rs.TIPOS),
        "Caixas": m["caixas"].map(_n), "Remuneração Ambev": m["remuneracao"].map(_m),
        "R$/cx Ambev": [_t(_div(a, b)) for a, b in zip(m["remuneracao"], m["caixas"])],
        "Gasto real OBZ": m["real"].map(_m), "R$/cx gasto": [_t(_div(a, b)) for a, b in zip(m["real"], m["caixas"])],
        "Plan OBZ": m["plan"].map(_m), "Resultado": m["resultado"].map(_m),
        "Cobertura": m["cobertura"].map(lambda v: "—" if pd.isna(v) else ui.pct(v, 0)),
        "": ["🟢" if v >= 0 else "🔴" for v in m["resultado"]]})
    ui.tabela(vis, baixar="remun_obz_mensal")
    tema.secao("🏢 OBZ por departamento",
               "Gasto real e plan de cada departamento no período; a remuneração entra nos departamentos ligados "
               "(dividida pelo peso do gasto).")
    if dep.empty:
        st.info("Sem OBZ (real/plan) no período.")
    else:
        so = st.toggle("Só os departamentos ligados à remuneração", value=False, key="ra_obz_so")
        d = dep[dep["ligado"] != ""] if so else dep
        ui.tabela(pd.DataFrame({
            "Departamento": [obz.rotulo_depto(c, nomes) for c in d["depto"]],
            "Ligado a": d["ligado"].map(lambda v: v or "—"), "Real": d["real"].map(_m), "Plan": d["plan"].map(_m),
            "Remuneração Ambev": [_m(v) if lg else "—" for v, lg in zip(d["remuneracao"], d["ligado"])],
            "Resultado": [_m(v - g) if lg else "—" for v, g, lg in zip(d["remuneracao"], d["real"], d["ligado"])]}),
            baixar="remun_obz_deptos")
    _config(usuario, op, cfg, nomes)


def _config(usuario: dict, op: int, cfg: dict, nomes: dict) -> None:
    from services import faturamento_service as fs
    from services import obz_service as obz

    with st.expander("⚙️ Departamentos e operações usados na comparação"):
        if operacoes_repo.e_consolidada(op):
            st.info("Escolha uma revenda no menu para ajustar.")
            return
        dps = obz.departamentos()["codigo"].tolist()
        from database.connection import query_df

        on = query_df("SELECT codigo, nome FROM operacoes_fiscais")
        ops_nomes = dict(zip(on["codigo"].astype(str), on["nome"].fillna("")))
        ops_base = sorted({*cfg["ops_carreto"], *cfg["ops_frete"], *fs.operacoes_do_setor("hl_venda"),
                           *fs.operacoes_do_setor("hl_compra")}, key=lambda x: (len(x), x))
        with st.form("ra_cfg"):
            c1, c2 = st.columns(2)
            dc = c1.multiselect("🚚 Carreto × departamentos (entrega)", dps,
                                default=[d for d in cfg["deptos_carreto"] if d in dps],
                                format_func=lambda c: obz.rotulo_depto(c, nomes))
            df_ = c2.multiselect("🏭 Frete × departamentos (puxada)", dps,
                                 default=[d for d in cfg["deptos_frete"] if d in dps],
                                 format_func=lambda c: obz.rotulo_depto(c, nomes))
            oc = c1.multiselect("Operações de entrega (03.02.37 vendas)", ops_base, default=cfg["ops_carreto"],
                                format_func=lambda c: f"{c} · {ops_nomes.get(c, '')}".strip(" ·"))
            of = c2.multiselect("Operações de compra (03.02.37 compra)", ops_base, default=cfg["ops_frete"],
                                format_func=lambda c: f"{c} · {ops_nomes.get(c, '')}".strip(" ·"))
            if st.form_submit_button("💾 Salvar", type="primary"):
                ui.acao(rs.salvar_config, op, {"deptos_carreto": dc, "deptos_frete": df_, "ops_carreto": oc,
                                               "ops_frete": of}, sucesso="Configuração salva.")


# --- 📥 Tabelas Ambev --------------------------------------------------------------------------------------------------
def _tabelas(usuario: dict, op: int) -> None:
    consolidada = operacoes_repo.e_consolidada(op)
    if consolidada:
        st.info("Escolha uma revenda no menu para subir as tabelas da Ambev.")
    else:
        tema.secao("📤 Subir tabela de remuneração da Ambev",
                   "Um arquivo por fábrica (unidade fornecedora) — pode escolher vários de uma vez. Coluna N = frete "
                   "puxada, coluna P = carreto, por caixa e vigência.")
        v = st.session_state.get("ra_up_v", 0)
        arqs = st.file_uploader("Tabelas Ambev (CSV ou ZIP)", type=["csv", "txt", "zip"], accept_multiple_files=True,
                                key=f"ra_up_{v}", label_visibility="collapsed")
        arqs = [a for a in (arqs or []) if a is not None]
        if arqs and st.button("Gravar" if len(arqs) == 1 else f"Gravar as {len(arqs)} tabelas", type="primary",
                              key="ra_gravar"):
            erros = []
            for a in arqs:
                try:
                    r = rs.importar(a.getvalue(), a.name, op, usuario.get("nome", ""))
                except RegraNegocioError as e:
                    erros.append(f"{a.name}: {e}")
                except Exception as e:  # noqa: BLE001
                    erros.append(f"{a.name}: erro inesperado ({e}). Confira se é o relatório da Ambev em CSV.")
                else:
                    ui.avisar(f"{r['unidade']}: {r['produtos']} produtos, {r['vigencias']} vigências "
                              f"({pd.to_datetime(r['de']).strftime('%d/%m')} a "
                              f"{pd.to_datetime(r['ate']).strftime('%d/%m/%Y')})"
                              + ("" if r["fornecedor"] else " — ligue a fábrica abaixo."))
            for e in erros:
                st.error(e)
            if not erros:
                st.session_state["ra_up_v"] = v + 1
                st.rerun()
    un = rs.unidades(op)
    if un.empty:
        st.caption("Nenhuma tabela subida ainda.")
        return
    tema.secao("🔗 Unidades Ambev × fábrica do 03.02.37",
               "Ligue cada unidade da Ambev à fábrica da coluna M do 03.02.37 compra — é assim que o frete sabe de "
               "qual fábrica veio cada caixa.")
    mp = rs.mapas(op)
    forn = rs.fornecedores(op)
    nomes_f = dict(zip(forn["fornecedor"], forn["nome"]))
    opcs = [""] + forn["fornecedor"].tolist()
    for _, u in un.iterrows():
        o, cod = int(u["operacao_id"]), str(u["unidade_cod"])
        atual = mp.get((o, cod), "")
        c1, c2, c3, c4 = st.columns([2.2, 2.6, 1.4, 0.8])
        c1.markdown(f"**{cod} · {u['unidade_nome']}**  \n{int(u['produtos'])} produtos · vigências de "
                    f"{pd.to_datetime(u['de']).strftime('%d/%m/%Y')} a {pd.to_datetime(u['ate']).strftime('%d/%m/%Y')}")
        if consolidada:
            c2.markdown(f"Fábrica: **{atual} · {nomes_f.get(atual, '')}**" if atual else "Fábrica: —")
            continue
        lista = opcs if atual in opcs else opcs + [atual]
        esc = c2.selectbox("Fábrica do 03.02.37", lista, index=lista.index(atual), key=f"ra_map_{o}_{cod}",
                           format_func=lambda c: "— escolha —" if not c else f"{c} · {nomes_f.get(c, '') or 'Fábrica'}",
                           label_visibility="collapsed")
        if esc != atual:
            rs.salvar_mapa(o, cod, esc or None)
            ui.salvo_automatico("Fábrica ligada.")
        c3.caption(f"subida em {pd.to_datetime(u['importado_em']).strftime('%d/%m %H:%M') if u['importado_em'] else '—'}"
                   f"  \npor {u['importado_por'] or '—'}")
        from core.auth import e_master

        if e_master(usuario) and c4.button("🗑️", key=f"ra_del_{o}_{cod}", help="Excluir a tabela desta unidade"):
            ui.acao(rs.excluir_unidade, o, cod, sucesso="Tabela excluída.")
    if forn.empty:
        st.caption("ℹ️ A lista de fábricas vem do 03.02.37 compra — suba ele em 📥 Relatórios.")
    tema.secao("🔎 Ver tabela")
    esc = st.selectbox("Unidade", un["unidade_cod"].astype(str).unique().tolist(), key="ra_ver_un",
                       format_func=lambda c: f"{c} · {un.set_index('unidade_cod').loc[c, 'unidade_nome']}"
                       if c in set(un["unidade_cod"]) else c)
    t = rs.tabela(op, esc)
    so_vig = st.toggle("Só a vigência atual de cada produto", value=True, key="ra_ver_vig")
    if so_vig and not t.empty:
        t = t.sort_values("ini").groupby("produto", as_index=False).tail(1)
    ui.tabela(pd.DataFrame({
        "Código": t["produto"], "Produto": t["descricao"],
        "Início": pd.to_datetime(t["ini"]).dt.strftime("%d/%m/%Y"),
        "Fim": [pd.to_datetime(x).strftime("%d/%m/%Y") if isinstance(x, str) and x else "vigente" for x in t["fim"]],
        "Carreto (P) R$/cx": t["carreto"].map(_t), "Frete puxada (N) R$/cx": t["frete"].map(_t)}),
        baixar=f"tabela_ambev_{esc}")
