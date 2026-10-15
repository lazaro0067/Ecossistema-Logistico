"""🏗️ Gestão de Capex — projetos de investimento do próximo ano: cadastro, aprovação, cronograma de desembolso e
impacto no resultado (entra no 🧮 Simulador OBZ)."""
import datetime as dt

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from modules.financeiro.obz_painel import AZUL, VERDE, VERMELHO, _mk
from repositories import operacoes_repo
from services import capex_service as cx
from services import obz_service as obz
from services.erros import RegraNegocioError

_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_ABAS = {"painel": "📊 Painel", "projetos": "📋 Projetos", "novo": "➕ Novo projeto",
         "fluxo": "💸 Desembolso & impacto no resultado"}


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def render(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "capex")
    prox = dt.date.today().year + 1
    c1, c2 = st.columns([1, 3])
    ano = c1.selectbox("Ano do orçamento", [str(prox), str(prox - 1), str(prox + 1)], key="cx_ano")
    with c2:
        aba = ui._escolha("cx_aba", list(_ABAS), "painel", pills=True, formatar=_ABAS.get)
    df = cx.resumo(op, ano)
    if aba == "novo":
        _form(usuario, op, ano, None)
        return
    if df.empty:
        st.info(f"Nenhum projeto de capex para {ano}. Use ➕ Novo projeto para orçar os investimentos — os aprovados "
                "entram no 🧮 Simulador OBZ como custo mensal (depreciação, juros, leasing, custo operacional − "
                "economia).")
        return
    {"painel": _painel, "projetos": _projetos, "fluxo": _fluxo}[aba](usuario, op, ano, df)


# --- 📊 Painel ---------------------------------------------------------------------------------------------------------
def _painel(usuario: dict, op: int, ano: str, df: pd.DataFrame) -> None:
    ap = df[df["status"].isin(cx.ENTRA_NO_ORCAMENTO)]
    prop = df[df["status"] == "proposto"]
    pb = ap["payback"].dropna()
    tema.kpis([
        {"titulo": "Proposto (todos)", "valor": _mk(df.loc[df["status"] != "reprovado", "valor"].sum()), "icone": "📝",
         "status": "info", "detalhe": f"{int((df['status'] != 'reprovado').sum())} projeto(s)"},
        {"titulo": "Aprovado", "valor": _mk(ap["valor"].sum()), "icone": "✔️", "status": "bom",
         "detalhe": f"{len(ap)} projeto(s)"},
        {"titulo": "Aguardando aprovação", "valor": _mk(prop["valor"].sum()), "icone": "⏳",
         "status": "atencao" if len(prop) else "bom", "detalhe": f"{len(prop)} projeto(s)"},
        {"titulo": f"Desembolso em {ano}", "valor": _mk(ap["desembolso_ano"].sum()), "icone": "💸", "status": "info",
         "detalhe": "caixa (aprovados)"},
        {"titulo": "Impacto no resultado", "valor": _mk(ap["impacto_ano"].sum()), "icone": "📉", "status": "info",
         "detalhe": f"depreciação {_mk(ap['deprec_ano'].sum())} · juros {_mk(ap['juros_ano'].sum())}"},
        {"titulo": "Payback médio", "valor": f"{pb.mean():.0f} meses" if len(pb) else "—", "icone": "⏱️",
         "status": "info", "detalhe": "projetos com economia"},
    ], key="kp_capex")
    a1, a2 = st.columns(2)
    vivos = df[df["status"] != "reprovado"]
    with a1:
        g = vivos.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor")
        fig = go.Figure(go.Bar(y=g["categoria"], x=g["valor"], orientation="h", marker_color=AZUL,
                               hovertemplate="%{y}<br>R$ %{x:,.0f}<extra></extra>"))
        graficos.mostrar(graficos._layout(fig, "Por categoria", max(260, 40 * len(g) + 80), legenda=False),
                         key="cx_g_cat")
    with a2:
        g = vivos.groupby(["area", "status"], as_index=False)["valor"].sum()
        fig = go.Figure()
        for stt, cor in (("aprovado", VERDE), ("em_execucao", AZUL), ("concluido", "#0B1F3A"), ("proposto", "#eda100")):
            x = g[g["status"] == stt]
            if not x.empty:
                fig.add_bar(y=x["area"], x=x["valor"], name=cx.STATUS[stt], orientation="h", marker_color=cor)
        fig.update_layout(barmode="stack")
        graficos.mostrar(graficos._layout(fig, "Por departamento e status", 320), key="cx_g_area")
    tema.secao("🏆 Projetos por prioridade")
    for pr in cx.PRIORIDADES:
        x = vivos[vivos["prioridade"] == pr]
        if x.empty:
            continue
        st.markdown(f"**{pr}** — {len(x)} projeto(s) · {_m(x['valor'].sum())}")
        ui.tabela(_tabela(x))


