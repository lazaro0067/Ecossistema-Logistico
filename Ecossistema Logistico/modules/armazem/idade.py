"""📦 Armazém › 📅 Gestão de Idade (FEFO) — quebra de FEFO, qualidade do armazém e vencimentos."""
import pandas as pd
import streamlit as st

from core import arquivos, tema, ui
from repositories import operacoes_repo
from services import idade_service as ids
from services.erros import RegraNegocioError

_TELAS = {"painel": "📊 Painel", "shelf": "🧊 Shelf ao vivo", "picking": "🔁 FEFO Picking", "estoque": "🧱 FEFO Estoque & Contagens",
          "vencimentos": "⏳ Vencimentos", "bases": "📥 Contagens & Cadastros"}


def _n(v, c=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, c)


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _pct(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%".replace(".", ",")


def _d(v) -> str:
    return ids._br(v) if v else "—"


def render(usuario: dict, operacao_id: int) -> None:
    op = operacao_id
    c = ids.contagens(op)
    if c.empty:
        st.info("Suba a primeira contagem com validade (relatório de contagens do WMS) em 📥 Contagens & Cadastros.")
        _bases(usuario, op, None)
        return
    idsc = c["id"].astype(int).tolist()
    rot = {int(r.id): f"📅 {_d(r.data)} · {r.linhas} linhas" for r in c.itertuples()}
    if st.session_state.get("idd_sel") not in idsc:
        st.session_state["idd_sel"] = idsc[0]
    c1, _ = st.columns([1.4, 2])
    cid = int(c1.selectbox("Contagem", idsc, key="idd_sel", format_func=rot.get))
    tela = ui._escolha("idd_tela", list(_TELAS), "painel", pills=True, formatar=_TELAS.get)
    {"painel": _painel, "shelf": lambda u, o, c: render_shelf(u, o, "armazem"), "picking": _picking, "estoque": _estoque, "vencimentos": _vencimentos,
     "bases": _bases}[tela](usuario, op, cid)


# --- tabelas ------------------------------------------------------------------------------------------------------
def _tab_pk(q: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Cód": q["produto"], "Produto": q["descricao"], "Picking": q["picking_end"],
        "Validades no picking": q["picking_validades"], "Estoque mais antigo": q["estoque_validade"].map(_d),
        "Onde (estoque)": q["estoque_end"] + " · " + q["estoque_area"], "Cx no estoque": q["estoque_cx"].map(_n),
        "Dias de diferença": q["dias_dif"], "O que fazer": q["acao"]})


def _tab_cc(q: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Cód": q["produto"], "Produto": q["descricao"], "Saiu a validade": q["validade_saiu"].map(_d),
        "Saiu (cx)": q["saiu_cx"].map(_n), "Ficou parada a validade": q["validade_parada"].map(_d),
        "Parada (cx)": q["parada_cx"].map(_n), "Dias de diferença": q["dias_dif"]})


def _tab_venc(v: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Cód": v["produto"].values, "Produto": v["descricao"].values,
        "Contado (cx)": v["contado_cx"].map(lambda x: _n(x, 1)).values,
        "Vendido desde a contagem": v["vendido_cx"].map(lambda x: _n(x, 1) if x else "—").values,
        "Quantidade atual (cx)": v["qtd_cx"].map(lambda x: _n(x, 1)).values, "Validade": v["validade"].map(_d).values,
        "Dias p/ vencer": v["dias"].values, "Valor": v["valor"].map(_m).values,
        "Linear (cx/dia)": v["linear"].map(lambda x: _n(x, 1)).values,
        "Dias limite": v["dias_limite"].values, "Dias disponíveis": v["dias_disp"].values,
        "Sai pela linear (cx)": v["sai_cx"].map(lambda x: _n(x, 1)).values,
        "Previsão de vencer (cx)": v["vencer_cx"].map(lambda x: _n(x, 1) if pd.notna(x) and x else "—").values,
        "Previsão de vencer (R$)": v["vencer_valor"].map(lambda x: _m(x) if pd.notna(x) and x else "—").values,
        "Precisa vender (cx/dia)": v["meta_dia"].map(lambda x: "passou do limite" if x == float("inf")
                                                     else _n(x, 1)).values,
        "Última puxada": v["ultima_puxada"].map(_d).values, "Situação": v["situacao"].values,
        "Endereços": v["enderecos"].values})


