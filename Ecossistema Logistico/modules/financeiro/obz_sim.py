"""Financeiro › 🧮 Simulador OBZ — monta o orçamento do ano seguinte a partir do histórico do ano atual, com
premissas, volume de HL, equipe pelo HL, iniciativas e capex; depois passa pela crítica dos donos e pelas aprovações
(financeiro → diretor → corporativo/CEO) e vira o Plan do OBZ."""
import datetime as dt
import html as _h

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from modules.financeiro.obz_painel import AZUL, CINZA, VERDE, VERMELHO, _mk
from repositories import operacoes_repo
from services import obz_service as obz
from services import obz_sim_service as sim
from services.erros import RegraNegocioError

_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_ABAS = {"resumo": "📊 Resumo", "premissas": "1️⃣ Premissas", "volume": "2️⃣ Volume & equipe",
         "contas": "3️⃣ Contas & departamentos", "inic": "4️⃣ Iniciativas & capex", "criticas": "💬 Críticas",
         "reunioes": "🗓️ Reuniões", "historico": "🕒 Histórico"}
_CSS = """<style>
.sim-fluxo{display:flex;flex-wrap:wrap;gap:.35rem;margin:.4rem 0 .8rem}
.sim-et{flex:1 1 120px;border-radius:12px;padding:.45rem .6rem;font-size:.78rem;font-weight:700;border:1px solid #dfe5ee;
 background:#fff;color:#7a8394;line-height:1.25}
.sim-et.ok{background:#e7f7f0;border-color:#9fdcc3;color:#0f6b4a}
.sim-et.at{background:linear-gradient(120deg,#0B1F3A,#2a78d6);color:#fff;border-color:#2a78d6;box-shadow:0 4px 14px #2a78d633}
.sim-et small{display:block;font-weight:500;opacity:.85;font-size:.7rem}
</style>"""


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+.1f}%".replace(".", ",")


def _nomes(uids) -> str:
    from repositories import usuarios_repo

    out = []
    for u in uids:
        r = usuarios_repo.buscar(int(u)) if u else None
        if r:
            out.append(r["nome"])
    return ", ".join(out) or "ninguém cadastrado (⚙️ Cadastros OBZ › Papéis)"


def render(usuario: dict, operacao_id: int) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    if operacoes_repo.e_consolidada(operacao_id):
        st.info("Escolha uma revenda no menu (não a visão consolidada) para montar o orçamento.")
        return
    sims = sim.listar(operacao_id)
    pode_montar = sim.pode_montar(usuario)
    c1, c2 = st.columns([2.2, 1])
    sim_id = None
    if not sims.empty:
        ids = sims["id"].tolist()
        rot = {r["id"]: f"{r['nome']} · {sim.ETAPAS.get(r['status'], r['status'])}" for _, r in sims.iterrows()}
        sim_id = c1.selectbox("Simulação", ids, format_func=rot.get, key="sim_sel")
    with c2:
        st.write("")
        criar = st.toggle("➕ Criar simulador de OBZ", key="sim_criar", value=sims.empty, disabled=not pode_montar,
                          help=None if pode_montar else "Só o dono do financeiro (ou quem o Master liberou para o Plan)")
    if criar and pode_montar:
        _form_criar(usuario, operacao_id)
    if sims.empty:
        if not pode_montar:
            st.info("Ainda não há simulador de orçamento. Quem cria é o dono do financeiro (papel liberado pelo Master "
                    "em ⚙️ Cadastros OBZ › 🔑 Papéis).")
        _explicacao()
        return
    s = sim.buscar(sim_id)
    _cabecalho(s, usuario)
    aba = ui._escolha("sim_aba", list(_ABAS), "resumo", pills=True, formatar=_ABAS.get)
    {"resumo": _resumo, "premissas": _premissas, "volume": _volume, "contas": _contas, "inic": _iniciativas,
     "criticas": _criticas, "reunioes": _reunioes, "historico": _historico}[aba](s, usuario)


def _explicacao() -> None:
    tema.secao("Como funciona", "Tudo começa pelo histórico do ano atual (16.03.01 / Base OBZ).")
    st.markdown(
        "1. **Montagem (financeiro):** premissas (IPCA, aluguel, fretes, insumos, dissídio no mês negociado), volume "
        "de HL mês a mês, equipe pelo HL, iniciativas e capex → o sistema calcula cada conta × departamento.\n"
        "2. **Dono do financeiro** aprova a montagem.\n3. **Donos de conta** criticam as suas contas.\n"
        "4. **Donos de departamento** criticam o departamento.\n5. **Financeiro** revisa cada crítica (aprova ou "
        "reprova com justificativa).\n6. **Diretor** aprova.\n7. **Corporativo / CEO** aprova → vira o **Plan** do OBZ "
        "do ano, por conta e departamento.\n\nCada etapa avisa quem precisa agir e tem a sua reunião estruturada.")


