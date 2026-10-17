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
        _diaria(usuario, operacao_id)
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


_CHECK = {"ok": "✔️", "conciliado": "✔️", "divergente": "❌", "pendente": "📨", "recontado": "📥",
          "aguardando": "⏳", "sem_conversao": "❔"}


def _cx(un, fator) -> str:
    """Quantidade em unidade de venda (caixas)."""
    if un is None or pd.isna(un):
        return "—"
    v = float(un) / (float(fator or 1) or 1.0)
    txt = f"{v:,.0f}" if abs(v - round(v)) < 0.005 else f"{v:,.2f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def _dif_cx(d: pd.DataFrame) -> list[str]:
    out = []
    for a, b, f in zip(d["c1_un"], d["c2_un"], d["fator"]):
        if pd.isna(a) or pd.isna(b):
            out.append("—")
        else:
            t = _cx(b - a, f)
            out.append(t if t.startswith("-") or t == "0" else "+" + t)
    return out


def _contou(un, fator, txt) -> str:
    """Quanto contou: em caixas quando dá para converter; senão do jeito que contou (ex.: 4 CX + 7 LST)."""
    return _cx(un, fator) + " cx" if un is not None and not pd.isna(un) else (txt or "0")


def _diferenca(d: pd.DataFrame) -> list[str]:
    out = []
    for a, b, f, u2, dt in zip(d["c1_un"], d["c2_un"], d["fator"], d["u2"], d["dif_txt"]):
        if pd.isna(u2):
            out.append("—")
        elif pd.notna(a) and pd.notna(b):
            t = _cx(b - a, f)
            out.append("0" if t == "0" else (t if t.startswith("-") else "+" + t) + " cx")
        else:
            out.append(dt or "0")
    return out


def _tab_div(d: pd.DataFrame, area: bool = True, nomes: tuple | None = None) -> pd.DataFrame:
    """Uma linha por endereço × produto: ✔️/❌, o que cada um contou (em caixas; sem conversão, do jeito que contou)
    e a diferença (2ª − 1ª). `nomes` = (contador 1, contador 2) vira o título das colunas (um endereço só)."""
    c1 = [_contou(v, f, t) for v, f, t in zip(d["c1_un"], d["fator"], d["t1"])]
    c2 = [_contou(v, f, t) if pd.notna(u) else "—" for v, f, t, u in zip(d["c2_un"], d["fator"], d["t2"], d["u2"])]
    t = pd.DataFrame({"": d["status"].map(_CHECK).fillna("").values, "Área": d["area"].values,
                      "Endereço": d["endereco"].values, "Cód": d["produto"].values,
                      "Produto": d["descricao"].fillna("").values})
    if nomes:
        t[f"1ª · {nomes[0]}"] = c1
        t[f"2ª · {nomes[1]}"] = c2
    else:
        t["Contador 1"] = d["u1"].fillna("—").values
        t["Contou 1"] = c1
        t["Contador 2"] = d["u2"].fillna("— (falta)").values
        t["Contou 2"] = c2
    t["Diferença"] = _diferenca(d)
    # recontagens (rodada 1, 2…) e o final ficam na frente, sem apagar a 1ª e a 2ª contagem originais
    rods = sorted([c for c in d.columns if c.startswith("r") and c.endswith("_un") and c[1:-3].isdigit()
                   and d[c].notna().any()], key=lambda c: int(c[1:-3]))
    for c in rods:
        t[f"Recontagem {c[1:-3]}"] = [_contou(x, f, "") if pd.notna(x) else "" for x, f in zip(d[c], d["fator"])]
    if rods:
        t["Final"] = [_cx(x, f) + " cx" if pd.notna(x) else "—" for x, f in zip(d["final_un"], d["fator"])]
    t[""] = (d["orig"] if "orig" in d else d["status"]).map(_CHECK).fillna("").values
    t["Situação"] = d["status"].map(inv.STATUS).values
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
    f1, f2 = st.columns([1, 1.6])
    area = f1.selectbox("Área", opcs, key="inv_area",
                        format_func=lambda a: "Todas as áreas com diferença" if a == "__todas__" else nomes.get(a, a))
    d = conc[conc["status"] == "divergente"]
    if area != "__todas__":
        d = d[d["area"] == area]
    ends = sorted(d["endereco"].fillna("").unique().tolist())
    sel_end = f2.multiselect("Endereços (vazio = todos da área)", ends, key=f"inv_env_ends_{area}",
                             format_func=lambda e: e or "(sem endereço)")
    if sel_end:
        d = d[d["endereco"].fillna("").isin(sel_end)]
    if d.empty:
        st.success("Nenhum item com diferença entre a 1ª e a 2ª contagem aqui. 👏")
        return
    todos = st.checkbox("Marcar todos", value=True, key=f"inv_env_todos_{area}")
    vis = _tab_div(d).drop(columns="Situação")
    vis.insert(0, "Recontar", todos)
    ed = st.data_editor(vis, hide_index=True, key=f"inv_ed_env_{inv_id}_{area}_{'|'.join(sel_end)}_{todos}",
                        **ui.LARGURA,
                        disabled=[c for c in vis.columns if c != "Recontar"],
                        column_config={"Recontar": st.column_config.CheckboxColumn("Recontar", default=True)})
    marcados = d.reset_index(drop=True)[ed["Recontar"].fillna(False).astype(bool).values]
    alvo = (f"área {nomes.get(area, area)}" if area != "__todas__" else "todas as áreas") + \
        (f" · {len(sel_end)} endereço(s)" if sel_end else "")
    if st.button(f"📨 Enviar {len(marcados)} item(ns) para recontagem ({alvo})", type="primary", key="inv_enviar",
                 disabled=marcados.empty):
        ui.acao(inv.enviar_recontagem, inv_id, marcados, usuario.get("nome", ""),
                sucesso=f"{len(marcados)} item(ns) enviados para o app de recontagem.")