# --- 📊 Painel ------------------------------------------------------------------------------------------------------
def _painel(usuario: dict, op: int, cid: int) -> None:
    q = ids.qualidade(op, cid)
    pk = ids.fefo_picking(cid)
    cc = ids.fefo_contagens(q["anterior"], cid) if q["anterior"] else pd.DataFrame()
    v = ids.vencimentos(op, cid)
    faixa = {f: v[v["faixa"] == f] for f in ids.FAIXAS}
    risco = v[v["vencer_cx"] > 0]
    pct = q["pct"]
    tema.kpis([
        {"titulo": "Qualidade do armazém (FEFO)", "valor": _pct(pct), "icone": "🏅",
         "status": "neutro" if pct is None else "bom" if pct >= 98 else "atencao" if pct >= 95 else "critico",
         "detalhe": f"{_n(q['produtos'] - q['quebras'])} de {_n(q['produtos'])} produtos sem quebra"},
        {"titulo": "Quebra FEFO no picking", "valor": _n(q["quebra_picking"]), "icone": "🔁",
         "status": "critico" if q["quebra_picking"] else "bom", "detalhe": "estoque mais antigo que o picking",
         "dados": _tab_pk(pk) if len(pk) else None},
        {"titulo": "Quebra contagem × contagem", "valor": _n(q["quebra_contagem"]) if q["anterior"] else "—",
         "icone": "🔄", "status": "critico" if q["quebra_contagem"] else "bom" if q["anterior"] else "neutro",
         "detalhe": "saiu o mais novo primeiro" if q["anterior"] else "suba a 2ª contagem para comparar",
         "dados": _tab_cc(cc) if len(cc) else None},
    ], key=f"kp_idd_q_{cid}")
    cards = []
    for f, rot in ids.FAIXAS.items():
        x = faixa[f]
        if f == "vencido" and x.empty:
            continue
        cards.append({"titulo": rot, "valor": f"{_n(x['qtd_cx'].sum())} cx", "icone": "⏳",
                      "status": "critico" if f in ("vencido", "30") and len(x) else "atencao" if len(x) else "bom",
                      "detalhe": f"{_m(x['valor'].sum())} · {x['produto'].nunique()} produto(s)",
                      "dados": _tab_venc(x) if len(x) else None})
    cards.append({"titulo": "Previsão de vencer", "valor": _m(risco["vencer_valor"].sum()), "icone": "🧊",
                  "status": "critico" if len(risco) else "bom",
                  "detalhe": f"{_n(risco['vencer_cx'].sum())} cx · {risco['produto'].nunique()} produto(s) — não comprar",
                  "dados": _tab_venc(risco) if len(risco) else None})
    tema.kpis(cards, key=f"kp_idd_v_{cid}")
    tema.secao("🛣️ Por rua / área")
    r = ids.resumo_ruas(cid)
    if not r.empty:
        ui.tabela(pd.DataFrame({"Rua / área": r["area"], "Tipo": r["tipo"].map(ids.TIPOS_AREA),
                                "Endereços": r["enderecos"], "Produtos": r["produtos"],
                                "Caixas": r["caixas"].map(_n), "Validade mais antiga": r["validade_min"].map(_d),
                                "Validade mais nova": r["validade_max"].map(_d),
                                "Produtos com validades misturadas": r["produtos_mistos"]}), baixar=f"idade_ruas_{cid}")