def _form_criar(usuario: dict, op: int) -> None:
    with st.form("sim_form_criar", border=True):
        st.markdown("**🧮 Novo simulador de orçamento**")
        a1, a2, a3 = st.columns([1, 2, 1])
        prox = dt.date.today().year + 1
        ano = a1.selectbox("Ano do orçamento", [str(prox), str(prox + 1), str(prox - 1)], key="sim_n_ano")
        nome = a2.text_input("Nome", value=f"Orçamento {prox}", key="sim_n_nome")
        cresc = a3.number_input("Crescimento de volume (%)", value=0.0, step=1.0, key="sim_n_cresc")
        st.caption(f"Base = realizado de {int(ano) - 1} (histórico do ano atual). As premissas podem ser ajustadas "
                   "depois, na etapa de montagem.")
        if st.form_submit_button("Criar simulador", type="primary"):
            try:
                sid = sim.criar(op, ano, nome, usuario, {"crescimento_volume": cresc})
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["sim_sel"] = sid
                st.session_state["sim_criar"] = False
                ui.avisar("Simulador criado a partir do histórico. Ajuste as premissas e o volume.")
                st.rerun()


def _cabecalho(s: dict, usuario: dict) -> None:
    etapas = list(sim.ETAPAS)
    i = etapas.index(s["status"])
    caixas = []
    for k, (et, rot) in enumerate(sim.ETAPAS.items()):
        cls = "ok" if k < i else "at" if k == i else ""
        caixas.append(f'<div class="sim-et {cls}">{_h.escape(rot)}<small>{"✓ feito" if k < i else "agora" if k == i else ""}'
                      f'</small></div>')
    st.markdown(f'<div class="sim-fluxo">{"".join(caixas)}</div>', unsafe_allow_html=True)
    quem = {"rascunho": obz.usuarios_papel("fin_dono") + obz.usuarios_papel("plan"),
            "aprov_fin": obz.usuarios_papel("fin_dono"), "revisao_fin": obz.usuarios_papel("fin_dono"),
            "diretor": obz.usuarios_papel("diretor"), "ceo": obz.usuarios_papel("ceo")}
    if s["status"] in quem:
        st.caption(f"👤 Quem age agora: **{_nomes(quem[s['status']])}**")
    elif s["status"] == "critica_conta":
        st.caption("👤 Quem age agora: **donos e sub-donos de cada conta** (aba 💬 Críticas). O dono do financeiro "
                   "encerra a rodada.")
    elif s["status"] == "critica_depto":
        st.caption("👤 Quem age agora: **donos de cada departamento** (aba 💬 Críticas). O dono do financeiro encerra "
                   "a rodada.")
    else:
        st.success(f"✅ Publicado no Plan de {s['ano']} em {pd.to_datetime(s['publicado_em']).strftime('%d/%m/%Y %H:%M')}"
                   if s.get("publicado_em") else "✅ Aprovado.")
    acoes = sim.acoes_disponiveis(s, usuario)
    if not acoes:
        return
    with st.container(border=True):
        st.markdown("**▶️ Próximo passo**")
        precisa = [a for a in acoes if sim._TRANSICOES[a][3]]
        coment = st.text_area("Comentário / justificativa" + (" (obrigatório para devolver ou criticar)" if precisa else
                                                             " (opcional)"), key=f"sim_coment_{s['id']}", height=70)
        if s["status"] == "revisao_fin" and sim.pendencias_revisao(s["id"]):
            st.warning(f"Faltam decisões em {sim.pendencias_revisao(s['id'])} crítica(s) antes de enviar ao diretor "
                       "(aba 💬 Críticas).")
        cols = st.columns(len(acoes))
        for c, a in zip(cols, acoes):
            if c.button(sim.ROTULO_ACAO[a], key=f"sim_ac_{a}", type="secondary" if sim._TRANSICOES[a][3] else "primary"):
                try:
                    para = sim.avancar(s["id"], a, usuario, coment)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    ui.avisar(f"Simulador agora em: {sim.ETAPAS[para]}.")
                    st.rerun()