# --- 📍 Por endereço ----------------------------------------------------------------------------------------------------
def _enderecos(usuario: dict, op: int, inv_id: int) -> None:
    conc = inv.conciliacao(inv_id)
    if conc.empty:
        st.info("Ainda não há contagens neste inventário — suba em 📥 Bases.")
        return
    # esta tela mostra a 1ª × 2ª contagem como foram (a diferença continua visível); o andamento da recontagem e a
    # conciliação ficam na aba 🔁 Recontagem
    pe = inv.por_endereco(conc.assign(status=conc["orig"]))
    nomes = dict(zip(*[inv.painel_areas(conc, op)[c] for c in ("area", "nome")]))
    c1, c2 = st.columns([1.3, 2])
    areas_ = ["__todas__"] + sorted(pe["area"].unique(), key=lambda a: nomes.get(a, a))
    area = c1.selectbox("Área", areas_, key="inv_end_area",
                        format_func=lambda a: "Todas as áreas" if a == "__todas__" else nomes.get(a, a))
    pa = pe if area == "__todas__" else pe[pe["area"] == area]
    ca = conc if area == "__todas__" else conc[conc["area"] == area]
    cont = pa["situacao"].value_counts()

    def itens_de(situacoes: list[str], status_item: list[str] | None = None) -> pd.DataFrame | None:
        x = ca.merge(pa.loc[pa["situacao"].isin(situacoes), ["area", "endereco"]], on=["area", "endereco"])
        if status_item:
            x = x[x["orig"].isin(status_item)]
        if x.empty:
            return None
        t = _tab_div(x.sort_values(["area", "endereco", "produto"]))
        t["Área"] = t["Área"].map(lambda a: nomes.get(a, a))
        return t

    with c2:
        tema.kpis([
            {"titulo": "Endereços", "valor": _n(len(pa)), "icone": "📍", "status": "info",
             "dados": itens_de(list(inv.END_STATUS))},
            {"titulo": "Validados ✔️", "valor": _n(cont.get("validado", 0)), "icone": "✅", "status": "bom",
             "detalhe": _pct(cont.get("validado", 0) / len(pa) * 100) if len(pa) else "—",
             "dados": itens_de(["validado"])},
            {"titulo": "Com diferença ❌", "valor": _n(cont.get("divergente", 0)), "icone": "⚠️",
             "status": "critico" if cont.get("divergente", 0) else "bom",
             "detalhe": f"{_n((ca['orig'] == 'divergente').sum())} produto(s) · 1ª ≠ 2ª",
             "dados": itens_de(["divergente"], ["divergente"])},
            {"titulo": "Só 1 contagem", "valor": _n(cont.get("aguardando", 0)), "icone": "⏳",
             "status": "atencao" if cont.get("aguardando", 0) else "bom", "dados": itens_de(["aguardando"])},
        ], key="kp_inv_end")
    sem = ca[ca["sem_conv"].fillna(False).astype(bool)]
    if len(sem):
        st.caption(f"❔ {sem['produto'].nunique()} produto(s) contados em palete/lastro sem a conversão da 01.11 — "
                   "aparecem do jeito que contaram (ex.: 4 CX + 7 LST). Suba a 01.11 em ⚙️ Cadastros › 🔁 Conversões "
                   "para ver tudo em caixas.")
    f1, f2 = st.columns([1.3, 2])
    ends = ["__todos__"] + [f"{a}|{e}" for a, e in zip(pa["area"], pa["endereco"])]
    sit_end = dict(zip([f"{a}|{e}" for a, e in zip(pa["area"], pa["endereco"])], pa["situacao"]))
    esc = f1.selectbox("Endereço", ends, key=f"inv_end_sel_{area}",
                       format_func=lambda k: "Todos os endereços" if k == "__todos__" else
                       f"{inv.END_STATUS[sit_end[k]].split(' ')[0]} {k.split('|', 1)[1]}"
                       + ("" if area != "__todas__" else f" · {nomes.get(k.split('|', 1)[0], '')}"))
    if esc == "__todos__":
        d = ca
    else:
        a_, e_ = esc.split("|", 1)
        d = ca[(ca["area"] == a_) & (ca["endereco"] == e_)]
    # OK/NOK = resultado da 1ª × 2ª contagem (o que deu diferença continua em NOK mesmo depois de recontado)
    n_ok = int((d["orig"] == "ok").sum())
    n_nok = int((d["orig"] == "divergente").sum())
    filtro = f2.radio("Mostrar", ["todos", "ok", "nok"], horizontal=True, key="inv_end_filtro",
                      format_func={"todos": f"Todos ({len(d)})", "ok": f"✔️ OK ({n_ok})",
                                   "nok": f"❌ NOK — com diferença ({n_nok})"}.get)
    d = d[d["orig"] == "ok"] if filtro == "ok" else d[d["orig"] == "divergente"] if filtro == "nok" else d
    d = d.sort_values(["area", "endereco", "produto"])
    aberto = (inv.inventario(inv_id) or {}).get("status") == "aberto"
    if esc == "__todos__":
        t = _tab_div(d, area == "__todas__")
        if "Área" in t:
            t["Área"] = t["Área"].map(lambda a: nomes.get(a, a))
        ui.tabela(t, vazio="Nenhum produto nesse filtro.", baixar=f"inventario_enderecos_{inv_id}")
        alvo = d
    else:
        base_ = ca[(ca["area"] == a_) & (ca["endereco"] == e_)]
        u1 = base_["u1"].iloc[0] if len(base_) else None
        u2 = base_["u2"].iloc[0] if len(base_) else None
        st.markdown(f"#### 📍 {e_} · {nomes.get(a_, a_)}")
        t = _tab_div(d, False, (u1 or "1ª contagem", u2 or "falta 2ª contagem")).drop(columns=["Endereço"])
        ui.tabela(t, vazio="Nenhum produto nesse filtro.", baixar=f"inventario_endereco_{e_}")
        alvo = base_
    # ❌ que podem ir para o app: ainda divergentes ou já conciliados (vira a próxima rodada de recontagem)
    env = alvo[(alvo["orig"] == "divergente") & alvo["status"].isin(["divergente", "conciliado"])]
    if len(env) and aberto:
        n_nova = int((env["status"] == "conciliado").sum())
        if st.button(f"📨 Mandar {len(env)} item(ns) ❌ para recontagem"
                     + (f" ({n_nova} em nova rodada)" if n_nova else ""), type="primary", key=f"inv_env_end_{esc}"):
            ui.acao(inv.enviar_recontagem, inv_id, env, usuario.get("nome", ""),
                    sucesso=f"{len(env)} item(ns) enviados para o app de recontagem.")
    _base_final(usuario, inv_id, conc, nomes)