# --- 🔁 Picking ---------------------------------------------------------------------------------------------------
def _picking(usuario: dict, op: int, cid: int) -> None:
    pk = ids.fefo_picking(cid)
    tema.secao("🔁 Quebra de FEFO no picking",
               "O estoque (pulmão) tem validade mais antiga do que o que está no picking: o picking vai sair com "
               "produto mais novo. Corrija abastecendo o picking com a validade mais antiga.")
    if pk.empty:
        st.success("Nenhuma quebra de FEFO no picking nesta contagem. 👏")
        return
    st.error(f"{len(pk)} produto(s) com quebra de FEFO no picking.")
    ui.tabela(_tab_pk(pk), baixar=f"fefo_picking_{cid}")
    if not operacoes_repo.e_consolidada(op) and st.button("📣 Pedir correção aos responsáveis", type="primary",
                                                          key="idd_pedir"):
        ui.acao(ids.pedir_correcao, op, cid, usuario,
                sucesso="Pedido de correção enviado para os responsáveis do armazém.")


# --- 🧱 Estoque & contagens -----------------------------------------------------------------------------------------
def _estoque(usuario: dict, op: int, cid: int) -> None:
    tema.secao("🧱 FEFO estoque × estoque — por rua",
               "Produtos com mais de uma validade no estoque. A 1ª validade é a que deve sair primeiro — veja em que "
               "rua e endereço ela está.")
    e = ids.estoque_por_rua(cid)
    if e.empty:
        st.success("Nenhum produto com validades misturadas no estoque.")
    else:
        ruas = ["__todas__"] + sorted({x for s in e["ruas"] for x in s.split(", ")})
        rua = st.selectbox("Rua / área", ruas, key="idd_rua", format_func=lambda x: "Todas" if x == "__todas__" else x)
        x = e if rua == "__todas__" else e[e["produto"].isin(e.loc[e["ruas"].str.contains(rua, regex=False),
                                                                     "produto"])]
        ui.tabela(pd.DataFrame({
            "Cód": x["produto"], "Produto": x["descricao"],
            "Ordem de saída": x["ordem"].map(lambda o: "1ª — sai primeiro" if o == 1 else f"{o}ª"),
            "Validade": x["validade"].map(_d), "Rua / área": x["ruas"], "Endereços": x["enderecos"],
            "Caixas": x["qtd_cx"].map(_n)}), baixar=f"fefo_estoque_{cid}")
    tema.secao("🔄 Contagem × contagem",
               "Compara com a contagem anterior: se saiu uma validade mais nova enquanto a mais antiga ficou parada, "
               "houve quebra de FEFO na operação.")
    c = ids.contagens(op)
    outras = [int(i) for i, d in zip(c["id"], c["data"]) if int(i) != cid]
    if not outras:
        st.info("Suba a 2ª contagem para comparar.")
        return
    ant = ids.anterior(op, cid)
    rot = {int(r.id): f"📅 {_d(r.data)}" for r in c.itertuples()}
    ref = st.selectbox("Comparar com", outras, index=outras.index(ant) if ant in outras else 0, key=f"idd_ant_{cid}",
                       format_func=rot.get)
    a, b = (ref, cid) if str(c.set_index("id").loc[ref, "data"]) <= str(c.set_index("id").loc[cid, "data"]) \
        else (cid, ref)
    q = ids.fefo_contagens(a, b)
    if q.empty:
        st.success(f"Nenhuma quebra de FEFO entre {rot[a][2:]} e {rot[b][2:]}. 👏")
    else:
        st.error(f"{q['produto'].nunique()} produto(s) com quebra de FEFO entre {rot[a][2:]} e {rot[b][2:]}.")
        ui.tabela(_tab_cc(q), baixar=f"fefo_contagens_{a}_{b}")