# --- 📊 Resumo --------------------------------------------------------------------------------------------------
def _resumo(s: dict, usuario: dict) -> None:
    ra = sim.resumo_areas(s["id"])
    hb, hp = sim.hl_totais(s["id"])
    base, calc, fin = float(ra["base"].sum()), float(ra["calculado"].sum()), float(ra["final"].sum())
    cap = sim.capex(s["id"])
    pend = sim.pendencias_revisao(s["id"])
    rs_b, rs_p = (base / hb if hb else None), (fin / hp if hp else None)
    tema.kpis([
        {"titulo": f"Histórico {s['ano_base']} (base)", "valor": _mk(base), "icone": "📚", "status": "info",
         "detalhe": "realizado do ano atual, anualizado"},
        {"titulo": f"Orçamento {s['ano']}", "valor": _mk(fin), "icone": "🎯",
         "status": "atencao" if fin > base * 1.08 else "bom", "detalhe": f"{_p((fin / base - 1) * 100 if base else None)} "
                                                                       "vs histórico"},
        {"titulo": "R$/HL", "valor": _m(rs_p), "icone": "💲", "status": "bom" if rs_p and rs_b and rs_p <= rs_b * 1.05
         else "atencao", "detalhe": f"histórico {_m(rs_b)}/HL"},
        {"titulo": f"HL {s['ano']}", "valor": ui.numero(hp), "icone": "🍺", "status": "info",
         "detalhe": f"{_p((hp / hb - 1) * 100 if hb else None)} vs {s['ano_base']}"},
        {"titulo": "Capex previsto", "valor": _mk(cap), "icone": "🏗️", "status": "info", "detalhe": "investimento"},
        {"titulo": "Críticas sem decisão", "valor": ui.numero(pend), "icone": "💬",
         "status": "atencao" if pend else "bom", "detalhe": f"calculado {_mk(calc)}"},
    ], key="kp_sim")
    if ra.empty:
        st.info("Sem contas no simulador.")
        return
    a1, a2 = st.columns([1.3, 1])
    with a1:
        fig = go.Figure()
        fig.add_bar(y=ra["area"], x=ra["base"], name=f"Histórico {s['ano_base']}", orientation="h", marker_color="#c9d3e3")
        fig.add_bar(y=ra["area"], x=ra["final"], name=f"Orçamento {s['ano']}", orientation="h",
                    marker_color=[VERMELHO if f > b * 1.08 else AZUL for f, b in zip(ra["final"], ra["base"])])
        fig.update_layout(barmode="group")
        fig.update_yaxes(autorange="reversed")
        graficos.mostrar(graficos._layout(fig, "Por departamento", max(300, 40 * len(ra) + 80)), key="sim_g_area")
    with a2:
        v = sim.valores_mensais(s["id"], final=True)
        li = sim.linhas(s["id"])
        sinal = dict(zip(zip(li["conta"], li["depto"]), li["sinal"]))
        v["liq"] = [x * sinal.get((c, d), 1.0) for c, d, x in zip(v["conta"], v["depto"], v["valor"])]
        mens = v.groupby("mes")["liq"].sum()
        vol = sim.volume(s["id"])
        x = [_MESES[int(m[5:]) - 1] for m in mens.index]
        fig = go.Figure()
        fig.add_bar(x=x, y=mens.values, name="Orçamento (R$)", marker_color=AZUL)
        fig.add_scatter(x=x, y=[base / 12] * len(x), name="Média histórica", mode="lines",
                        line=dict(color="#0B1F3A", dash="dot"))
        hlp = dict(zip([_MESES[int(m[5:]) - 1] for m in vol["mes"]], vol["hl_plan"]))
        fig.add_scatter(x=x, y=[hlp.get(k) for k in x], name="HL", yaxis="y2", mode="lines+markers",
                        line=dict(color=VERDE))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
        graficos.mostrar(graficos._layout(fig, "Mês a mês", 340), key="sim_g_mes")
    vis = pd.DataFrame({"Departamento": ra["area"], f"Histórico {s['ano_base']}": ra["base"].map(_m),
                        "Calculado": ra["calculado"].map(_m), f"Orçamento {s['ano']}": ra["final"].map(_m),
                        "Var. %": ra["var_pct"].map(_p),
                        "R$/HL": (ra["final"] / hp if hp else ra["final"] * 0).map(_m)})
    vis.loc[len(vis)] = ["TOTAL", _m(base), _m(calc), _m(fin), _p((fin / base - 1) * 100 if base else None), _m(rs_p)]
    ui.tabela(vis, baixar=f"orcamento_{s['ano']}_departamentos")