def _tabela(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Projeto": df["nome"], "Departamento": df["area"], "Categoria": df["categoria"].fillna(""),
        "Status": df["status"].map(cx.STATUS), "Investimento": df["valor"].map(_m),
        "Forma": df["forma"].map(cx.FORMAS), "Início": df["mes_ini"].map(lambda m: _MESES[int(m) - 1]),
        "Impacto no ano": df["impacto_ano"].map(_m),
        "Payback": df["payback"].map(lambda v: f"{v:.0f} meses" if pd.notna(v) else "—"),
        "Responsável": df["responsavel"].fillna("")}).reset_index(drop=True)


# --- 📋 Projetos -------------------------------------------------------------------------------------------------------
def _projetos(usuario: dict, op: int, ano: str, df: pd.DataFrame) -> None:
    c1, c2 = st.columns([1.2, 2])
    filtro = c1.multiselect("Status", list(cx.STATUS), default=[s for s in cx.STATUS if s != "reprovado"],
                            format_func=cx.STATUS.get, key="cx_f_st")
    v = df[df["status"].isin(filtro)] if filtro else df
    busca = c2.text_input("🔎 Buscar projeto", key="cx_busca")
    if busca:
        v = v[v["nome"].str.lower().str.contains(busca.lower())]
    t = _tabela(v)
    t.loc[len(t)] = ["TOTAL", "", "", "", _m(v["valor"].sum()), "", "", _m(v["impacto_ano"].sum()), "", ""]
    ui.tabela(t, baixar=f"capex_{ano}")
    if v.empty:
        return
    ids = v["id"].tolist()
    pid = st.selectbox("🔎 Abrir projeto", ids, format_func=lambda i: f"{df.set_index('id').at[i, 'nome']} · "
                       f"{cx.STATUS[df.set_index('id').at[i, 'status']]}", key="cx_sel")
    p = cx.buscar(pid)
    _detalhe(usuario, op, ano, p)


def _detalhe(usuario: dict, op: int, ano: str, p: dict) -> None:
    f = cx.fluxo(p)
    pb = cx.payback_meses(p)
    with st.container(border=True):
        st.markdown(f"### 🏗️ {p['nome']}  \n{p.get('area') or ''} · {p.get('categoria') or ''} · "
                    f"{p.get('tipo') or ''} · {p.get('prioridade') or ''} · **{cx.STATUS[p['status']]}**")
        if p.get("justificativa"):
            st.caption(f"Justificativa: {p['justificativa']}")
        tema.kpis([
            {"titulo": "Investimento", "valor": _m(p["valor"]), "icone": "🏗️", "status": "info",
             "detalhe": f"{cx.FORMAS.get(p['forma'])} · início {_MESES[int(p['mes_ini']) - 1]}"},
            {"titulo": f"Desembolso em {ano}", "valor": _m(f["desembolso"].sum()), "icone": "💸", "status": "info",
             "detalhe": f"{p['parcelas']} parcela(s)" if p["forma"] != "avista" else "à vista"},
            {"titulo": "Impacto no resultado", "valor": _m(f["impacto"].sum()), "icone": "📉", "status": "info",
             "detalhe": f"conta {p.get('conta') or '— (escolha a conta!)'}"},
            {"titulo": "Payback", "valor": f"{pb:.0f} meses" if pb else "—", "icone": "⏱️", "status": "info",
             "detalhe": f"economia {_m(p['economia_mensal'])}/mês · opex {_m(p['opex_mensal'])}/mês"},
            {"titulo": "Realizado", "valor": _m(p.get("valor_realizado")), "icone": "✅", "status": "info",
             "detalhe": "valor executado"},
        ], key=f"kp_cx_{p['id']}")
        acoes = []
        if p["status"] in ("proposto", "reprovado"):
            acoes += ["aprovado", "reprovado"] if p["status"] == "proposto" else ["proposto"]
        elif p["status"] == "aprovado":
            acoes += ["em_execucao", "reprovado"]
        elif p["status"] == "em_execucao":
            acoes += ["concluido"]
        if acoes:
            c1, c2 = st.columns([2, 1])
            com = c1.text_input("Comentário (obrigatório para reprovar)", key=f"cx_com_{p['id']}")
            real = c2.number_input("Valor realizado (R$)", value=float(p.get("valor_realizado") or 0), step=1000.0,
                                   key=f"cx_real_{p['id']}") if p["status"] in ("aprovado", "em_execucao") else None
            cols = st.columns(len(acoes) + 1)
            rot = {"aprovado": "✔️ Aprovar", "reprovado": "❌ Reprovar", "em_execucao": "🔧 Iniciar execução",
                   "concluido": "✅ Concluir", "proposto": "↩️ Reabrir como proposto"}
            for c, a in zip(cols, acoes):
                if c.button(rot[a], key=f"cx_ac_{p['id']}_{a}", type="primary" if a != "reprovado" else "secondary"):
                    ui.acao(cx.mudar_status, p["id"], a, usuario, com, real if real else None,
                            sucesso=f"Projeto: {cx.STATUS[a]}.")
            if not cx.pode_aprovar(usuario):
                st.caption("Aprovar / reprovar: dono do financeiro, diretor ou CEO (papéis liberados pelo Master).")
        e1, e2 = st.columns(2)
        with e1.expander("✏️ Editar projeto"):
            _form(usuario, op, ano, p)
        with e2.expander("🕒 Histórico"):
            h = cx.historico(p["id"])
            ui.tabela(pd.DataFrame({"Quando": pd.to_datetime(h["em"]).dt.strftime("%d/%m/%Y %H:%M"),
                                    "Status": h["status"].map(cx.STATUS).fillna("✏️"), "Quem": h["usuario"],
                                    "Comentário": h["comentario"].fillna("")}))
            if st.button("🗑️ Excluir projeto", key=f"cx_del_{p['id']}"):
                ui.acao(cx.excluir, p["id"], usuario, sucesso="Projeto excluído.")
        tab = pd.DataFrame({"Mês": [_MESES[m - 1] for m in f["mes"]], "Desembolso": f["desembolso"].map(_m),
                            "Depreciação": f["depreciacao"].map(_m), "Juros": f["juros"].map(_m),
                            "Leasing/locação": f["parcela"].map(_m), "Custo operacional": f["opex"].map(_m),
                            "Economia": f["economia"].map(_m), "Impacto no resultado": f["impacto"].map(_m)})
        tab.loc[len(tab)] = ["TOTAL", *[_m(f[c].sum()) for c in ("desembolso", "depreciacao", "juros", "parcela",
                                                                     "opex", "economia", "impacto")]]
        ui.tabela(tab, baixar=f"capex_{p['id']}_fluxo")