# --- ⏳ Vencimentos ---------------------------------------------------------------------------------------------------
def _vencimentos(usuario: dict, op: int, cid: int) -> None:
    v = ids.vencimentos(op, cid)
    cont = {f: int((v["faixa"] == f).sum()) for f in ids.FAIXAS}
    f = ui._escolha("idd_faixa", ["30", "60", "90", "vencido", "risco"], "30", pills=True,
                    formatar=lambda k: f"{ids.FAIXAS[k]} ({cont[k]})" if k in ids.FAIXAS
                    else f"🧊 Com previsão de vencer ({int((v['vencer_cx'] > 0).sum())})")
    x = v[v["vencer_cx"] > 0] if f == "risco" else v[v["faixa"] == f]
    padrao, _ = ids.limites(op)
    st.caption(f"Uma linha por produto × validade (todas as áreas). Quantidade em caixa (unidade de venda) · Valor = "
               f"custo do último 02.05.02 · Linear = venda/dia do Ressuprimento (sem ela, média de 30 dias da 03.02.37) "
               f"· Dias disponíveis = dias p/ vencer − dias limite (padrão {padrao}) · Previsão de vencer = o que a "
               f"linear não vende até lá (as validades mais antigas saem primeiro) · Última puxada = 03.02.37 compra.")
    if x.empty:
        st.success("Nada nesta faixa. 👏")
        return
    a, b, c_ = st.columns(3)
    a.metric("Caixas", _n(x["qtd_cx"].sum()))
    b.metric("Valor", _m(x["valor"].sum()))
    c_.metric("Previsão de vencer", _m(x["vencer_valor"].sum()))
    ui.tabela(_tab_venc(x.sort_values(["dias", "produto"])), baixar=f"vencimentos_{f}_{cid}")


# --- 🧊 Shelf ao vivo (Armazém, Ressuprimento e Vendas) -------------------------------------------------------------
_CSS_SHELF = """
<style>
.shf-top {border-radius: 14px; padding: .9rem 1.1rem; margin: .2rem 0 .8rem 0; color: #fff;
          background: linear-gradient(120deg, #0B1F3A 0%, #1d4f91 60%, #2a78d6 100%);}
.shf-top b {font-size: 1.15rem;} .shf-top span {opacity: .85; font-size: .88rem; display: block; margin-top: .15rem;}
.shf-card {border: 1px solid rgba(120,130,150,.25); border-left: 6px solid var(--c); border-radius: 12px;
           padding: .7rem .9rem; margin-bottom: .7rem; background: rgba(127,127,127,.04);}
.shf-card .t {font-weight: 700; font-size: 1rem;} .shf-card .s {font-size: .8rem; opacity: .75;}
.shf-tag {display: inline-block; font-size: .72rem; font-weight: 700; padding: .1rem .5rem; border-radius: 99px;
          background: var(--c); color: #fff; margin-left: .3rem; vertical-align: middle;}
.shf-row {display: flex; gap: .6rem; margin: .55rem 0 .35rem 0; flex-wrap: wrap;}
.shf-row div {flex: 1 1 90px; min-width: 90px;}
.shf-row small {display: block; font-size: .7rem; opacity: .7; text-transform: uppercase; letter-spacing: .02em;}
.shf-row b {font-size: 1.12rem;}
.shf-bar {height: 9px; border-radius: 99px; background: rgba(127,127,127,.18); overflow: hidden;}
.shf-bar i {display: block; height: 100%; background: var(--c);}
.shf-foot {font-size: .78rem; opacity: .8; margin-top: .3rem;}
</style>
"""
_COR_URG = {"⛔ Vencido": "#6b1d1d", "🔴 Crítico": "#e34948", "🟠 Atenção": "#f08c2e", "🟡 Monitorar": "#d4a72c"}
_PUBLICO = {
    "armazem": ("🧊 Shelf ao vivo", "Saldo da última contagem atualizado com as vendas de cada dia (03.02.37)."),
    "ressup": ("🧊 Risco de Shelf — não comprar", "Estes produtos não vão sair a tempo com a venda atual. Segure novas "
               "puxadas até o risco zerar."),
    "vendas": ("🎯 Foco de venda — produtos com risco de vencer", "Ajuste a venda: a meta por dia é o que precisa sair "
               "para a validade não vencer no armazém."),
}