# --- 1️⃣ Premissas ------------------------------------------------------------------------------------------------
def _premissas(s: dict, usuario: dict) -> None:
    pm = s["premissas"]
    ed = s["status"] == "rascunho" and sim.pode_montar(usuario)
    if not ed:
        st.caption("🔒 As premissas só mudam na etapa de montagem, por quem monta o orçamento.")
    with st.form(f"sim_prem_{s['id']}", border=True):
        st.markdown("**📈 Inflação e reajustes do próximo ano**")
        c = st.columns(4)
        ipca = c[0].number_input("IPCA (%)", value=float(pm["ipca"]), step=.1, disabled=not ed,
                                 help="Corrige as despesas fixas e as receitas")
        alug = c[1].number_input("Aluguel (%)", value=float(pm["aluguel"]), step=.1, disabled=not ed,
                                 help="Reajuste dos contratos de aluguel (IGP-M/IPCA)")
        fret = c[2].number_input("Fretes (%)", value=float(pm["fretes"]), step=.1, disabled=not ed,
                                 help="Inflação de fretes — aplicada sobre o custo por HL")
        ins = c[3].number_input("Insumos (%)", value=float(pm["insumos"]), step=.1, disabled=not ed,
                                help="Combustível, pneus, peças, materiais — sobre o custo por HL")
        st.markdown("**👥 Pessoal**")
        d = st.columns(3)
        dmes = d[0].selectbox("Mês do dissídio (negociado)", list(range(1, 13)), index=int(pm["dissidio_mes"]) - 1,
                              format_func=lambda m: _MESES[m - 1], disabled=not ed)
        dpct = d[1].number_input("% negociado no dissídio", value=float(pm["dissidio_pct"]), step=.1, disabled=not ed)
        elas = d[2].number_input("Equipe acompanha o volume (%)", value=float(pm["elasticidade"]), step=5.0,
                                 disabled=not ed, help="Nos departamentos operacionais sem equipe informada: quanto do "
                                                       "crescimento de HL vira crescimento de equipe")
        st.markdown("**📚 Base (histórico do ano atual)**")
        base = st.radio("Como anualizar o histórico", ["media", "ytd_plan"], index=0 if pm["base"] == "media" else 1,
                        horizontal=True, disabled=not ed,
                        format_func={"media": f"Média mensal do realizado de {s['ano_base']} × 12",
                                     "ytd_plan": f"Realizado de {s['ano_base']} + plan dos meses que faltam"}.get)
        if st.form_submit_button("💾 Salvar e recalcular", type="primary", disabled=not ed):
            ui.acao(sim.salvar_premissas, s["id"], {"ipca": ipca, "aluguel": alug, "fretes": fret, "insumos": ins,
                                                    "dissidio_mes": dmes, "dissidio_pct": dpct, "elasticidade": elas,
                                                    "base": base}, usuario, sucesso="Premissas salvas e contas recalculadas.")
    st.markdown("**Como cada conta é projetada**")
    ui.tabela(pd.DataFrame({"Driver": list(sim.DRIVERS.values()), "Cálculo mensal": [
        "base × (1 + dissídio a partir do mês negociado) × fator de equipe (HL do mês ÷ produtividade)",
        "base × (HL do mês ÷ HL médio do ano atual) × (1 + fretes)",
        "base × (HL do mês ÷ HL médio do ano atual) × (1 + insumos)", "base × (1 + aluguel)", "base × (1 + IPCA)",
        "base × (1 + IPCA)", "igual à base"]}))


# --- 2️⃣ Volume & equipe -------------------------------------------------------------------------------------------
def _volume(s: dict, usuario: dict) -> None:
    ed = s["status"] == "rascunho" and sim.pode_montar(usuario)
    vol = sim.volume(s["id"])
    tema.secao("🍺 Volume de HL mês a mês", f"HL base = vendido em {s['ano_base']} (mês sem dado usa a média). "
                                            "Edite o HL planejado de cada mês.")
    if ed:
        c1, c2, _ = st.columns([1, 1, 2])
        cr = c1.number_input("Crescimento sobre o histórico (%)", value=0.0, step=1.0, key="sim_vol_cr")
        if c2.button("Aplicar em todos os meses", key="sim_vol_ap"):
            ui.acao(sim.salvar_volume, s["id"], vol.assign(hl_plan=vol["hl_base"] * (1 + cr / 100)), usuario,
                    sucesso="Volume atualizado.")
    tab = vol.assign(Mês=[_MESES[int(m[5:]) - 1] + "/" + m[:4] for m in vol["mes"]])
    din = st.column_config.NumberColumn
    novo = st.data_editor(tab, hide_index=True, key=f"sim_vol_{s['id']}", **ui.LARGURA,
                          disabled=[c for c in tab.columns if c != "hl_plan"] if ed else list(tab.columns),
                          column_order=["Mês", "hl_base", "hl_plan"],
                          column_config={"hl_base": din(f"HL {s['ano_base']}", format="%.0f"),
                                         "hl_plan": din(f"HL {s['ano']} ✏️", format="%.0f")})
    if ed and st.button("💾 Salvar volume e recalcular", type="primary", key="sim_vol_s"):
        ui.acao(sim.salvar_volume, s["id"], novo, usuario, sucesso="Volume salvo e contas recalculadas.")
    hb, hp = sim.hl_totais(s["id"])
    st.caption(f"Total: {ui.numero(hb)} HL em {s['ano_base']} → {ui.numero(hp)} HL em {s['ano']} "
               f"({_p((hp / hb - 1) * 100 if hb else None)}).")

    tema.secao("👥 Equipe pelo HL (desdobrada)",
               "Para os departamentos que acompanham o volume: informe a equipe de hoje e a produtividade alvo "
               "(HL por pessoa no mês) — a equipe necessária de cada mês = HL do mês ÷ produtividade, e o custo de "
               "pessoal acompanha. Sem equipe informada, usa o % das premissas.")
    eq = sim.equipe(s["id"])
    hl_med_b = float(pd.to_numeric(vol["hl_base"], errors="coerce").mean() or 0)
    eq["acompanha"] = eq["acompanha"].fillna(0).astype(int) == 1
    eq["hl_pessoa"] = [hl_med_b / float(e) if pd.notna(e) and e else None for e in eq["equipe_atual"]]
    novo = st.data_editor(eq, hide_index=True, key=f"sim_eq_{s['id']}", **ui.LARGURA,
                          disabled=["area", "hl_pessoa"] if ed else list(eq.columns),
                          column_order=["area", "acompanha", "equipe_atual", "hl_pessoa", "produtividade"],
                          column_config={"area": "Departamento",
                                         "acompanha": st.column_config.CheckboxColumn("Acompanha o HL ✏️"),
                                         "equipe_atual": din("Equipe hoje (pessoas) ✏️", format="%.0f"),
                                         "hl_pessoa": din("HL/pessoa hoje", format="%.0f"),
                                         "produtividade": din("Produtividade alvo (HL/pessoa) ✏️", format="%.0f")})
    if ed and st.button("💾 Salvar equipe e recalcular", type="primary", key="sim_eq_s"):
        ui.acao(sim.salvar_equipe, s["id"], novo, usuario, sucesso="Equipe salva e pessoal recalculado.")
    proj = eq[eq["acompanha"] & eq["equipe_atual"].notna() & eq["produtividade"].notna()]
    if not proj.empty:
        linhas = []
        for r in proj.itertuples(index=False):
            linhas.append({"Departamento": r.area, "Hoje": int(r.equipe_atual),
                           **{_MESES[int(m[5:]) - 1]: round(float(h) / float(r.produtividade), 1)
                              for m, h in zip(vol["mes"], vol["hl_plan"]) if pd.notna(h)}})
        st.markdown("**Equipe necessária por mês (HL do mês ÷ produtividade alvo)**")
        ui.tabela(pd.DataFrame(linhas), baixar=f"equipe_{s['ano']}")