def _base_final(usuario: dict, inv_id: int, conc: pd.DataFrame, nomes: dict) -> None:
    i = inv.inventario(inv_id) or {}
    with st.expander("🏁 Finalizar e salvar a base do inventário", expanded=bool(i.get("finalizado_em"))):
        pend = conc[conc["final_un"].isna()]
        abertos = conc[conc["status"].isin(["pendente", "recontado"])]
        if i.get("finalizado_em"):
            st.success(f"Base finalizada em {pd.to_datetime(i['finalizado_em']).strftime('%d/%m/%Y %H:%M')} por "
                       f"{i.get('finalizado_por') or '—'}.")
        else:
            st.caption("A base final guarda a 1ª e a 2ª contagem originais, cada recontagem e a quantidade final de "
                       "cada endereço. Depois de finalizar o inventário fica fechado (dá para reabrir em 📥 Bases).")
            if len(pend):
                st.warning(f"{len(pend)} item(ns) ainda sem quantidade final ({len(abertos)} na recontagem) — "
                           "finalize quando estiverem resolvidos.")
            if st.button("✅ Finalizar e salvar base", type="primary", key="inv_finalizar",
                         disabled=i.get("status") != "aberto"):
                ui.acao(inv.finalizar, inv_id, usuario.get("nome", ""), sucesso="Inventário finalizado e base salva.")
        t = _tab_div(conc.sort_values(["area", "endereco", "produto"]))
        t["Área"] = t["Área"].map(lambda a: nomes.get(a, a))
        if "Final" not in t:
            t["Final"] = [_cx(x, f) + " cx" if pd.notna(x) else "—" for x, f in zip(conc.sort_values(
                ["area", "endereco", "produto"])["final_un"], conc.sort_values(["area", "endereco", "produto"])["fator"])]
        ui.tabela(t, baixar=f"inventario_base_final_{inv_id}")


# --- 🔁 Recontagem ------------------------------------------------------------------------------------------------------
def _link_app(op: int | None = None) -> str:
    """Link do app de recontagem da revenda (cada revenda tem o seu)."""
    from modules.puxada.app_motorista import link_do_app

    base = link_do_app().replace("?app=motorista", "?app=recontagem")
    tok = inv.link_token(op) if op and not operacoes_repo.e_consolidada(op) else None
    return f"{base}&k={tok}" if tok else base