def _card_shelf(r, publico: str, valor: bool = True) -> str:
    e = tema._e
    cor = _COR_URG.get(r.urgencia, "#888")
    meta = r.meta_dia
    meta_txt = "passou do limite" if meta == float("inf") else f"{_n(meta, 1)} cx/dia"
    pct = 0 if pd.isna(r.pct_meta) else float(r.pct_meta)
    lin = "sem linear" if pd.isna(r.linear) else f"{_n(r.linear, 1)} cx/dia"
    extra = {"armazem": f"📍 {e(str(r.enderecos)[:60])}",
             "ressup": f"🛒 Última puxada: {_d(r.ultima_puxada)} · ⛔ não comprar",
             "vendas": f"💪 Vender mais {_n(r.falta_dia, 1)} cx/dia" if r.falta_dia and r.falta_dia != float("inf")
             else "💪 Manter o ritmo de venda"}[publico]
    dias = "vencido" if r.dias < 0 else f"{int(r.dias)} dias"
    return (f'<div class="shf-card" style="--c:{cor}"><div class="t">{e(r.produto)} · {e(str(r.descricao)[:48])}'
            f'<span class="shf-tag">{e(r.urgencia)}</span></div>'
            f'<div class="s">Validade {_d(r.validade)} · {dias} · vendido desde a contagem {_n(r.vendido_cx)} cx</div>'
            f'<div class="shf-row"><div><small>Estoque em risco</small><b>{_n(r.estoque_risco)} cx</b></div>'
            f'<div><small>Precisa vender</small><b>{meta_txt}</b></div>'
            f'<div><small>Vende hoje</small><b>{lin}</b></div>'
            f'<div><small>Vai vencer</small><b>{_n(r.vencer_cx)} cx' + (f' · {_m(r.vencer_valor)}' if valor else '')
            + '</b></div></div>'
            f'<div class="shf-bar"><i style="width:{pct:.0f}%"></i></div>'
            f'<div class="shf-foot">Ritmo atual = {pct:.0f}% do necessário · {extra}</div></div>')


def foco_portal(operacao_id: int) -> None:
    """Portal Comercial (RN no celular): produtos com risco de vencer para priorizar na venda."""
    try:
        r = ids.risco_shelf(operacao_id)
    except Exception:  # noqa: BLE001 — o portal nunca quebra por causa disso
        return
    r = r[r["dias"] >= 0] if not r.empty else r
    if r.empty:
        return
    st.markdown(_CSS_SHELF, unsafe_allow_html=True)
    with st.expander(f"🎯 Venda prioritária — {len(r)} produto(s) com risco de vencer", expanded=False):
        st.caption("Estes produtos precisam vender mais para não vencer no armazém. Ofereça primeiro!")
        for row in r.head(15).itertuples():
            st.markdown(_card_shelf(row, "vendas", valor=False), unsafe_allow_html=True)