# --- 3️⃣ Contas ----------------------------------------------------------------------------------------------------
def _contas(s: dict, usuario: dict) -> None:
    ed = s["status"] == "rascunho" and sim.pode_montar(usuario)
    li = sim.linhas(s["id"])
    if li.empty:
        st.info("Sem contas.")
        return
    c1, c2 = st.columns([1.4, 2])
    areas = ["Todos"] + sorted(li["area"].dropna().unique())
    area = c1.selectbox("Departamento", areas, key="sim_ct_area")
    busca = c2.text_input("🔎 Buscar conta", key="sim_ct_busca", placeholder="código ou nome")
    v = li if area == "Todos" else li[li["area"] == area]
    if busca:
        b = busca.lower()
        v = v[v["conta"].str.contains(b) | v["nome_conta"].fillna("").str.lower().str.contains(b)]
    _, hp = sim.hl_totais(s["id"])
    tab = pd.DataFrame({"id": v["id"], "Departamento": v["area"], "Conta": v["conta"] + " · " + v["nome_conta"].fillna(""),
                        "Depto": v["nome_depto"], "driver": v["driver"], "Base": v["base_ano"], "Calculado": v["calc_ano"],
                        "Final": v["final_ano"], "Var %": v["var_pct"].round(1),
                        "R$/HL": (v["final_ano"] / hp if hp else v["final_ano"] * 0).round(2)}).reset_index(drop=True)
    st.caption(f"{len(tab)} linha(s) conta × depto · Base = histórico de {s['ano_base']} anualizado · Final = calculado "
               "ou a crítica aprovada pelo financeiro." + (" Troque o **driver** para mudar como a conta é projetada."
                                                           if ed else ""))
    din = st.column_config.NumberColumn
    novo = st.data_editor(tab, hide_index=True, key=f"sim_ct_{s['id']}_{area}", **ui.LARGURA,
                          disabled=[c for c in tab.columns if c != "driver"] if ed else list(tab.columns),
                          column_order=["Departamento", "Conta", "Depto", "driver", "Base", "Calculado", "Final",
                                        "Var %", "R$/HL"],
                          column_config={"driver": st.column_config.SelectboxColumn("Driver ✏️",
                                                                                    options=list(sim.DRIVERS),
                                                                                    width="medium"),
                                         "Base": din(format="R$ %.0f"), "Calculado": din(format="R$ %.0f"),
                                         "Final": din(format="R$ %.0f"), "Var %": din(format="%.1f%%"),
                                         "R$/HL": din(format="R$ %.2f")})
    st.caption("Drivers: " + " · ".join(f"**{k}** = {v_}" for k, v_ in sim.DRIVERS.items()))
    if ed and st.button("💾 Salvar drivers e recalcular", type="primary", key="sim_ct_s"):
        mud = {int(i): d for i, d, o in zip(novo["id"], novo["driver"], tab["driver"]) if d != o}
        ui.acao(sim.salvar_drivers, s["id"], mud, usuario, sucesso=f"{len(mud)} driver(s) alterado(s) e recalculado.")


