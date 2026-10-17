"""Armazém › 🎯 Acuracidade de Estoque.

📦 Inventário mensal: 02.05.02 (disponível = base do sistema) × contagens do WMS por área (1ª e 2ª contagem por
usuário) → divergências vão para recontagem no app → conciliação → resultado por produto e por área.
🔄 Conciliação diária: em montagem.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import arquivos, graficos, tema, tempo, ui
from repositories import operacoes_repo
from services import inventario_service as inv
from services.erros import RegraNegocioError

_PASTAS = {"mensal": "📦 Inventário mensal", "diaria": "🔄 Conciliação diária"}
_TELAS = {"painel": "📊 Painel", "enderecos": "📍 Por endereço", "recontagem": "🔁 Recontagem", "resultado": "📋 Resultado", "bases": "📥 Bases",
          "cadastros": "⚙️ Cadastros"}
VERDE, VERMELHO, AMARELO, AZUL, ROXO, CINZA = "#1baf7a", "#e34948", "#eda100", "#2a78d6", "#7c5cd6", "#9aa4b2"
_COR = {"ok": VERDE, "divergente": VERMELHO, "pendente": AMARELO, "recontado": ROXO, "conciliado": AZUL,
        "aguardando": CINZA, "sem_conversao": "#c7ccd4"}


def _n(v, c=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, c)


def _pct(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%".replace(".", ",")


def _q(un, fator) -> str:
    return inv.cx_un(un, fator)


def render(usuario: dict, operacao_id: int) -> None:
    pasta = ui._escolha("acu_pasta", list(_PASTAS), "mensal", formatar=_PASTAS.get)
    if pasta == "diaria":
        tema.secao("🔄 Conciliação diária", "Contagem cíclica do dia × sistema — vamos montar depois do inventário "
                                           "mensal.")
        st.info("🚧 Em montagem. Comece pelo 📦 Inventário mensal.")
        return
    _mensal(usuario, operacao_id)


# --- seleção / criação do inventário ------------------------------------------------------------------------------------
def _mensal(usuario: dict, op: int) -> None:
    invs = inv.inventarios(op)
    c1, c2 = st.columns([2.2, 1])
    with c2.popover("➕ Novo inventário"):
        meses = [str(pd.Period(tempo.hoje(), "M") - k) for k in range(0, 13)]
        mes = st.selectbox("Mês", meses, format_func=ui.nome_mes, key="inv_novo_mes")
        nome = st.text_input("Nome (opcional)", key="inv_novo_nome", placeholder=f"Inventário {ui.nome_mes(mes)}")
        if st.button("Criar inventário", type="primary", key="inv_criar"):
            try:
                novo = inv.criar(op, mes, nome, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["inv_sel"] = novo
                st.session_state["inv_tela"] = st.session_state["inv_tela__ultima"] = "bases"
                ui.avisar("Inventário criado — suba o 02.05.02 e as contagens.")
                st.rerun()
    if invs.empty:
        c1.info("Nenhum inventário ainda. Clique em **➕ Novo inventário** para começar.")
        return
    ids = invs["id"].astype(int).tolist()
    rot = {int(r.id): f"{ui.nome_mes(r.mes)} · {r.nome} · {'🟢 aberto' if r.status == 'aberto' else '🔒 fechado'}"
           for r in invs.itertuples()}
    if st.session_state.get("inv_sel") not in ids:
        st.session_state["inv_sel"] = ids[0]
    inv_id = c1.selectbox("Inventário", ids, key="inv_sel", format_func=rot.get, label_visibility="collapsed")
    tela = ui._escolha("inv_tela", list(_TELAS), "painel", pills=True, formatar=_TELAS.get)
    {"painel": _painel, "enderecos": _enderecos, "recontagem": _recontagem, "resultado": _resultado, "bases": _bases,
     "cadastros": _cadastros}[tela](usuario, op, int(inv_id))


# --- 📊 Painel ---------------------------------------------------------------------------------------------------------
def _dif_cxun(d: pd.DataFrame) -> list[str]:
    return [_q(b - a, f) if pd.notna(a) and pd.notna(b) else "—"
            for a, b, f in zip(d["c1_un"], d["c2_un"], d["fator"])]


def _tab_div(d: pd.DataFrame, area: bool = True) -> pd.DataFrame:
    """Uma linha por endereço × produto: quem contou, quanto contou (do jeito que contou) e a diferença."""
    t = pd.DataFrame({
        "Área": d["area"], "Endereço": d["endereco"], "Cód": d["produto"], "Produto": d["descricao"],
        "Contador 1": d["u1"].fillna("—"), "Contagem 1": d["t1"].fillna(""),
        "Contador 2": d["u2"].fillna("— (falta)"), "Contagem 2": d["t2"].fillna("").replace("", "—"),
        "Diferença": d["dif_txt"].replace("", "—"), "Diferença (cx/un)": _dif_cxun(d),
        "Situação": d["status"].map(inv.STATUS)}).reset_index(drop=True)
    return t if area else t.drop(columns="Área")


def _painel(usuario: dict, op: int, inv_id: int) -> None:
    conc = inv.conciliacao(inv_id)
    if conc.empty:
        st.info("Ainda não há contagens neste inventário. Suba o 02.05.02 e o relatório de contagens do WMS em "
                "**📥 Bases**.")
        return
    cont = conc["status"].value_counts()
    div = conc[conc["status"] == "divergente"]
    comparados = len(conc) - int(cont.get("aguardando", 0)) - int(cont.get("sem_conversao", 0))
    acerto = int(cont.get("ok", 0)) / comparados * 100 if comparados else None
    sem = conc[conc["sem_conv"].fillna(False).astype(bool)]
    tema.kpis([
        {"titulo": "Endereços contados", "valor": _n(conc["endereco"].nunique()), "icone": "📍", "status": "info",
         "detalhe": f"{_n(conc['area'].nunique())} áreas · {_n(len(conc))} itens × endereço"},
        {"titulo": "Acerto 1ª × 2ª contagem", "valor": _pct(acerto), "icone": "🎯",
         "status": "bom" if (acerto or 0) >= 98 else "atencao" if (acerto or 0) >= 95 else "critico",
         "detalhe": f"{_n(cont.get('ok', 0))} bateram de {_n(comparados)}"},
        {"titulo": "Para recontagem", "valor": _n(len(div)), "icone": "⚠️",
         "status": "critico" if len(div) else "bom", "detalhe": "1ª e 2ª contagem diferentes",
         "dados": _tab_div(div) if len(div) else None},
        {"titulo": "No app / para conciliar", "valor": f"{_n(cont.get('pendente', 0))} / {_n(cont.get('recontado', 0))}",
         "icone": "📱", "status": "atencao" if cont.get("recontado", 0) else "info",
         "detalhe": f"{_n(cont.get('conciliado', 0))} já conciliados"},
        {"titulo": "Falta 2ª contagem", "valor": _n(cont.get("aguardando", 0)), "icone": "⏳",
         "status": "atencao" if cont.get("aguardando", 0) else "bom", "detalhe": "áreas com um usuário só",
         "dados": _tab_div(conc[conc["status"] == "aguardando"]) if cont.get("aguardando", 0) else None},
        {"titulo": "Sem conversão", "valor": _n(sem["produto"].nunique()), "icone": "❔",
         "status": "atencao" if len(sem) else "bom", "detalhe": "compara na unidade contada; para o sistema "
                                                                "falta a 01.11 (⚙️ Conversões)",
         "dados": _tab_div(sem) if len(sem) else None},
    ], key="kp_inv_geral")
    pa = inv.painel_areas(conc, op)
    tema.secao("🗺️ Por área", "Clique na área para ver os itens que deram diferença e mandar para recontagem.")
    cards = []
    for r in pa.itertuples():
        n_div = int(r.divergente)
        cards.append({"titulo": f"{r.nome}"[:34], "valor": f"{n_div} p/ recontar" if n_div else "ok",
                      "icone": "⚠️" if n_div else "✅", "status": "critico" if n_div else (
                          "atencao" if r.aguardando or r.sem_conversao else "bom"),
                      "detalhe": f"{r.armazem} · {int(r.end_validados)}/{int(r.enderecos)} end. validados · "
                                 f"acerto {_pct(r.acerto)}",
                      "ao_clicar": (lambda a=r.area: st.session_state.update(inv_area=a))})
    tema.kpis(cards, key=f"kp_inv_areas_{inv_id}")
    g = pa.iloc[::-1]
    fig = go.Figure()
    for s in ("ok", "conciliado", "recontado", "pendente", "divergente", "aguardando", "sem_conversao"):
        if s in g and g[s].sum():
            fig.add_bar(y=g["nome"], x=g[s], name=inv.STATUS[s], orientation="h", marker_color=_COR[s])
    fig.update_layout(barmode="stack")
    graficos.mostrar(graficos._layout(fig, "Itens × endereço por área", max(320, 28 * len(g) + 110)),
                     key="inv_g_areas",
                     detalhe=lambda rot: _tab_div(conc[(conc["area"].map(dict(zip(pa["area"], pa["nome"]))) == rot)
                                                       & (conc["status"] != "ok")]))
    _enviar(usuario, inv_id, conc, pa)


def _enviar(usuario: dict, inv_id: int, conc: pd.DataFrame, pa: pd.DataFrame) -> None:
    nomes = dict(zip(pa["area"], pa["nome"]))
    opcs = ["__todas__"] + pa.loc[pa["divergente"] > 0, "area"].tolist()
    if st.session_state.get("inv_area") not in opcs:
        st.session_state["inv_area"] = "__todas__"
    tema.secao("📨 Mandar para recontagem", "Analise e desmarque o que não precisa recontar. Os marcados vão para o "
                                          "app, com a área e o endereço de cada produto.")
    area = st.selectbox("Área", opcs, key="inv_area",
                        format_func=lambda a: "Todas as áreas com diferença" if a == "__todas__" else nomes.get(a, a))
    d = conc[conc["status"] == "divergente"]
    if area != "__todas__":
        d = d[d["area"] == area]
    if d.empty:
        st.success("Nenhum item com diferença entre a 1ª e a 2ª contagem aqui. 👏")
        return
    vis = _tab_div(d).drop(columns="Situação")
    vis.insert(0, "Recontar", True)
    ed = st.data_editor(vis, hide_index=True, key=f"inv_ed_env_{inv_id}_{area}", **ui.LARGURA,
                        disabled=[c for c in vis.columns if c != "Recontar"],
                        column_config={"Recontar": st.column_config.CheckboxColumn("Recontar", default=True)})
    marcados = d.reset_index(drop=True)[ed["Recontar"].fillna(False).astype(bool).values]
    if st.button(f"📨 Enviar {len(marcados)} item(ns) para recontagem", type="primary", key="inv_enviar",
                 disabled=marcados.empty):
        ui.acao(inv.enviar_recontagem, inv_id, marcados, usuario.get("nome", ""),
                sucesso=f"{len(marcados)} item(ns) enviados para o app de recontagem.")


# --- 📍 Por endereço ----------------------------------------------------------------------------------------------------
def _enderecos(usuario: dict, op: int, inv_id: int) -> None:
    conc = inv.conciliacao(inv_id)
    if conc.empty:
        st.info("Ainda não há contagens neste inventário — suba em 📥 Bases.")
        return
    pe = inv.por_endereco(conc)
    nomes = dict(zip(*[inv.painel_areas(conc, op)[c] for c in ("area", "nome")]))
    cont = pe["situacao"].value_counts()
    tema.kpis([
        {"titulo": "Endereços", "valor": _n(len(pe)), "icone": "📍", "status": "info",
         "detalhe": f"{_n(pe['area'].nunique())} áreas"},
        {"titulo": "Validados", "valor": _n(cont.get("validado", 0)), "icone": "✅", "status": "bom",
         "detalhe": _pct(cont.get("validado", 0) / len(pe) * 100) + " dos endereços"},
        {"titulo": "Com divergência", "valor": _n(cont.get("divergente", 0)), "icone": "⚠️",
         "status": "critico" if cont.get("divergente", 0) else "bom", "detalhe": "1ª ≠ 2ª contagem"},
        {"titulo": "Em recontagem / conciliar", "valor": f"{_n(cont.get('recontagem', 0))} / "
                                                         f"{_n(cont.get('conciliar', 0))}", "icone": "📨",
         "status": "atencao" if cont.get("conciliar", 0) else "info"},
        {"titulo": "Só 1 contagem", "valor": _n(cont.get("aguardando", 0)), "icone": "⏳",
         "status": "atencao" if cont.get("aguardando", 0) else "bom", "detalhe": "falta a 2ª contagem do endereço"},
    ], key="kp_inv_end")
    c1, c2, c3 = st.columns([1.4, 1.2, 1.4])
    areas_ = ["__todas__"] + sorted(pe["area"].unique(), key=lambda a: nomes.get(a, a))
    area = c1.selectbox("Área", areas_, key="inv_end_area",
                        format_func=lambda a: "Todas as áreas" if a == "__todas__" else nomes.get(a, a))
    sit = c2.selectbox("Situação", ["__todas__", *inv.END_STATUS], key="inv_end_sit",
                       format_func=lambda s: "Todas" if s == "__todas__" else inv.END_STATUS[s])
    busca = c3.text_input("Buscar endereço ou produto", key="inv_end_busca").strip().upper()
    v = pe if area == "__todas__" else pe[pe["area"] == area]
    if sit != "__todas__":
        v = v[v["situacao"] == sit]
    if busca:
        tem_prod = set(conc.loc[conc["produto"].astype(str).str.contains(busca, regex=False)
                                | conc["descricao"].fillna("").str.upper().str.contains(busca, regex=False),
                                "endereco"])
        v = v[v["endereco"].astype(str).str.upper().str.contains(busca, regex=False) | v["endereco"].isin(tem_prod)]
    if v.empty:
        st.info("Nenhum endereço com esses filtros.")
        return
    modo = ui._escolha("inv_end_modo", ["produtos", "resumo"], "produtos",
                       formatar={"produtos": "📦 Produtos de cada endereço", "resumo": "📍 Resumo por endereço"}.get)
    sel = conc.merge(v[["area", "endereco"]], on=["area", "endereco"])
    if busca:
        so_prod = sel["produto"].astype(str).str.contains(busca, regex=False) | sel["descricao"].fillna(
            "").str.upper().str.contains(busca, regex=False) | sel["endereco"].astype(str).str.upper().str.contains(
            busca, regex=False)
        sel = sel[so_prod]
    if modo == "produtos":
        tema.secao("📦 Produtos contados em cada endereço",
                   "Na frente de cada produto: quem contou, quanto contou (na unidade em que contou) e a diferença "
                   "(2ª − 1ª).")
        t = _tab_div(sel.sort_values(["area", "endereco", "produto"]))
        t["Área"] = t["Área"].map(lambda a: nomes.get(a, a))
        ui.tabela(t, baixar=f"inventario_enderecos_produtos_{inv_id}")
    else:
        tema.secao("📍 Resumo por endereço", "Validado = todos os produtos do endereço bateram (ou foram conciliados). "
                                            "Clique na linha para abrir os produtos.")
        resumo = pd.DataFrame({
            "": v["situacao"].map(lambda s: inv.END_STATUS[s].split(" ")[0]), "Área": v["area"].map(
                lambda a: nomes.get(a, a)), "Endereço": v["endereco"], "Contador 1": v["u1"].fillna("—"),
            "Contador 2": v["u2"].fillna("— (falta)"), "Itens": v["itens"], "Bateram": v["ok"],
            "Divergentes": v["divergente"], "Situação": v["situacao"].map(inv.END_STATUS)}).reset_index(drop=True)
        try:
            ev = st.dataframe(resumo, hide_index=True, on_select="rerun", selection_mode="single-row",
                              key=f"inv_end_tab_{inv_id}", **ui.LARGURA)
            linhas = list(ev["selection"]["rows"]) if ev else []
        except (TypeError, KeyError, AttributeError):
            ui.tabela(resumo, baixar=False)
            linhas = []
        if linhas:
            r = v.iloc[linhas[0]]
            tema.detalhe(f"📍 {r['endereco']} · {nomes.get(r['area'], r['area'])}",
                         _tab_div(conc[(conc["area"] == r["area"]) & (conc["endereco"] == r["endereco"])], False))
    chaves = list(dict.fromkeys(f"{a}|{e}" for a, e in zip(sel["area"], sel["endereco"])))
    if not chaves:
        return
    esc = st.selectbox("🔎 Abrir um endereço", chaves, key="inv_end_sel",
                       format_func=lambda k: f"{k.split('|', 1)[1]} · {nomes.get(k.split('|', 1)[0], '')} · "
                                             + inv.END_STATUS[v.set_index(['area', 'endereco']).loc[
                                                 tuple(k.split('|', 1)), 'situacao']])
    a, e = esc.split("|", 1)
    d = conc[(conc["area"] == a) & (conc["endereco"] == e)]
    u1, u2 = d["u1"].iloc[0] or "1ª contagem", d["u2"].iloc[0] or "2ª contagem (falta)"
    st.markdown(f"#### 📍 {e} · {nomes.get(a, a)}")
    det = pd.DataFrame({
        "Cód": d["produto"], "Produto": d["descricao"],
        f"1ª · {u1}": d["t1"].fillna(""), f"2ª · {u2}": d["t2"].fillna("").replace("", "—"),
        "Diferença": d["dif_txt"].replace("", "—"), "Diferença (cx/un)": _dif_cxun(d),
        "Recontagem": [_q(x, f) if pd.notna(x) else "" for x, f in zip(d["rec_un"], d["fator"])],
        "Final (cx/un)": [_q(x, f) for x, f in zip(d["final_un"], d["fator"])],
        "Situação": d["status"].map(inv.STATUS)}).reset_index(drop=True)
    ui.tabela(det, baixar=f"inventario_endereco_{e}")
    dv = d[d["status"] == "divergente"]
    if len(dv) and (inv.inventario(inv_id) or {}).get("status") == "aberto" and st.button(
            f"📨 Mandar os {len(dv)} item(ns) divergentes deste endereço para recontagem", type="primary",
            key=f"inv_env_end_{a}_{e}"):
        ui.acao(inv.enviar_recontagem, inv_id, dv, usuario.get("nome", ""),
                sucesso=f"{len(dv)} item(ns) do endereço {e} enviados para recontagem.")


# --- 🔁 Recontagem ------------------------------------------------------------------------------------------------------
def _link_app() -> str:
    from modules.puxada.app_motorista import link_do_app

    return link_do_app().replace("?app=motorista", "?app=recontagem")


def _recontagem(usuario: dict, op: int, inv_id: int) -> None:
    rc = inv.recontagens(inv_id)
    cont = rc["status"].value_counts() if not rc.empty else pd.Series(dtype=int)
    tema.kpis([
        {"titulo": "Aguardando no app", "valor": _n(cont.get("pendente", 0)), "icone": "📨", "status": "info"},
        {"titulo": "Contados (falta descarga)", "valor": _n(cont.get("contado", 0)), "icone": "✍️",
         "status": "atencao" if cont.get("contado", 0) else "info"},
        {"titulo": "Descarga feita — conciliar", "valor": _n(cont.get("recontado", 0)), "icone": "📥",
         "status": "critico" if cont.get("recontado", 0) else "bom"},
        {"titulo": "Conciliados", "valor": _n(cont.get("conciliado", 0)), "icone": "✔️", "status": "bom"},
    ], key="kp_inv_rec")
    with st.expander("📱 Link do app de recontagem (abrir no celular)"):
        link = _link_app()
        st.code(link, language=None)
        st.caption("O conferente entra com o login dele no sistema e vê só as áreas e endereços a recontar.")
        st.link_button("Abrir o app", link)
    if rc.empty:
        st.info("Nada enviado para recontagem ainda — mande pelo 📊 Painel.")
        return
    para = rc[rc["status"] == "recontado"]
    tema.secao("📥 Conciliar", "A recontagem confirma uma das contagens: o sistema já sugere a que bateu. Ajuste se "
                              "precisar e concilie.")
    if para.empty:
        st.caption("Nenhuma descarga para conciliar agora.")
    else:
        vis = pd.DataFrame({
            "Conciliar": True, "Área": para["area"], "Endereço": para["endereco"], "Cód": para["produto"],
            "Produto": para["descricao"], "1ª contagem": [_q(v, f) for v, f in zip(para["c1_un"], para["fator"])],
            "2ª contagem": [_q(v, f) for v, f in zip(para["c2_un"], para["fator"])],
            "Recontagem": [_q(v, f) for v, f in zip(para["qtd_un"], para["fator"])],
            "Usar": [inv.ESCOLHAS.get(s or "rec") for s in para["sugestao"]],
            "Recontado por": para["contado_por"].fillna("")}).reset_index(drop=True)
        ed = st.data_editor(vis, hide_index=True, key=f"inv_ed_conc_{inv_id}", **ui.LARGURA,
                            disabled=[c for c in vis.columns if c not in ("Conciliar", "Usar")],
                            column_config={"Usar": st.column_config.SelectboxColumn(
                                "Usar", options=list(inv.ESCOLHAS.values()), required=True)})
        inv_esc = {v: k for k, v in inv.ESCOLHAS.items()}
        escolhas = {int(i): inv_esc.get(u, "rec") for i, u, ok in zip(para["id"], ed["Usar"], ed["Conciliar"]) if ok}
        if st.button(f"✅ Conciliar {len(escolhas)} item(ns)", type="primary", key="inv_conciliar",
                     disabled=not escolhas):
            ui.acao(inv.conciliar, escolhas, usuario.get("nome", ""), sucesso="Itens conciliados.")
    abertos = rc[rc["status"].isin(["pendente", "contado"])]
    if not abertos.empty:
        tema.secao("📨 No app")
        ui.tabela(pd.DataFrame({"Área": abertos["area"], "Endereço": abertos["endereco"], "Cód": abertos["produto"],
                                "Produto": abertos["descricao"], "Situação": abertos["status"].map(inv.REC_STATUS),
                                "Enviado por": abertos["enviado_por"].fillna("")}), baixar="inv_no_app")
        canc = st.multiselect("Tirar da recontagem", abertos["id"].tolist(), key="inv_canc",
                              format_func=lambda i: " · ".join(str(x) for x in abertos.set_index("id").loc[
                                  i, ["endereco", "produto", "descricao"]]))
        if canc and st.button("Tirar da recontagem", key="inv_canc_b"):
            ui.acao(inv.cancelar_recontagem, canc, sucesso="Itens retirados da recontagem.")
    feitos = rc[rc["status"] == "conciliado"]
    if not feitos.empty:
        tema.secao("✔️ Conciliados")
        ui.tabela(pd.DataFrame({
            "Área": feitos["area"], "Endereço": feitos["endereco"], "Cód": feitos["produto"],
            "Produto": feitos["descricao"], "Usado": feitos["escolha"].map(inv.ESCOLHAS),
            "Quantidade final": [_q(v, f) for v, f in zip(feitos["final_un"], feitos["fator"])],
            "Por": feitos["conciliado_por"].fillna("")}), baixar="inv_conciliados")
        desf = st.selectbox("Desfazer uma conciliação", [None] + feitos["id"].tolist(), key="inv_desf",
                            format_func=lambda i: "—" if i is None else " · ".join(
                                str(x) for x in feitos.set_index("id").loc[i, ["endereco", "produto", "descricao"]]))
        if desf and st.button("↩️ Desfazer", key="inv_desf_b"):
            ui.acao(inv.desfazer_conciliacao, desf, sucesso="Conciliação desfeita.")


# --- 📋 Resultado -------------------------------------------------------------------------------------------------------
def _resultado(usuario: dict, op: int, inv_id: int) -> None:
    conc = inv.conciliacao(inv_id)
    r = inv.resultado(inv_id, conc)
    if r.empty:
        st.info("Suba o 02.05.02 e as contagens em 📥 Bases.")
        return
    fechados = r[~r["situacao"].isin(["⏳ pendente", "❔ sem conversão"])]
    ok = (fechados["situacao"] == "✅ ok").sum()
    acur = ok / len(fechados) * 100 if len(fechados) else None
    sobra = r.loc[r["dif_cx"] > 0, "dif_cx"].sum()
    falta = r.loc[r["dif_cx"] < 0, "dif_cx"].sum()
    pend = r[r["situacao"].isin(["⏳ pendente", "❔ sem conversão"])]
    tema.kpis([
        {"titulo": "Acuracidade (itens)", "valor": _pct(acur), "icone": "🎯",
         "status": "bom" if (acur or 0) >= 98 else "atencao" if (acur or 0) >= 95 else "critico",
         "detalhe": f"{_n(ok)} de {_n(len(fechados))} produtos iguais ao sistema"},
        {"titulo": "Produtos", "valor": _n(len(r)), "icone": "📦", "status": "info",
         "detalhe": f"{_n((r['sistema_un'] != 0).sum())} no sistema · {_n((r['contado_un'] != 0).sum())} contados"},
        {"titulo": "Sobra", "valor": f"{_n(sobra, 1)} cx", "icone": "🔺", "status": "atencao" if sobra else "bom",
         "dados": _tab_res(r[r["dif_cx"] > 0]) if sobra else None},
        {"titulo": "Falta", "valor": f"{_n(falta, 1)} cx", "icone": "🔻", "status": "critico" if falta else "bom",
         "dados": _tab_res(r[r["dif_cx"] < 0]) if falta else None},
        {"titulo": "Pendentes", "valor": _n(len(pend)), "icone": "⏳", "status": "atencao" if len(pend) else "bom",
         "detalhe": "com endereço sem conciliar ou sem conversão", "dados": _tab_res(pend) if len(pend) else None},
    ], key="kp_inv_res")
    if not (inv.inventario(inv_id) or {}).get("base_em"):
        st.warning("Sem 02.05.02 neste inventário — o “sistema” está zerado. Suba em 📥 Bases.")
    so = st.toggle("Só produtos com diferença ou pendentes", value=True, key="inv_res_so")
    vis = r[r["situacao"] != "✅ ok"] if so else r
    tema.secao("📋 Sistema × contado por produto", "Sistema = disponível da 02.05.02; contado = soma dos endereços "
                                                   "(contagem que bateu ou conciliada).")
    ui.tabela(_tab_res(vis), baixar=f"inventario_resultado_{inv_id}")
    tema.secao("🗺️ Por área")
    pa = inv.painel_areas(conc, op)
    ui.tabela(pd.DataFrame({"Armazém": pa["armazem"], "Área": pa["nome"], "Endereços": pa["enderecos"],
                            "Endereços validados": pa["end_validados"],
                            "Itens": pa["itens"], "Bateu": pa["ok"], "Divergentes": pa["divergente"],
                            "Em recontagem": pa["pendente"] + pa["recontado"], "Conciliados": pa["conciliado"],
                            "Acerto 1ª × 2ª": pa["acerto"].map(_pct)}), baixar=f"inventario_areas_{inv_id}")
    tema.secao("🔎 Endereços do produto")
    prods = r["produto"].tolist()
    nomes = dict(zip(r["produto"], r["descricao"]))
    p_ = st.selectbox("Produto", prods, key="inv_res_prod", format_func=lambda p: f"{p} · {nomes.get(p, '')}")
    x = conc[conc["produto"] == p_]
    if x.empty:
        st.caption("Produto não contado em nenhum endereço.")
    else:
        t = _tab_div(x)
        t["Final"] = [_q(v, f) for v, f in zip(x["final_un"], x["fator"])]
        ui.tabela(t, baixar=f"inventario_enderecos_{p_}")


def _tab_res(r: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Cód": r["produto"], "Produto": r["descricao"].fillna(""),
        "Sistema": [_q(v, f) for v, f in zip(r["sistema_un"], r["fator"])],
        "Contado": [_q(v, f) for v, f in zip(r["contado_un"], r["fator"])],
        "Diferença": [_q(v, f) for v, f in zip(r["dif_un"], r["fator"])],
        "Diferença (cx)": r["dif_cx"].map(lambda v: f"{v:+.2f}".replace(".", ",")),
        "Endereços": r["enderecos"].map(_n), "Situação": r["situacao"]}).reset_index(drop=True)


# --- 📥 Bases -----------------------------------------------------------------------------------------------------------
def _bases(usuario: dict, op: int, inv_id: int) -> None:
    from core.auth import e_master

    i = inv.inventario(inv_id) or {}
    aberto = i.get("status") == "aberto"
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"**1. 02.05.02 (base do sistema)**  \nÚltima carga: "
                    f"{pd.to_datetime(i['base_em']).strftime('%d/%m/%Y %H:%M') if i.get('base_em') else 'nunca'}"
                    + (f" · {i.get('base_arquivo')}" if i.get("base_arquivo") else ""))
        st.caption("Usa a coluna L (Disponível, em cx/un) de cada produto, com o fator da coluna X.")
        v = st.session_state.get("inv_up_b_v", 0)
        arq = st.file_uploader("02.05.02", type=arquivos.FORMATOS, key=f"inv_up_b_{v}", label_visibility="collapsed",
                               disabled=not aberto)
        if arq is not None and st.button("Gravar 02.05.02", type="primary", key="inv_grava_b"):
            try:
                a2 = arquivos.preparar(arq)
                r = inv.importar_base(inv_id, a2.getvalue(), a2.name, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["inv_up_b_v"] = v + 1
                ui.avisar(f"02.05.02: {r['produtos']} produtos · depósitos {', '.join(r['depositos'])}.")
                st.rerun()
        deps = inv.depositos_base(inv_id)
        if deps:
            atuais = [d for d in str(i.get("depositos") or "").split(",") if d in deps] or deps
            sel = st.multiselect("Depósitos que entram no inventário", deps, default=atuais, key=f"inv_deps_{inv_id}",
                                 disabled=not aberto)
            if aberto and sorted(sel) != sorted(atuais):
                inv.salvar_depositos(inv_id, sel)
                ui.salvo_automatico("Depósitos salvos.")
    with c2, st.container(border=True):
        st.markdown("**2. Contagens do WMS**")
        st.caption("C = área · D = endereço · E = usuário · K = quantidade · L = unidade. A mesma contagem subida de "
                   "novo substitui a anterior. A 1ª e a 2ª contagem da área são definidas pela ordem em que cada "
                   "usuário terminou.")
        modo = st.radio("Como subir", ["area", "total"], horizontal=True, key="inv_up_modo",
                        format_func={"area": "📍 Por área", "total": "📦 Todas as áreas (arquivo completo)"}.get,
                        disabled=not aberto)
        area_up = None
        if modo == "area":
            sa = inv.situacao_areas(inv_id, op)
            if sa.empty:
                st.info("Nenhuma área cadastrada ainda. Cadastre em ⚙️ Cadastros › Áreas ou suba o primeiro arquivo "
                        "como “Todas as áreas” (as áreas entram sozinhas).")
            else:
                rot = {r.area: f"{'✅' if r.contagens >= 2 else '1️⃣' if r.contagens == 1 else '⬜'} {r.nome} · "
                               f"{r.contagens} contagem(ns)" + (f" ({r.usuarios})" if r.usuarios else "")
                       for r in sa.itertuples()}
                area_up = st.selectbox("Área", list(rot), key="inv_up_area", format_func=rot.get)
        v2 = st.session_state.get("inv_up_c_v", 0)
        arqs = st.file_uploader("Contagens", type=arquivos.FORMATOS, key=f"inv_up_c_{v2}", accept_multiple_files=True,
                                label_visibility="collapsed", disabled=not aberto)
        arqs = [a for a in (arqs or []) if a is not None]
        pronto = bool(arqs) and (modo == "total" or area_up is not None)
        rot_b = (f"Gravar na área {inv._nome_area(area_up)}" if modo == "area" and area_up else
                 f"Gravar {len(arqs)} arquivo(s) — todas as áreas")
        if pronto and st.button(rot_b, type="primary", key="inv_grava_c"):
            erros = []
            for a in arqs:
                try:
                    a2 = arquivos.preparar(a)
                    r = inv.importar_contagem(inv_id, a2.getvalue(), a2.name, usuario.get("nome", ""),
                                              area_up if modo == "area" else None)
                except RegraNegocioError as e:
                    erros.append(f"{a.name}: {e}")
                else:
                    ui.avisar(f"{a.name}: {r['linhas']} linhas · {r['areas']} área(s) · {r['enderecos']} endereços · "
                              f"{', '.join(r['usuarios'])}."
                              + (f" {r['outras']} linha(s) de outras áreas ignoradas." if r.get("outras") else ""))
            for e in erros:
                st.error(e)
            if not erros:
                st.session_state["inv_up_c_v"] = v2 + 1
                st.rerun()
    rc = inv.resumo_contagens(inv_id)
    if not rc.empty:
        tema.secao("👥 Contagens por área e usuário")
        ui.tabela(pd.DataFrame({
            "Área": rc["area"], "Contagem": rc["contagem"].map(lambda n: f"{n}ª"), "Usuário": rc["usuario"],
            "Terminou": pd.to_datetime(rc["fim"], errors="coerce").dt.strftime("%d/%m %H:%M"),
            "Endereços": rc["enderecos"], "Itens": rc["itens"], "Linhas": rc["linhas"], "Arquivo": rc["arquivo"]}),
            baixar=f"inventario_contagens_{inv_id}")
        if aberto:
            with st.expander("🗑️ Apagar uma contagem (área × usuário)"):
                chaves = [f"{a}|{u}" for a, u in zip(rc["area"], rc["usuario"])]
                esc = st.selectbox("Contagem", chaves, key="inv_apaga", format_func=lambda k: k.replace("|", " · "))
                if st.button("Apagar esta contagem", key="inv_apaga_b"):
                    a, u = esc.split("|", 1)
                    ui.acao(inv.limpar_contagens, inv_id, a, u, sucesso="Contagem apagada.")
    tema.secao("🔒 Situação do inventário")
    b1, b2, _ = st.columns([1, 1, 2])
    if aberto:
        if b1.button("🔒 Fechar inventário", key="inv_fechar"):
            ui.acao(inv.mudar_status, inv_id, "fechado", sucesso="Inventário fechado.")
    elif b1.button("🔓 Reabrir inventário", key="inv_reabrir"):
        ui.acao(inv.mudar_status, inv_id, "aberto", sucesso="Inventário reaberto.")
    if e_master(usuario) and b2.button("🗑️ Excluir inventário", key="inv_excluir"):
        ui.acao(inv.excluir, inv_id, sucesso="Inventário excluído.")


# --- ⚙️ Cadastros -------------------------------------------------------------------------------------------------------
def _cadastros(usuario: dict, op: int, inv_id: int) -> None:
    aba = ui._escolha("inv_cad", ["areas", "armazens", "conv", "resp"], "areas",
                      formatar={"areas": "🗺️ Áreas", "armazens": "🏬 Armazéns", "conv": "🔁 Conversões (01.11)",
                                "resp": "👥 Responsáveis"}.get)
    if operacoes_repo.e_consolidada(op) and aba != "conv":
        st.info("Escolha uma revenda no menu para cadastrar.")
        return
    if aba == "armazens":
        arm = inv.armazens(op)
        st.caption("Cadastre os armazéns e depois ligue cada área ao seu armazém. Apague o nome para excluir.")
        vis = arm[["id", "nome", "ativo"]].copy() if not arm.empty else pd.DataFrame(
            {"id": pd.Series(dtype="float"), "nome": pd.Series(dtype="object"), "ativo": pd.Series(dtype="bool")})
        vis["ativo"] = vis["ativo"].fillna(1).astype(bool)
        ed = st.data_editor(vis, hide_index=True, num_rows="dynamic", key=f"inv_arm_{op}", **ui.LARGURA,
                            column_config={"id": None, "nome": "Armazém", "ativo": st.column_config.CheckboxColumn(
                                "Ativo", default=True)})
        if st.button("💾 Salvar armazéns", type="primary", key="inv_arm_s"):
            ui.acao(inv.salvar_armazens, op, ed.to_dict("records"), sucesso="Armazéns salvos.")
    elif aba == "areas":
        ar = inv.areas(op)
        arm = inv.armazens(op)
        st.caption("As áreas entram sozinhas quando sobe a contagem (coluna C do WMS). Dê o nome, o armazém e a ordem "
                   "em que aparecem no painel e no app.")
        if ar.empty:
            st.info("Nenhuma área ainda — suba uma contagem em 📥 Bases.")
            return
        nomes_arm = dict(zip(arm["id"].astype(int), arm["nome"])) if not arm.empty else {}
        vis = pd.DataFrame({"id": ar["id"], "Código (WMS)": ar["codigo"], "Nome": ar["nome"],
                            "Armazém": ar["armazem_id"].map(lambda i: nomes_arm.get(int(i)) if pd.notna(i) else None),
                            "Ordem": pd.to_numeric(ar["ordem"], errors="coerce").fillna(0).astype(int),
                            "Ativa": ar["ativo"].fillna(1).astype(bool)})
        ed = st.data_editor(vis, hide_index=True, key=f"inv_areas_{op}", **ui.LARGURA,
                            disabled=["Código (WMS)"],
                            column_config={"id": None, "Armazém": st.column_config.SelectboxColumn(
                                "Armazém", options=list(nomes_arm.values()))})
        if not nomes_arm:
            st.caption("Cadastre os armazéns em 🏬 Armazéns para poder escolher aqui.")
        if st.button("💾 Salvar áreas", type="primary", key="inv_areas_s"):
            id_arm = {v: k for k, v in nomes_arm.items()}
            linhas = [{"id": r["id"], "nome": r["Nome"], "armazem_id": id_arm.get(r["Armazém"]), "ordem": r["Ordem"],
                       "ativo": bool(r["Ativa"])} for r in ed.to_dict("records")]
            ui.acao(inv.salvar_areas, op, linhas, sucesso="Áreas salvas.")
    elif aba == "conv":
        _conversoes(usuario, inv_id)
    else:
        from repositories import usuarios_repo

        us = {u["id"]: f"{u['nome']} ({u.get('cargo') or u.get('perfil') or ''})" for u in usuarios_repo.listar()}
        sel = st.multiselect("Quem recebe o aviso quando o conferente faz a descarga da recontagem", list(us),
                             default=[i for i in inv.responsaveis(op) if i in us], format_func=us.get,
                             key=f"inv_resp_{op}")
        if st.button("💾 Salvar responsáveis", type="primary", key="inv_resp_s"):
            ui.acao(inv.salvar_responsaveis, op, sel, sucesso="Responsáveis salvos.")


def _conversoes(usuario: dict, inv_id: int) -> None:
    c = inv._contagens_un(inv_id)
    st.caption("Conversão das unidades contadas para unidades: CX = un/cx · PL = cx/palete × un/cx · LST = cx/lastro × "
               "un/cx. Vem da 01.11 (cx/palete, cx/lastro) e do fator da 02.05.02 (un/cx); o que você ajustar aqui "
               "vale para todos os inventários.")
    _upload_0111(usuario)
    if c.empty:
        st.info("Suba as contagens para ver os produtos.")
        return
    falta = set(c.loc[c["mult"].isna(), "produto"])
    usados = c.groupby("produto")["unidade"].apply(lambda s: ", ".join(sorted(set(s))))
    cv = inv.conversoes(inv_id, sorted(set(c["produto"])))
    so = st.toggle(f"Só os {len(falta)} produto(s) sem conversão", value=bool(falta), key="inv_conv_so")
    if so:
        cv = cv[cv["produto"].isin(falta)]
    vis = pd.DataFrame({"produto": cv["produto"], "Produto": cv["descricao"].fillna(""),
                        "Contado em": cv["produto"].map(usados).fillna(""),
                        "un_cx": cv["un_cx_f"], "cx_pallet": cv["cx_pallet_f"], "cx_lastro": cv["cx_lastro_f"],
                        "": ["❔ falta" if p in falta else "✅" for p in cv["produto"]]}).reset_index(drop=True)
    ed = st.data_editor(vis, hide_index=True, key=f"inv_conv_{inv_id}_{so}", **ui.LARGURA,
                        disabled=["produto", "Produto", "Contado em", ""],
                        column_config={"produto": "Cód",
                                       "un_cx": st.column_config.NumberColumn("Un/cx", min_value=0.0, format="%.0f"),
                                       "cx_pallet": st.column_config.NumberColumn("Cx/palete", min_value=0.0,
                                                                                  format="%.0f"),
                                       "cx_lastro": st.column_config.NumberColumn("Cx/lastro", min_value=0.0,
                                                                                  format="%.0f")})
    if st.button("💾 Salvar conversões", type="primary", key="inv_conv_s"):
        mud = ed[(ed[["un_cx", "cx_pallet", "cx_lastro"]].fillna(-1) != vis[["un_cx", "cx_pallet", "cx_lastro"]]
                  .fillna(-1)).any(axis=1)]
        ui.acao(inv.salvar_conversoes, mud.to_dict("records"), usuario.get("nome", ""),
                sucesso=f"{len(mud)} conversão(ões) salvas.")


def _upload_0111(usuario: dict) -> None:
    with st.expander("📥 Trazer as conversões da 01.11 (unidades por caixa, caixas por palete e por lastro)",
                     expanded=True):
        st.caption("Suba a 01.11 e confira as colunas — o sistema grava no cadastro de produtos e passa a converter "
                   "CX, PL e LST automaticamente em todos os inventários.")
        v = st.session_state.get("inv_0111_v", 0)
        arq = st.file_uploader("01.11", type=arquivos.FORMATOS, key=f"inv_0111_{v}", label_visibility="collapsed")
        if arq is None:
            return
        try:
            a2 = arquivos.preparar(arq)
            df, mapa = inv.ler_0111(a2.getvalue(), a2.name)
        except RegraNegocioError as e:
            st.error(str(e))
            return
        salvo = inv.mapa_0111_salvo()
        cols = [None] + list(df.columns)
        rot = {"cod": "Código do produto *", "un_cx": "Unidades por caixa", "cx_pallet": "Caixas por palete",
               "cx_lastro": "Caixas por lastro"}
        esc = {}
        c = st.columns(4)
        for i, (k, r) in enumerate(rot.items()):
            pad = salvo.get(k) if salvo.get(k) in df.columns else mapa.get(k)
            esc[k] = c[i].selectbox(r, cols, index=cols.index(pad) if pad in cols else 0, key=f"inv_0111_m_{k}",
                                    format_func=lambda x: "— não usar —" if x is None else x)
        with st.expander("Prévia da 01.11"):
            ui.tabela(df[[x for x in esc.values() if x]].head(10) if any(esc.values()) else df.head(10), baixar=False)
        if st.button("💾 Gravar conversões da 01.11", type="primary", key="inv_0111_g"):
            try:
                r = inv.importar_conversoes_0111(df, esc, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["inv_0111_v"] = v + 1
                ui.avisar(f"01.11: conversões de {r['produtos']} produto(s) gravadas.")
                st.rerun()