def render_shelf(usuario: dict, operacao_id: int, publico: str = "armazem") -> None:
    st.markdown(_CSS_SHELF, unsafe_allow_html=True)
    tit, sub = _PUBLICO[publico]
    sv = ids.situacao_viva(operacao_id)
    if not sv:
        st.info("Ainda não há contagem com validade — suba em 📦 Armazém › 📅 Gestão de Idade.")
        return
    ate = sv.get("vendas_ate")
    st.markdown(f'<div class="shf-top"><b>{tit}</b><span>{sub}</span><span>📅 Contagem de {_d(sv["contagem"])} · '
                + (f"🔄 vendas baixadas até {_d(ate)}" if ate else "🔄 ainda sem vendas depois da contagem")
                + ' · atualiza a cada 03.02.37 de vendas subida</span></div>', unsafe_allow_html=True)
    r = ids.risco_shelf(operacao_id)
    if r.empty:
        st.success("Nenhum produto com risco de vencer. 👏")
        return
    urg = {u: r[r["urgencia"] == u] for u in _COR_URG}
    tema.kpis([
        {"titulo": "Valor em risco", "valor": _m(r["vencer_valor"].sum()), "icone": "💸", "status": "critico",
         "detalhe": f"{_n(r['vencer_cx'].sum())} cx vão vencer com a venda atual"},
        {"titulo": "Produtos em risco", "valor": _n(len(r)), "icone": "🧊", "status": "critico",
         "detalhe": f"{len(urg['🔴 Crítico'])} críticos (até 30 dias para vender)"},
        {"titulo": "Vender a mais por dia", "valor": f"{_n(r.loc[r['falta_dia'] != float('inf'), 'falta_dia'].sum(), 1)} cx",
         "icone": "💪", "status": "atencao", "detalhe": "soma do que falta no ritmo de venda"},
        {"titulo": "Vendido desde a contagem", "valor": f"{_n(r['vendido_cx'].sum())} cx", "icone": "🔄",
         "status": "info", "detalhe": "destes produtos"},
        {"titulo": "Vencidos", "valor": _n(len(urg["⛔ Vencido"])), "icone": "⛔",
         "status": "critico" if len(urg["⛔ Vencido"]) else "bom"},
    ], key=f"kp_shelf_{publico}")
    conta = {u: len(x) for u, x in urg.items()}
    f = ui._escolha(f"shf_f_{publico}", ["todos", *[u for u in _COR_URG if conta[u]]], "todos", pills=True,
                    formatar=lambda k: f"Todos ({len(r)})" if k == "todos" else f"{k} ({conta[k]})")
    x = r if f == "todos" else urg[f]
    top = x.sort_values("vencer_valor", ascending=False).head(10)
    if top["vencer_valor"].notna().any():
        from core import graficos

        graficos.mostrar(graficos.barras_h([f"{p} · {str(d)[:24]}" for p, d in zip(top["produto"], top["descricao"])],
                                           top["vencer_valor"].fillna(0).tolist(),
                                           cores=[_COR_URG.get(u, "#888") for u in top["urgencia"]],
                                           titulo="Maiores valores em risco (R$)"), key=f"g_shelf_{publico}_{f}")
    n = st.session_state.get(f"shf_n_{publico}", 12)
    cols = st.columns(2)
    for k, row in enumerate(x.head(n).itertuples()):
        cols[k % 2].markdown(_card_shelf(row, publico), unsafe_allow_html=True)
    if len(x) > n and st.button(f"Mostrar mais ({len(x) - n})", key=f"shf_mais_{publico}"):
        st.session_state[f"shf_n_{publico}"] = n + 24
        st.rerun()
    with st.expander("📋 Tabela completa"):
        ui.tabela(pd.DataFrame({
            "Urgência": x["urgencia"], "Cód": x["produto"], "Produto": x["descricao"],
            "Validade": x["validade"].map(_d), "Dias p/ vencer": x["dias"],
            "Estoque em risco (cx)": x["estoque_risco"].map(_n), "Vendido desde a contagem (cx)": x["vendido_cx"].map(_n),
            "Precisa vender (cx/dia)": x["meta_dia"].map(lambda v: "passou do limite" if v == float("inf") else _n(v, 1)),
            "Vende hoje (cx/dia)": x["linear"].map(lambda v: _n(v, 1)),
            "Vai vencer (cx)": x["vencer_cx"].map(_n), "Vai vencer (R$)": x["vencer_valor"].map(_m),
            "Última puxada": x["ultima_puxada"].map(_d), "Endereços": x["enderecos"]}), baixar=f"shelf_{publico}")


def render_risco_shelf(usuario: dict, operacao_id: int) -> None:
    render_shelf(usuario, operacao_id, "ressup")


def render_foco_vendas(usuario: dict, operacao_id: int) -> None:
    render_shelf(usuario, operacao_id, "vendas")