# --- 4️⃣ Iniciativas & capex -----------------------------------------------------------------------------------------
def _iniciativas(s: dict, usuario: dict) -> None:
    ed = s["status"] == "rascunho" and sim.pode_montar(usuario)
    st.caption("O que vai planejar para o ano: **despesas novas** (contratações, contratos, projetos), **economias** "
               "(cortes, renegociações) e **capex** (investimentos — fica à parte do OBZ). Despesa e economia entram na "
               "conta escolhida, a partir do mês de início (por mês se recorrente).")
    ini = sim.iniciativas(s["id"])
    li = sim.linhas(s["id"])
    ct = obz.contas(so_obz=True)
    opc_ct = [f"{c} · {n}" for c, n in zip(ct["codigo"], ct["nome"].fillna(""))]
    rot_ct = {c: f"{c} · {n}" for c, n in zip(ct["codigo"], ct["nome"].fillna(""))}
    areas = sorted(li["area"].dropna().unique()) if not li.empty else []
    tipos_rot = {v: k for k, v in sim.TIPOS_INIC.items()}
    tab = pd.DataFrame({"tipo": [sim.TIPOS_INIC.get(t, t) for t in ini["tipo"]] if not ini.empty else [],
                        "descricao": ini["descricao"] if not ini.empty else [],
                        "area": ini["area"] if not ini.empty else [],
                        "conta": [rot_ct.get(c, c) for c in ini["conta"]] if not ini.empty else [],
                        "mes_ini": [_MESES[int(m) - 1] for m in ini["mes_ini"]] if not ini.empty else [],
                        "valor": ini["valor"] if not ini.empty else [],
                        "recorrente": (ini["recorrente"].astype(int) == 1) if not ini.empty else []})
    novo = st.data_editor(tab, hide_index=True, num_rows="dynamic" if ed else "fixed", key=f"sim_ini_{s['id']}",
                          **ui.LARGURA, disabled=not ed,
                          column_config={
                              "tipo": st.column_config.SelectboxColumn("Tipo ✏️", options=list(sim.TIPOS_INIC.values()),
                                                                       required=True),
                              "descricao": st.column_config.TextColumn("Descrição ✏️", width="large"),
                              "area": st.column_config.SelectboxColumn("Departamento ✏️", options=areas),
                              "conta": st.column_config.SelectboxColumn("Conta (despesa/economia) ✏️", options=opc_ct,
                                                                        width="large"),
                              "mes_ini": st.column_config.SelectboxColumn("Início ✏️", options=_MESES),
                              "valor": st.column_config.NumberColumn("Valor ✏️ (R$/mês · capex = total)",
                                                                     format="R$ %.2f"),
                              "recorrente": st.column_config.CheckboxColumn("Todo mês ✏️")})
    if ed and st.button("💾 Salvar iniciativas e recalcular", type="primary", key="sim_ini_s"):
        dados = novo.assign(tipo=novo["tipo"].map(tipos_rot),
                            conta=novo["conta"].map(lambda x: str(x).split(" · ")[0] if isinstance(x, str) else None),
                            mes_ini=novo["mes_ini"].map(lambda x: _MESES.index(x) + 1 if x in _MESES else 1))
        ui.acao(sim.salvar_iniciativas, s["id"], dados, usuario, sucesso="Iniciativas salvas e orçamento recalculado.")
    if not ini.empty:
        g = ini.assign(anual=[abs(v) * ((13 - int(m)) if r else 1) if t != "capex" else abs(v)
                              for v, m, r, t in zip(ini["valor"], ini["mes_ini"], ini["recorrente"], ini["tipo"])])
        tema.kpis([{"titulo": sim.TIPOS_INIC[t], "valor": _m(g.loc[g["tipo"] == t, "anual"].sum()), "icone": "",
                    "status": "info", "detalhe": f"{int((g['tipo'] == t).sum())} item(ns) no ano"}
                   for t in sim.TIPOS_INIC], key="kp_sim_ini")