def _recontagem(usuario: dict, op: int, inv_id: int) -> None:
    rc = inv.recontagens(inv_id)
    cont = rc["status"].value_counts() if not rc.empty else pd.Series(dtype=int)
    tema.kpis([
        {"titulo": "Aguardando no app", "valor": _n(cont.get("pendente", 0)), "icone": "📨", "status": "info"},
        {"titulo": "Contados (falta descarga)", "valor": _n(cont.get("contado", 0)), "icone": "✍️",
         "status": "atencao" if cont.get("contado", 0) else "info"},
        {"titulo": "Bateu — conciliar", "valor": _n(((rc["sit"] == "recontado") if not rc.empty else
                                                       pd.Series(dtype=bool)).sum()), "icone": "📥",
         "status": "atencao" if cont.get("recontado", 0) else "bom"},
        {"titulo": "Não bateu — recontar", "valor": _n(((rc["sit"] == "nao_bateu") if not rc.empty else
                                                         pd.Series(dtype=bool)).sum()), "icone": "🔁",
         "status": "critico" if not rc.empty and (rc["sit"] == "nao_bateu").any() else "bom"},
        {"titulo": "Conciliados", "valor": _n(cont.get("conciliado", 0)), "icone": "✔️", "status": "bom"},
    ], key="kp_inv_rec")
    with st.expander("📱 Link do app de recontagem desta revenda (abrir no celular)"):
        link = _link_app(op)
        st.code(link, language=None)
        st.caption("O conferente entra com o login cadastrado em ⚙️ Cadastros › 📱 App & conferentes e vê só as "
                   "áreas e endereços a recontar.")
        st.link_button("Abrir o app", link)
    if rc.empty:
        st.info("Nada enviado para recontagem ainda — mande pelo 📊 Painel.")
        return
    nb = rc[rc["sit"] == "nao_bateu"]
    if not nb.empty:
        tema.secao("🔁 Não bateu — criar nova recontagem",
                   "A recontagem não ficou igual a nenhuma contagem anterior (1ª, 2ª nem recontagens). Selecione o que "
                   "precisa contar de novo e crie a próxima recontagem — até fechar o número.")
        ant = [", ".join(_cx(float(x), f) + " cx" for x in str(a).split(",") if x not in ("", "nan", "None"))
               for a, f in zip(nb["anteriores"], nb["fator"])]
        vis_nb = pd.DataFrame({
            "Recontar": True, "Rodada": nb["rodada"].map(lambda r: f"{r}ª"), "Área": nb["area"],
            "Endereço": nb["endereco"], "Cód": nb["produto"], "Produto": nb["descricao"],
            "1ª contagem": [_cx(v, f) + " cx" if pd.notna(v) else "—" for v, f in zip(nb["c1_un"], nb["fator"])],
            "2ª contagem": [_cx(v, f) + " cx" if pd.notna(v) else "—" for v, f in zip(nb["c2_un"], nb["fator"])],
            "Recontagens anteriores": [a or "—" for a in ant],
            "Última recontagem": [_cx(v, f) + " cx" for v, f in zip(nb["qtd_un"], nb["fator"])]}).reset_index(drop=True)
        ed_nb = st.data_editor(vis_nb, hide_index=True, key=f"inv_ed_nb_{inv_id}", **ui.LARGURA,
                               disabled=[c for c in vis_nb.columns if c != "Recontar"])
        sel = [int(i) for i, ok in zip(nb["id"], ed_nb["Recontar"]) if ok]
        b1, b2 = st.columns(2)
        if b1.button(f"📨 Criar nova recontagem ({len(sel)} item(ns))", type="primary", key="inv_nova_rec",
                     disabled=not sel, **ui.LARGURA):
            ui.acao(inv.nova_recontagem, inv_id, sel, usuario.get("nome", ""),
                    sucesso=f"Nova recontagem criada para {len(sel)} item(ns) — já está no app.")
        if b2.button(f"✅ Aceitar a última recontagem ({len(sel)})", key="inv_aceita_rec", disabled=not sel,
                     **ui.LARGURA):
            ui.acao(inv.conciliar, {i: "rec" for i in sel}, usuario.get("nome", ""),
                    sucesso="Última recontagem aceita como quantidade final.")
    para = rc[(rc["status"] == "recontado") & (rc["sit"] == "recontado")]
    tema.secao("📥 Bateu — conciliar", "A recontagem ficou igual a uma das contagens: o sistema já sugere qual usar. "
                                       "Ajuste se precisar e concilie.")
    if para.empty:
        st.caption("Nenhuma recontagem que bateu esperando conciliação.")
    else:
        vis = pd.DataFrame({
            "Conciliar": True, "Rodada": para["rodada"].fillna(1).astype(int).map(lambda r: f"{r}ª"),
            "Área": para["area"], "Endereço": para["endereco"], "Cód": para["produto"],
            "Produto": para["descricao"], "1ª contagem (cx)": [_cx(v, f) for v, f in zip(para["c1_un"], para["fator"])],
            "2ª contagem (cx)": [_cx(v, f) for v, f in zip(para["c2_un"], para["fator"])],
            "Recontagem (cx)": [_cx(v, f) for v, f in zip(para["qtd_un"], para["fator"])],
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
    _excluir_enviadas(inv_id, "mensal")
    feitos = rc[rc["status"] == "conciliado"]
    if not feitos.empty:
        tema.secao("✔️ Conciliados")
        ui.tabela(pd.DataFrame({
            "Área": feitos["area"], "Endereço": feitos["endereco"], "Cód": feitos["produto"],
            "Produto": feitos["descricao"], "Usado": feitos["escolha"].map(inv.ESCOLHAS),
            "Quantidade final (cx)": [_cx(v, f) for v, f in zip(feitos["final_un"], feitos["fator"])],
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
    aba = ui._escolha("inv_cad", ["areas", "armazens", "conv", "app", "resp"], "areas",
                      formatar={"areas": "🗺️ Áreas", "armazens": "🏬 Armazéns", "conv": "🔁 Conversões (01.11)",
                                "app": "📱 App & responsáveis", "resp": "👥 Responsáveis"}.get)
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
    elif aba == "app":
        _conferentes(usuario, op)
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


def _conferentes(usuario: dict, op: int) -> None:
    from core.auth import e_master

    nome_rev = (operacoes_repo.buscar(op) or {}).get("nome", "")
    tema.secao(f"📱 Link do app de recontagem — {nome_rev}",
               "Cada revenda tem o seu link. Mande para os responsáveis: eles entram com o CPF e a senha cadastrados "
               "abaixo.")
    link = _link_app(op)
    st.code(link, language=None)
    c1, c2, _ = st.columns([1, 1, 2])
    c1.link_button("Abrir o app", link, **ui.LARGURA)
    if c2.button("♻️ Gerar novo link", key="inv_novo_link", help="O link antigo para de funcionar.", **ui.LARGURA):
        ui.acao(inv.novo_link, op, sucesso="Novo link gerado — mande de novo para os conferentes.")
    tema.secao("👷 Responsáveis pelas recontagens (login do app)",
               "Cadastre nome, CPF e senha. No app eles entram com o CPF e essa senha.")
    from services.portal_rn_service import formatar_cpf

    with st.form("inv_conf_novo", clear_on_submit=True, border=True):
        f1, f2 = st.columns([2, 1.3])
        nome = f1.text_input("Nome")
        cpf = f2.text_input("CPF", placeholder="000.000.000-00")
        f3, f4, f5 = st.columns([1.3, 1.3, 1])
        s1 = f3.text_input("Senha", type="password")
        s2 = f4.text_input("Confirme a senha", type="password")
        f5.write("")
        if f5.form_submit_button("➕ Cadastrar", type="primary", **ui.LARGURA):
            ui.acao(inv.salvar_conferente, op, nome, cpf, usuario.get("nome", ""), None, True, s1, s2,
                    sucesso="Responsável cadastrado — já pode entrar no app com o CPF e a senha.")
    cf = inv.conferentes(op)
    if cf.empty:
        st.caption("Nenhum responsável cadastrado ainda.")
        return
    ui.tabela(pd.DataFrame({
        "Nome": cf["nome"], "CPF": cf["login"].map(formatar_cpf),
        "Situação": ["🟢 Ativo" if a else "🔒 Bloqueado" for a in cf["ativo"]],
        "Senha": ["✅ definida" if t else "⏳ sem senha" for t in cf["tem_senha"]],
        "Último acesso": cf["ultimo_acesso"].fillna("nunca").astype(str).str[:16]}), baixar=False)
    ids = cf["id"].astype(int).tolist()
    nomes = dict(zip(ids, cf["nome"] + " · " + cf["login"].map(formatar_cpf)))
    sel = st.selectbox("Responsável", ids, format_func=nomes.get, key="inv_conf_sel")
    r = cf.set_index("id").loc[sel]
    with st.form(f"inv_conf_senha_{sel}", clear_on_submit=True):
        g1, g2, g3 = st.columns([1.3, 1.3, 1])
        n1 = g1.text_input("Nova senha", type="password")
        n2 = g2.text_input("Confirme", type="password")
        g3.write("")
        if g3.form_submit_button("🔑 Trocar senha", **ui.LARGURA):
            ui.acao(inv.definir_senha_conferente, sel, n1, n2, sucesso="Senha alterada.")
    b1, b2, _ = st.columns([1, 1, 2])
    if b1.button("🔒 Bloquear" if r["ativo"] else "🔓 Liberar", key="inv_conf_bloq", **ui.LARGURA):
        ui.acao(inv.salvar_conferente, op, r["nome"], r["login"], "", sel, not bool(r["ativo"]),
                sucesso="Responsável atualizado.")
    if e_master(usuario) and b2.button("🗑️ Excluir", key="inv_conf_del", **ui.LARGURA):
        ui.acao(inv.excluir_conferente, sel, sucesso="Responsável excluído.")


# =====================================================================================================================
# 🔄 Conciliação diária — uma contagem × estoque da 02.05.02; o que não bate vai para a 1ª recontagem sozinho
# =====================================================================================================================
_TELAS_D = {"painel": "📊 Painel", "recontagem": "🔁 Recontagem", "bases": "📥 Bases"}


def _diaria(usuario: dict, op: int) -> None:
    meses = inv.meses_diarios(op)
    c1, c2 = st.columns([2.2, 1])
    with c2.popover("➕ Nova contagem do dia"):
        dia = st.date_input("Dia", value=tempo.hoje(), format="DD/MM/YYYY", key="invd_novo_dia")
        if st.button("Criar", type="primary", key="invd_criar"):
            try:
                novo = inv.criar(op, "", "", usuario.get("nome", ""), tipo="diario", data=dia.isoformat())
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["invd_mes"] = dia.isoformat()[:7]
                st.session_state["invd_sel"] = novo
                st.session_state["invd_tela"] = st.session_state["invd_tela__ultima"] = "bases"
                ui.avisar("Contagem do dia criada — suba o 02.05.02 e a contagem do WMS.")
                st.rerun()
    if st.session_state.get("invd_mes") not in meses:
        st.session_state["invd_mes"] = meses[0]
    mes = c1.selectbox("📁 Pasta do mês", meses, key="invd_mes", format_func=lambda m: f"📁 {ui.nome_mes(m)}",
                       label_visibility="collapsed")
    pasta = inv.pasta_mes(op, mes)
    if pasta.empty:
        st.info(f"Nenhuma contagem em {ui.nome_mes(mes)}. Clique em **➕ Nova contagem do dia**.")
        return
    salvas = pasta[pasta["status"] == "fechado"]
    andamento = pasta[pasta["status"] != "fechado"]
    _pasta(mes, pasta, salvas, andamento)
    ids = pasta["id"].astype(int).tolist()
    rot = {int(r.id): f"{'💾' if r.status == 'fechado' else '🟢'} {_dia(r.data)} · {r.nome}"
           + ("" if r.status == "fechado" else " · em andamento") for r in pasta.itertuples()}
    if st.session_state.get("invd_sel") not in ids:
        st.session_state["invd_sel"] = int(andamento["id"].iloc[0]) if len(andamento) else ids[0]
    inv_id = int(st.selectbox("Conciliação", ids, key="invd_sel", format_func=rot.get))
    i = inv.inventario(inv_id) or {}
    fechado = i.get("status") == "fechado"
    st.markdown(f"### 📅 Conciliação de {_dia(i.get('data'))}"
                + (f" — {i.get('nome')}" if fechado else ""))
    if fechado:
        st.caption(f"💾 Salva na pasta de {ui.nome_mes(mes)} por {i.get('finalizado_por') or '—'} em "
                   f"{_dia_hora(i.get('finalizado_em'))}. Para mexer de novo, reabra em 📊 Painel.")
    else:
        st.caption("🟢 Em andamento — tudo é salvo automaticamente a cada carga e recontagem. Finalize só quando "
                   "estiver tudo OK (no fim do 📊 Painel).")
    tela = ui._escolha("invd_tela", list(_TELAS_D), "painel", pills=True, formatar=_TELAS_D.get)
    {"painel": _d_painel, "recontagem": _d_recontagem, "bases": _d_bases}[tela](usuario, op, inv_id)


def _dia(v) -> str:
    try:
        return pd.to_datetime(v).strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        return str(v or "—")


def _dia_hora(v) -> str:
    try:
        return pd.to_datetime(v).strftime("%d/%m/%Y %H:%M")
    except Exception:  # noqa: BLE001
        return str(v or "—")


def _pasta(mes: str, pasta: pd.DataFrame, salvas: pd.DataFrame, andamento: pd.DataFrame) -> None:
    """Resumo da pasta do mês: as conciliações salvas e as em andamento."""
    tot = salvas["ok"].sum() if len(salvas) else 0
    fech = (salvas["produtos"] - salvas["pendentes"]).sum() if len(salvas) else 0
    media = tot / fech * 100 if fech else None

    def tab(d):
        return pd.DataFrame({
            "Dia": [_dia(x) for x in d["data"]], "Nome": d["nome"].values,
            "Situação": ["💾 Salva" if x == "fechado" else "🟢 Em andamento" for x in d["status"]],
            "Produtos": d["produtos"].values, "Bateram": d["ok"].values, "Com diferença": d["diferenca"].values,
            "No app": d["pendentes"].values, "Acuracidade": [_pct(x) for x in d["acuracidade"]],
            "Salva por": d["finalizado_por"].fillna("").values})
    tema.kpis([
        {"titulo": f"Salvas em {ui.nome_mes(mes)}", "valor": _n(len(salvas)), "icone": "💾", "status": "info",
         "dados": tab(salvas) if len(salvas) else None},
        {"titulo": "Em andamento", "valor": _n(len(andamento)), "icone": "🟢", "status": "info",
         "dados": tab(andamento) if len(andamento) else None},
        {"titulo": "Acuracidade do mês", "valor": _pct(media), "icone": "🎯",
         "status": "bom" if (media or 0) >= 98 else "atencao" if (media or 0) >= 95 else "critico",
         "detalhe": "das conciliações salvas"},
    ], key=f"kp_invd_pasta_{mes}")
    with st.expander(f"📁 Conciliações de {ui.nome_mes(mes)} ({len(pasta)})"):
        ui.tabela(tab(pasta), baixar=f"conciliacoes_{mes}")


def _d_tab(d: pd.DataFrame) -> pd.DataFrame:
    t = pd.DataFrame({
        "": ["✔️" if s_ in ("ok", "ok_rec") else "📨" if s_ == "pendente" else "❔" if s_ == "sem_conversao" else "❌"
             for s_ in d["status"]],
        "Cód": d["produto"].values, "Produto": d["descricao"].fillna("").values,
        "Estoque 02.05.02": [_cx(v, f) + " cx" for v, f in zip(d["sistema_un"], d["fator"])],
        "Contagem": [_cx(v, f) + " cx" if pd.notna(v) else "—" for v, f in zip(d["contado_un"], d["fator"])]})
    for c in sorted([c for c in d.columns if c.startswith("r") and c.endswith("_un") and c[1:-3].isdigit()],
                    key=lambda c: int(c[1:-3])):
        if d[c].notna().any():
            t[f"Recontagem {c[1:-3]}"] = [_cx(v, f) + " cx" if pd.notna(v) else "" for v, f in zip(d[c], d["fator"])]
    t["Diferença"] = [("+" if v > 0 else "") + _cx(v, f) + " cx" if pd.notna(v) else "—"
                      for v, f in zip(d["dif_un"], d["fator"])]
    t["Endereços"] = d["enderecos"].values
    t["Situação"] = d["status"].map(inv.DIA_STATUS).values
    return t


def _d_painel(usuario: dict, op: int, inv_id: int) -> None:
    d = inv.conciliacao_dia(inv_id)
    if d.empty:
        st.info("Suba o 02.05.02 e a contagem do dia em 📥 Bases.")
        return
    if not (inv.inventario(inv_id) or {}).get("base_em"):
        st.warning("Sem 02.05.02 nesta contagem — o estoque está zerado. Suba em 📥 Bases.")
    cont = d["status"].value_counts()
    ok = int(cont.get("ok", 0) + cont.get("ok_rec", 0))
    fechados = len(d) - int(cont.get("pendente", 0)) - int(cont.get("sem_conversao", 0))
    acur = ok / fechados * 100 if fechados else None
    tema.kpis([
        {"titulo": "Produtos contados", "valor": _n(len(d)), "icone": "📦", "status": "info", "dados": _d_tab(d)},
        {"titulo": "Bateram ✔️", "valor": _n(ok), "icone": "✅", "status": "bom",
         "detalhe": f"{_n(cont.get('ok_rec', 0))} depois da recontagem",
         "dados": _d_tab(d[d["status"].isin(["ok", "ok_rec"])]) if ok else None},
        {"titulo": "Com diferença ❌", "valor": _n(cont.get("divergente", 0) + cont.get("confirmado", 0)),
         "icone": "⚠️", "status": "critico" if cont.get("divergente", 0) + cont.get("confirmado", 0) else "bom",
         "detalhe": f"{_n(cont.get('confirmado', 0))} confirmada(s) por 2 contagens",
         "dados": _d_tab(d[d["status"].isin(["divergente", "confirmado"])])
         if cont.get("divergente", 0) + cont.get("confirmado", 0) else None},
        {"titulo": "Em recontagem", "valor": _n(cont.get("pendente", 0)), "icone": "📨", "status": "info",
         "dados": _d_tab(d[d["status"] == "pendente"]) if cont.get("pendente", 0) else None},
        {"titulo": "Acuracidade do dia", "valor": _pct(acur), "icone": "🎯",
         "status": "bom" if (acur or 0) >= 98 else "atencao" if (acur or 0) >= 95 else "critico",
         "detalhe": f"{_n(ok)} de {_n(fechados)} produtos"},
    ], key="kp_invd")
    f = st.radio("Mostrar", ["todos", "ok", "nok"], horizontal=True, key="invd_filtro",
                 format_func={"todos": f"Todos ({len(d)})", "ok": f"✔️ OK ({ok})",
                              "nok": f"❌ Com diferença ({len(d) - ok})"}.get)
    v = d[d["status"].isin(["ok", "ok_rec"])] if f == "ok" else d[~d["status"].isin(["ok", "ok_rec"])] \
        if f == "nok" else d
    ui.tabela(_d_tab(v), vazio="Nenhum produto nesse filtro.", baixar=f"conciliacao_diaria_{inv_id}")
    tema.secao("🔎 Endereços do produto")
    nomes = dict(zip(d["produto"], d["descricao"]))
    p_ = st.selectbox("Produto", d["produto"].tolist(), key="invd_prod", format_func=lambda p: f"{p} · {nomes.get(p)}")
    cd = inv._contagem_dia(inv_id)
    x = cd[cd["produto"] == p_]
    fator = float(d.loc[d["produto"] == p_, "fator"].iloc[0])
    ui.tabela(pd.DataFrame({"Área": x["area"], "Endereço": x["endereco"], "Contou": x["usuario"],
                            "Quantidade": [_cx(q, fator) + " cx" if pd.notna(q) else "—" for q in x["qtd_un"]],
                            "Unid. contada": x["unidades"]}), baixar=False)
    _d_finalizar(usuario, inv_id, d)


def _d_finalizar(usuario: dict, inv_id: int, d: pd.DataFrame) -> None:
    i = inv.inventario(inv_id) or {}
    if i.get("status") == "fechado":
        tema.secao("💾 Conciliação salva")
        st.caption(f"**{i.get('nome')}** — salva por {i.get('finalizado_por') or '—'} em "
                   f"{_dia_hora(i.get('finalizado_em'))}.")
        if st.button("🔓 Reabrir para ajustar", key=f"invd_reabrir_p_{inv_id}"):
            ui.acao(inv.reabrir_diaria, inv_id, sucesso="Conciliação reaberta — finalize de novo quando terminar.")
        return
    tema.secao("✅ Finalizar e salvar conciliação",
               "Vai salvando automático enquanto vocês trabalham. Quando estiver tudo OK, dê um nome e finalize: a "
               "conciliação vai para a pasta do mês.")
    pend = int((d["status"] == "pendente").sum())
    dif = int(d["status"].isin(["divergente"]).sum())
    if pend:
        st.warning(f"📨 {pend} produto(s) ainda estão no app — finalize depois da descarga.")
    elif dif:
        st.info(f"❌ {dif} produto(s) com diferença ainda sem recontagem. Se está certo assim, pode finalizar.")
    with st.form(f"invd_fin_{inv_id}", border=False):
        f1, f2 = st.columns([2, 1])
        nome = f1.text_input("Nome da conciliação", value=f"Conciliação {_dia(i.get('data'))}",
                             key=f"invd_fin_nome_{inv_id}")
        f2.write("")
        if f2.form_submit_button("💾 Finalizar e salvar", type="primary", disabled=bool(pend), **ui.LARGURA):
            try:
                r = inv.finalizar_diaria(inv_id, nome, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(f"💾 “{r['nome']}” salva na pasta do mês ({r['ok']} de {r['produtos']} produtos OK).")
                st.rerun()


def _d_recontagem(usuario: dict, op: int, inv_id: int) -> None:
    if (inv.inventario(inv_id) or {}).get("status") == "fechado":
        st.info("💾 Conciliação salva — reabra em 📊 Painel para criar nova recontagem.")
        return
    d = inv.conciliacao_diaria(inv_id)
    with st.expander("📱 Link do app de recontagem desta revenda"):
        st.code(_link_app(op), language=None)
    if d.empty:
        st.info("Sem contagem ainda.")
        return
    pend = d[d["status"] == "pendente"]
    if len(pend):
        st.info(f"📨 {len(pend)} produto(s) no app para recontar.")
    alvo = d[d["status"].isin(["divergente", "confirmado"])]
    tema.secao("🔁 Criar recontagem", "Aparecem todos os produtos que ainda têm diferença com o estoque. Envie por "
                                     "produto (todos os endereços dele) ou escolha a área e os endereços.")
    if alvo.empty:
        st.success("Nenhum produto com diferença esperando recontagem. 👏")
        _excluir_enviadas(inv_id, "diario")
        return
    modo = ui._escolha("invd_modo", ["produto", "endereco"], "produto",
                       formatar={"produto": "📦 Por produto", "endereco": "📍 Por área e endereço"}.get)
    if modo == "endereco":
        _d_enviar_endereco(usuario, op, inv_id, alvo)
        _excluir_enviadas(inv_id, "diario")
        return
    t = _d_tab(alvo)
    t.insert(0, "Recontar", [s_ == "divergente" for s_ in alvo["status"]])
    ed = st.data_editor(t, hide_index=True, key=f"invd_ed_{inv_id}", **ui.LARGURA,
                        disabled=[c for c in t.columns if c != "Recontar"])
    sel = [p for p, ok in zip(alvo["produto"], ed["Recontar"]) if ok]
    if st.button(f"📨 Criar recontagem para {len(sel)} produto(s)", type="primary", key="invd_criar_rec",
                 disabled=not sel or (inv.inventario(inv_id) or {}).get("status") != "aberto"):
        ui.acao(inv.enviar_recontagem_diaria, inv_id, sel, usuario.get("nome", ""),
                sucesso=f"Recontagem criada para {len(sel)} produto(s) — já está no app.")
    _excluir_enviadas(inv_id, "diario")


def _d_enviar_endereco(usuario: dict, op: int, inv_id: int, alvo: pd.DataFrame) -> None:
    """Diária por área / endereço: só os endereços escolhidos vão para o app (os outros do produto ficam como estão)."""
    cd = inv._contagem_dia(inv_id)
    cd = cd[cd["produto"].isin(alvo["produto"])].copy()
    cd["endereco"] = cd["endereco"].fillna("")
    if cd.empty:
        st.info("Nenhum endereço com diferença.")
        return
    a = inv.areas(op)
    nomes = dict(zip(a["codigo"], a["nome"])) if not a.empty else {}
    areas_ = sorted(cd["area"].unique().tolist())
    f1, f2 = st.columns([1, 1.6])
    area = f1.selectbox("Área", areas_, key=f"invd_env_area_{inv_id}", format_func=lambda x: nomes.get(x, x))
    x = cd[cd["area"] == area]
    ends = sorted(x["endereco"].unique().tolist())
    sel_end = f2.multiselect("Endereços (vazio = todos da área)", ends, key=f"invd_env_ends_{inv_id}_{area}",
                             format_func=lambda e: e or "(sem endereço)")
    if sel_end:
        x = x[x["endereco"].isin(sel_end)]
    fat = dict(zip(alvo["produto"], alvo["fator"]))
    stt = dict(zip(alvo["produto"], alvo["status"]))
    todos = st.checkbox("Marcar todos", value=True, key=f"invd_env_todos_{area}")
    vis = pd.DataFrame({
        "Recontar": todos, "Endereço": x["endereco"].values, "Cód": x["produto"].values,
        "Produto": x["descricao"].fillna("").values,
        "Contou": [_cx(q, fat.get(p, 1)) + " cx" if pd.notna(q) else "—" for q, p in zip(x["qtd_un"], x["produto"])],
        "Situação do produto": [inv.DIA_STATUS.get(stt.get(p), "") for p in x["produto"]]})
    ed = st.data_editor(vis, hide_index=True, key=f"invd_ed_end_{inv_id}_{area}_{'|'.join(sel_end)}_{todos}",
                        **ui.LARGURA, disabled=[c for c in vis.columns if c != "Recontar"])
    marc = x.reset_index(drop=True)[ed["Recontar"].fillna(False).astype(bool).values]
    linhas = list(zip(marc["area"], marc["endereco"], marc["produto"]))
    st.caption("Os outros endereços desses produtos não vão para o app: ficam com a quantidade que já tinham.")
    if st.button(f"📨 Enviar {len(linhas)} endereço×produto para recontagem", type="primary",
                 key=f"invd_env_end_b_{inv_id}", disabled=not linhas):
        ui.acao(inv.enviar_recontagem_diaria, inv_id, [], usuario.get("nome", ""), linhas,
                sucesso=f"{len(linhas)} item(ns) enviados para o app.")


def _excluir_enviadas(inv_id: int, tipo: str) -> None:
    """Local para excluir recontagens já enviadas (no app, contadas ou já descarregadas e não conciliadas)."""
    e = inv.enviadas(inv_id)
    if e.empty:
        return
    with st.expander(f"🗑️ Excluir recontagens enviadas ({len(e)})"):
        st.caption("Tira do app o que foi enviado por engano ou não precisa mais. A contagem anterior volta a valer."
                   + (" Na diária a recontagem é excluída do produto inteiro (todos os endereços dele)."
                      if tipo == "diario" else " O que já foi conciliado não aparece aqui."))
        areas_ = ["__todas__"] + sorted(e["area"].unique().tolist())
        f1, f2 = st.columns([1, 1.6])
        area = f1.selectbox("Área", areas_, key=f"inv_exc_area_{inv_id}",
                            format_func=lambda a: "Todas" if a == "__todas__" else inv._nome_area(a))
        x = e if area == "__todas__" else e[e["area"] == area]
        ends = sorted(x["endereco"].unique().tolist())
        sel_end = f2.multiselect("Endereços", ends, key=f"inv_exc_ends_{inv_id}_{area}",
                                 format_func=lambda v: v or "(sem endereço)")
        if sel_end:
            x = x[x["endereco"].isin(sel_end)]
        todos = st.checkbox("Marcar todos", value=False, key=f"inv_exc_todos_{inv_id}_{area}")
        vis = pd.DataFrame({
            "Excluir": todos, "Rodada": x["rodada"].astype(int).map(lambda r: f"{r}ª").values,
            "Área": x["area"].values, "Endereço": x["endereco"].values, "Cód": x["produto"].values,
            "Produto": x["descricao"].fillna("").values, "Situação": x["status"].map(inv.REC_STATUS).values,
            "Enviado por": x["enviado_por"].fillna("").values,
            "Enviado em": [_dia_hora(v) for v in x["enviado_em"]]})
        ed = st.data_editor(vis, hide_index=True, key=f"inv_exc_ed_{inv_id}_{area}_{'|'.join(sel_end)}_{todos}",
                            **ui.LARGURA, disabled=[c for c in vis.columns if c != "Excluir"])
        ids = [int(i) for i, ok in zip(x["id"], ed["Excluir"].fillna(False)) if ok]
        if st.button(f"🗑️ Excluir {len(ids)} recontagem(ns)", key=f"inv_exc_b_{inv_id}", disabled=not ids):
            ui.acao(inv.excluir_recontagem, ids, sucesso=f"{len(ids)} recontagem(ns) excluída(s).")


def _d_bases(usuario: dict, op: int, inv_id: int) -> None:
    from core.auth import e_master

    i = inv.inventario(inv_id) or {}
    aberto = i.get("status") == "aberto"
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"**1. 02.05.02 do dia (estoque)**  \nÚltima carga: "
                    f"{pd.to_datetime(i['base_em']).strftime('%d/%m/%Y %H:%M') if i.get('base_em') else 'nunca'}")
        v = st.session_state.get("invd_up_b_v", 0)
        arq = st.file_uploader("02.05.02", type=arquivos.FORMATOS, key=f"invd_up_b_{v}", label_visibility="collapsed",
                               disabled=not aberto)
        if arq is not None and st.button("Gravar 02.05.02", type="primary", key="invd_grava_b"):
            try:
                a2 = arquivos.preparar(arq)
                r = inv.importar_base(inv_id, a2.getvalue(), a2.name, usuario.get("nome", ""))
                n = inv.auto_primeira_recontagem(inv_id, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["invd_up_b_v"] = v + 1
                ui.avisar(f"02.05.02: {r['produtos']} produtos." + (f" {n} produto(s) com diferença foram para a 1ª "
                                                                    "recontagem." if n else ""))
                st.rerun()
        deps = inv.depositos_base(inv_id)
        if deps:
            atuais = [x for x in str(i.get("depositos") or "").split(",") if x in deps] or deps
            sel = st.multiselect("Depósitos", deps, default=atuais, key=f"invd_deps_{inv_id}", disabled=not aberto)
            if aberto and sorted(sel) != sorted(atuais):
                inv.salvar_depositos(inv_id, sel)
                ui.salvo_automatico("Depósitos salvos.")
    with c2, st.container(border=True):
        st.markdown("**2. Contagem do dia (WMS)**")
        st.caption("Uma contagem só: o que não bater com o estoque vai sozinho para a 1ª recontagem no app.")
        v2 = st.session_state.get("invd_up_c_v", 0)
        arqs = st.file_uploader("Contagem", type=arquivos.FORMATOS, key=f"invd_up_c_{v2}", accept_multiple_files=True,
                                label_visibility="collapsed", disabled=not aberto)
        arqs = [a for a in (arqs or []) if a is not None]
        if arqs and st.button(f"Gravar {len(arqs)} arquivo(s)", type="primary", key="invd_grava_c"):
            erros, n = [], 0
            for a in arqs:
                try:
                    a2 = arquivos.preparar(a)
                    r = inv.importar_contagem(inv_id, a2.getvalue(), a2.name, usuario.get("nome", ""))
                except RegraNegocioError as e:
                    erros.append(f"{a.name}: {e}")
                else:
                    ui.avisar(f"{a.name}: {r['linhas']} linhas · {r['enderecos']} endereços · {r['itens']} produtos.")
            if not erros and i.get("base_em"):
                n = inv.auto_primeira_recontagem(inv_id, usuario.get("nome", ""))
                if n:
                    ui.avisar(f"{n} produto(s) com diferença foram para a 1ª recontagem no app.")
            for e in erros:
                st.error(e)
            if not erros:
                st.session_state["invd_up_c_v"] = v2 + 1
                st.rerun()
    if not aberto:
        st.caption("💾 Conciliação salva — para subir de novo, reabra em 📊 Painel.")
    elif e_master(usuario) and st.button("🗑️ Excluir esta contagem do dia", key=f"invd_excluir_{inv_id}"):
        ui.acao(inv.excluir, inv_id, sucesso="Contagem do dia excluída.")