# --- 📥 Bases & cadastros ------------------------------------------------------------------------------------------
def _bases(usuario: dict, op: int, cid: int | None) -> None:
    consol = operacoes_repo.e_consolidada(op)
    with st.container(border=True):
        st.markdown("**📥 Subir contagem com validade (relatório de contagens do WMS)**")
        st.caption("C = Tarefa (rua/área) · D = endereço · I = produto · K = quantidade · L = unidade (PL, LST, CX, "
                   "UN) · M = validade aferida. A data da contagem vem da finalização. Subir de novo a mesma data "
                   "substitui. Da 2ª contagem em diante o sistema compara e acha quebra de FEFO.")
        v = st.session_state.get("idd_up_v", 0)
        arq = st.file_uploader("Contagem", type=arquivos.FORMATOS, key=f"idd_up_{v}", label_visibility="collapsed",
                               disabled=consol)
        if arq is not None and st.button("Gravar contagem", type="primary", key="idd_gravar"):
            try:
                a2 = arquivos.preparar(arq)
                r = ids.importar(op, a2.getvalue(), a2.name, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(f"Contagem de {_d(r['data'])}: {r['linhas']} linhas · {r['produtos']} produtos"
                          + (" (substituiu a do mesmo dia)" if r["substituiu"] else "")
                          + (f" · {r['sem_validade']} sem validade" if r["sem_validade"] else "")
                          + (f" · {r['sem_conversao']} sem conversão na 01.11" if r["sem_conversao"] else "") + ".")
                st.session_state["idd_up_v"] = v + 1
                st.session_state["idd_sel"] = r["id"]
                st.rerun()
    c = ids.contagens(op)
    if not c.empty:
        tema.secao("📚 Contagens subidas")
        ui.tabela(pd.DataFrame({"Data": c["data"].map(_d), "Linhas": c["linhas"], "Arquivo": c["arquivo"],
                                "Por": c["criado_por"], "Em": c["criado_em"]}), baixar=False)
        if not consol:
            from core.auth import e_master

            rot = {int(r.id): f"📅 {_d(r.data)}" for r in c.itertuples()}
            x1, x2 = st.columns([1.4, 1])
            sel = x1.selectbox("Excluir contagem", list(rot), format_func=rot.get, key="idd_exc_sel")
            x2.write("")
            if e_master(usuario) and x2.button("🗑️ Excluir", key="idd_exc"):
                ui.acao(ids.excluir_contagem, sel, sucesso="Contagem excluída.")
    tema.secao("🛣️ Áreas: picking ou estoque",
               "O sistema separa pelo nome da área (com “Picking” = picking). Ajuste se precisar.")
    ar = ids.areas(op)
    if ar.empty:
        st.caption("As áreas aparecem depois da primeira contagem.")
    else:
        ed = st.data_editor(pd.DataFrame({"Área": ar["area"], "Tipo": ar["tipo"].fillna("estoque")}), hide_index=True,
                            key="idd_areas_ed", disabled=["Área"] if not consol else True, **ui.LARGURA,
                            column_config={"Tipo": st.column_config.SelectboxColumn(
                                "Tipo", options=list(ids.TIPOS_AREA), required=True)})
        if not consol and st.button("💾 Salvar áreas", key="idd_areas_salvar"):
            ui.acao(ids.salvar_areas, op, [{"area": a, "tipo": t} for a, t in zip(ed["Área"], ed["Tipo"])],
                    sucesso="Áreas salvas.")
    tema.secao("📆 Dias limite (disponibilidade)",
               "Quantos dias antes de vencer o produto precisa ter saído. Os dias disponíveis para vender = dias para "
               "vencer − dias limite; o que a linear não vender nesse prazo vira previsão de vencer.")
    padrao, exc = ids.limites(op)
    pad = st.number_input("Dias limite padrão (todos os produtos)", min_value=0, max_value=365, value=int(padrao),
                          step=1, key="idd_lim_pad", disabled=consol)
    base = pd.DataFrame({"Cód produto": exc["produto"].astype(str), "Dias limite": exc["dias"]}) if not exc.empty \
        else pd.DataFrame({"Cód produto": pd.Series(dtype=str), "Dias limite": pd.Series(dtype="Int64")})
    st.caption("Exceções por produto (opcional):")
    ed2 = st.data_editor(base, num_rows="dynamic", hide_index=True, key="idd_lim_ed", disabled=consol, **ui.LARGURA)
    if not consol and st.button("💾 Salvar dias limite", key="idd_lim_salvar"):
        ui.acao(ids.salvar_limites, op, int(pad),
                [{"produto": p, "dias": d} for p, d in zip(ed2["Cód produto"], ed2["Dias limite"])],
                sucesso="Dias limite salvos.")