# --- 💬 Críticas ------------------------------------------------------------------------------------------------------
def _criticas(s: dict, usuario: dict) -> None:
    li = sim.donos(sim.linhas(s["id"]))
    if li.empty:
        st.info("Sem contas.")
        return
    st_ = s["status"]
    ver_tudo = sim.pode_fin(usuario)
    din = st.column_config.NumberColumn
    if st_ in ("critica_conta", "critica_depto"):
        nivel = "conta" if st_ == "critica_conta" else "depto"
        if nivel == "conta":
            minhas = li[[usuario["id"] in (u or set()) for u in li["uids_conta"]]]
        else:
            minhas = li[li["uid_area"] == usuario["id"]]
        if ver_tudo:
            so = st.toggle("Mostrar só as minhas", key="sim_cr_so", value=not minhas.empty)
            v = minhas if so else li
        else:
            v = minhas
        if v.empty:
            st.info("Você não é dono de nenhuma conta/departamento deste orçamento (cadastro em ⚙️ Cadastros OBZ › 🌳 "
                    "Árvore de donos)." if not ver_tudo else "Nenhuma linha.")
            return
        areas = ["Todos"] + sorted(v["area"].dropna().unique())
        area = st.selectbox("Departamento", areas, key="sim_cr_area")
        if area != "Todos":
            v = v[v["area"] == area]
        st.caption("Deixe a **proposta** vazia para concordar com o calculado. Mudou o valor? Escreva a justificativa." +
                   (" Você vê a crítica que o dono da conta já fez." if nivel == "depto" else ""))
        prop_col, just_col = f"prop_{nivel}", f"just_{nivel}"
        tab = pd.DataFrame({"id": v["id"], "Departamento": v["area"],
                            "Conta": v["conta"] + " · " + v["nome_conta"].fillna(""), "Depto": v["nome_depto"],
                            "Base": v["base_ano"], "Calculado": v["calc_ano"],
                            **({"Proposta da conta": v["prop_conta"], "Justificativa da conta": v["just_conta"]}
                               if nivel == "depto" else {}),
                            "proposta": v[prop_col], "justificativa": v[just_col].fillna("")}).reset_index(drop=True)
        novo = st.data_editor(tab, hide_index=True, key=f"sim_cr_{s['id']}_{nivel}_{area}", **ui.LARGURA,
                              disabled=[c for c in tab.columns if c not in ("proposta", "justificativa")],
                              column_order=[c for c in tab.columns if c != "id"],
                              column_config={"Base": din(format="R$ %.0f"), "Calculado": din(format="R$ %.0f"),
                                             "Proposta da conta": din(format="R$ %.0f"),
                                             "proposta": din("Proposta (R$ ano) ✏️", format="R$ %.0f"),
                                             "justificativa": st.column_config.TextColumn("Justificativa ✏️",
                                                                                          width="large")})
        if st.button("💾 Salvar minha crítica", type="primary", key="sim_cr_s"):
            dados = [{"id": i, "proposta": p, "justificativa": j} for i, p, j in
                     zip(novo["id"], novo["proposta"], novo["justificativa"])]
            try:
                n = sim.salvar_critica(s["id"], nivel, dados, usuario)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(f"Crítica salva ({n} linha(s)).")
                st.rerun()
        feitas = li[li[f"por_{nivel}"].notna()]
        st.caption(f"Progresso da rodada: {len(feitas)} de {len(li)} linhas com crítica registrada · "
                   f"{int(li['proposta'].notna().sum())} com proposta de mudança.")
        return
    com = li[li["proposta"].notna() & ((li["proposta"] - li["calc_ano"]).abs() >= 0.005)]
    if st_ == "revisao_fin" and ver_tudo:
        if com.empty:
            st.success("Nenhuma crítica pediu mudança — pode enviar ao diretor.")
            return
        st.caption("Aprove (vale a proposta) ou reprove (vale o calculado) cada crítica. Reprovar exige justificativa.")
        tab = pd.DataFrame({"id": com["id"], "Departamento": com["area"],
                            "Conta": com["conta"] + " · " + com["nome_conta"].fillna(""), "Depto": com["nome_depto"],
                            "Calculado": com["calc_ano"], "Conta propôs": com["prop_conta"],
                            "Justificativa conta": com["just_conta"], "Depto propôs": com["prop_depto"],
                            "Justificativa depto": com["just_depto"],
                            "decisao": com["decisao"].map({"aprovada": "✔️ Aprovar", "reprovada": "❌ Reprovar"}),
                            "just_fin": com["just_fin"].fillna("")}).reset_index(drop=True)
        novo = st.data_editor(tab, hide_index=True, key=f"sim_rev_{s['id']}", **ui.LARGURA,
                              disabled=[c for c in tab.columns if c not in ("decisao", "just_fin")],
                              column_order=[c for c in tab.columns if c != "id"],
                              column_config={"Calculado": din(format="R$ %.0f"), "Conta propôs": din(format="R$ %.0f"),
                                             "Depto propôs": din(format="R$ %.0f"),
                                             "decisao": st.column_config.SelectboxColumn(
                                                 "Decisão ✏️", options=["✔️ Aprovar", "❌ Reprovar"]),
                                             "just_fin": st.column_config.TextColumn("Justificativa do financeiro ✏️",
                                                                                     width="large")})
        if st.button("💾 Salvar decisões", type="primary", key="sim_rev_s"):
            mapa = {"✔️ Aprovar": "aprovada", "❌ Reprovar": "reprovada"}
            dados = [{"id": i, "decisao": mapa.get(d), "justificativa": j}
                     for i, d, j in zip(novo["id"], novo["decisao"], novo["just_fin"])]
            ui.acao(sim.decidir, s["id"], dados, usuario, sucesso="Decisões salvas.")
        return
    if com.empty:
        st.info("Nenhuma crítica com proposta de mudança." if st_ not in ("rascunho", "aprov_fin")
                else "As críticas abrem depois que o dono do financeiro aprovar a montagem.")
        return
    ui.tabela(pd.DataFrame({
        "Departamento": com["area"], "Conta": com["conta"] + " · " + com["nome_conta"].fillna(""),
        "Calculado": com["calc_ano"].map(_m), "Proposta": com["proposta"].map(_m),
        "Justificativa": (com["just_depto"].fillna(com["just_conta"])).fillna(""),
        "Decisão": com["decisao"].map({"aprovada": "✔️ Aprovada", "reprovada": "❌ Reprovada"}).fillna("⏳"),
        "Financeiro": com["just_fin"].fillna(""), "Final": com["final_ano"].map(_m)}), baixar=f"criticas_{s['ano']}")