# --- ➕ Novo / editar --------------------------------------------------------------------------------------------------
def _form(usuario: dict, op: int, ano: str, p: dict | None) -> None:
    if operacoes_repo.e_consolidada(op):
        st.info("Escolha uma revenda (não a visão consolidada) para cadastrar projetos.")
        return
    p = p or {}
    areas = obz.areas()["nome"].tolist() or [obz.SEM_AREA]
    ct = obz.contas(so_obz=True)
    opc = [""] + [f"{c} · {n}" for c, n in zip(ct["codigo"], ct["nome"].fillna(""))]
    rot = {o.split(" · ")[0]: o for o in opc if o}
    # sugestão de conta: depreciação / arrendamento / juros
    def _sug(chaves):
        for o in opc[1:]:
            if any(k in obz._n(o) for k in chaves):
                return o
        return ""

    with st.form(f"cx_form_{p.get('id', 'novo')}", border=True):
        st.markdown("**🏗️ Projeto de investimento**" + (f" · {ano}" if not p else ""))
        a = st.columns([3, 1])
        nome = a[0].text_input("Nome do projeto *", value=p.get("nome") or "")
        codigo = a[1].text_input("Código", value=p.get("codigo") or "")
        b = st.columns(4)
        area = b[0].selectbox("Departamento *", areas, index=areas.index(p["area"]) if p.get("area") in areas else 0)
        cat = b[1].selectbox("Categoria", cx.CATEGORIAS, index=cx.CATEGORIAS.index(p["categoria"])
                             if p.get("categoria") in cx.CATEGORIAS else 0)
        tipo = b[2].selectbox("Tipo", cx.TIPOS, index=cx.TIPOS.index(p["tipo"]) if p.get("tipo") in cx.TIPOS else 0)
        prio = b[3].selectbox("Prioridade", cx.PRIORIDADES, index=cx.PRIORIDADES.index(p["prioridade"])
                              if p.get("prioridade") in cx.PRIORIDADES else 1)
        just = st.text_area("Justificativa (por que investir, o que resolve)", value=p.get("justificativa") or "",
                            height=70)
        st.markdown("**💰 Valor e forma**")
        c = st.columns(4)
        valor = c[0].number_input("Valor do investimento (R$) *", value=float(p.get("valor") or 0), step=1000.0,
                                  min_value=0.0)
        mes = c[1].selectbox("Mês de início", list(range(1, 13)), index=int(p.get("mes_ini") or 1) - 1,
                             format_func=lambda m: _MESES[m - 1])
        formas = list(cx.FORMAS)
        forma = c[2].selectbox("Forma", formas, index=formas.index(p["forma"]) if p.get("forma") in formas else 0,
                               format_func=cx.FORMAS.get)
        parc = c[3].number_input("Parcelas (financiado / leasing)", value=int(p.get("parcelas") or 1), min_value=1,
                                 step=1)
        d = st.columns(4)
        taxa = d[0].number_input("Juros do financiamento (% ao ano)", value=float(p.get("taxa_aa") or 0), step=.5,
                                 min_value=0.0)
        vida = d[1].number_input("Vida útil (anos) — depreciação", value=float(p.get("vida_util") or 5), step=1.0,
                                 min_value=0.5)
        opex = d[2].number_input("Custo operacional novo (R$/mês)", value=float(p.get("opex_mensal") or 0), step=100.0,
                                 help="Manutenção, seguro, licenças… que o investimento passa a gerar")
        econ = d[3].number_input("Economia esperada (R$/mês)", value=float(p.get("economia_mensal") or 0), step=100.0,
                                 help="O que deixa de gastar (aluguel, manutenção, horas extras…) — usado no payback")
        st.markdown("**🧾 Onde entra no orçamento (OBZ)**")
        e = st.columns(3)
        padrao = rot.get(p.get("conta") or "") or _sug(("deprecia", "amortiza", "arrend", "leasing"))
        conta = e[0].selectbox("Conta do custo mensal (depreciação / leasing / opex)", opc,
                               index=opc.index(padrao) if padrao in opc else 0)
        padrao_j = rot.get(p.get("conta_juros") or "") or _sug(("juros",))
        conta_j = e[1].selectbox("Conta dos juros (financiado)", opc, index=opc.index(padrao_j) if padrao_j in opc
                                 else 0)
        resp = e[2].text_input("Responsável", value=p.get("responsavel") or "")
        if st.form_submit_button("💾 Salvar projeto", type="primary"):
            dados = {"nome": nome, "codigo": codigo, "area": area, "categoria": cat, "tipo": tipo, "prioridade": prio,
                     "justificativa": just, "valor": valor, "mes_ini": mes, "forma": forma, "parcelas": parc,
                     "taxa_aa": taxa, "vida_util": vida, "opex_mensal": opex, "economia_mensal": econ,
                     "conta": conta.split(" · ")[0] if conta else None,
                     "conta_juros": conta_j.split(" · ")[0] if conta_j else None, "responsavel": resp}
            try:
                cx.salvar(op, p.get("ano") or ano, dados, usuario, p.get("id"))
            except RegraNegocioError as err:
                st.error(str(err))
            else:
                ui.avisar("Projeto salvo." + ("" if p else " Ele fica como 📝 Proposto até a aprovação."))
                st.session_state["cx_aba"] = st.session_state["cx_aba__ultima"] = "projetos"
                st.rerun()
    st.caption("À vista e financiado: o resultado recebe a depreciação (valor ÷ vida útil) e os juros. Leasing / "
               "locação: a parcela (valor do contrato ÷ parcelas). Em todos: + custo operacional − economia, a partir do "
               "mês de início. Só os projetos aprovados entram no 🧮 Simulador OBZ.")