# --- 🗓️ Reuniões --------------------------------------------------------------------------------------------------------
def _reunioes(s: dict, usuario: dict) -> None:
    st.caption("Uma reunião estruturada por etapa: a pauta vem pronta com os números do simulador — ajuste, registre "
               "participantes, ata e decisões.")
    etapas = list(sim.REUNIOES)
    c1, c2 = st.columns([1.6, 1])
    etapa = c1.selectbox("Reunião", etapas, index=etapas.index(s["status"]), format_func=sim.REUNIOES.get,
                         key=f"sim_re_et_{s['id']}")
    data = c2.date_input("Data", value=dt.date.today(), format="DD/MM/YYYY", key="sim_re_data")
    li = sim.donos(sim.linhas(s["id"]))
    sugest = {"rascunho": obz.usuarios_papel("fin_dono") + obz.usuarios_papel("plan"),
              "diretor": obz.usuarios_papel("fin_dono") + obz.usuarios_papel("diretor"),
              "ceo": obz.usuarios_papel("fin_dono") + obz.usuarios_papel("diretor") + obz.usuarios_papel("ceo")}
    uids = sugest.get(etapa) or (obz.usuarios_papel("fin_dono") + [u for u in li["uid_area"].dropna().astype(int)])
    with st.form(f"sim_re_f_{s['id']}_{etapa}", border=True):
        part = st.text_input("Participantes", value=_nomes(sorted(set(uids))) if uids else "")
        pauta = st.text_area("Pauta (sugerida pelo sistema)", value=sim.pauta_sugerida(s["id"], etapa), height=220)
        ata = st.text_area("Ata / pontos discutidos", height=110)
        dec = st.text_area("Decisões e ações (responsável e prazo)", height=90)
        if st.form_submit_button("💾 Registrar reunião", type="primary"):
            ui.acao(sim.salvar_reuniao, s["id"], {"etapa": etapa, "data": data.isoformat(), "participantes": part,
                                                  "pauta": pauta, "ata": ata, "decisoes": dec}, usuario,
                    sucesso="Reunião registrada.")
    re = sim.reunioes(s["id"])
    for r in re.itertuples(index=False):
        with st.expander(f"🗓️ {pd.to_datetime(r.data).strftime('%d/%m/%Y')} · {sim.REUNIOES.get(r.etapa, r.etapa)}"):
            st.markdown(f"**Participantes:** {r.participantes or '—'}")
            st.text(r.pauta or "")
            if r.ata:
                st.markdown(f"**Ata:** {r.ata}")
            if r.decisoes:
                st.markdown(f"**Decisões:** {r.decisoes}")
            st.caption(f"Registrada por {r.criado_por} em {r.criado_em}")
            if sim.pode_montar(usuario) and st.button("🗑️ Excluir", key=f"sim_re_del_{r.id}"):
                ui.acao(sim.excluir_reuniao, r.id, sucesso="Reunião excluída.")


# --- 🕒 Histórico -------------------------------------------------------------------------------------------------------
def _historico(s: dict, usuario: dict) -> None:
    h = sim.historico(s["id"])
    if h.empty:
        st.info("Sem histórico.")
    else:
        ui.tabela(pd.DataFrame({"Quando": pd.to_datetime(h["em"]).dt.strftime("%d/%m/%Y %H:%M"),
                                "Etapa": h["etapa"].map(sim.ETAPAS).fillna(h["etapa"]), "Ação": h["acao"],
                                "Quem": h["usuario"], "Comentário": h["comentario"].fillna("")}),
                  baixar=f"historico_simulador_{s['ano']}")
    st.caption(f"Criado por {s['criado_por']} em {s['criado_em']} · base {s['ano_base']}.")
    if sim.pode_montar(usuario) and s["status"] != "publicado":
        with st.expander("🗑️ Excluir este simulador"):
            if st.button("Excluir definitivamente", key=f"sim_del_{s['id']}"):
                ui.acao(sim.excluir, s["id"], usuario, sucesso="Simulador excluído.")