# --- 💸 Desembolso & impacto ------------------------------------------------------------------------------------------
def _fluxo(usuario: dict, op: int, ano: str, df: pd.DataFrame) -> None:
    so_ap = st.toggle("Só os aprovados", value=True, key="cx_fl_ap")
    v = df[df["status"].isin(cx.ENTRA_NO_ORCAMENTO)] if so_ap else df[df["status"] != "reprovado"]
    if v.empty:
        st.info("Nenhum projeto neste filtro.")
        return
    des, imp = {}, {}
    for p in v.to_dict("records"):
        f = cx.fluxo(p)
        des[p["nome"]] = f["desembolso"].tolist()
        imp[p["nome"]] = f["impacto"].tolist()
    x = _MESES
    td = [sum(vs[i] for vs in des.values()) for i in range(12)]
    ti = [sum(vs[i] for vs in imp.values()) for i in range(12)]
    fig = go.Figure()
    fig.add_bar(x=x, y=td, name="Desembolso (caixa)", marker_color=AZUL)
    fig.add_scatter(x=x, y=ti, name="Impacto no resultado", mode="lines+markers", line=dict(color=VERMELHO))
    graficos.mostrar(graficos._layout(fig, f"Capex {ano} — caixa × resultado por mês", 340), key="cx_g_fluxo")
    for titulo, dados, tot in (("💸 Desembolso de caixa por mês", des, td), ("📉 Impacto no resultado por mês", imp, ti)):
        tema.secao(titulo)
        t = pd.DataFrame({"Projeto": list(dados)})
        for i, mx in enumerate(x):
            t[mx] = [_mk(vs[i]) for vs in dados.values()]
        t["Total"] = [_m(sum(vs)) for vs in dados.values()]
        t.loc[len(t)] = ["TOTAL", *[_mk(z) for z in tot], _m(sum(tot))]
        ui.tabela(t, baixar=f"capex_{ano}_{'desembolso' if tot is td else 'impacto'}")
