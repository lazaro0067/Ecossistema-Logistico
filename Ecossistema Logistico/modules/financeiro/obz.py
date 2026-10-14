"""Financeiro › 🎯 Gestão OBZ — Plan × Tend × Real, dispersão, L-E, justificativas, aprovação, reuniões e cadastros."""
import datetime as dt

import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from repositories import usuarios_repo
from services import obz_service as obz
from services.erros import RegraNegocioError


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+.1f}%".replace(".", ",")


def _farol(desf, critica) -> str:
    if critica and desf > 0:
        return "🔴"
    if desf > 0:
        return "🟡"
    return "🟢"


def _seletor_mes(op: int, chave: str, container=None):
    meses = obz.meses(op)
    return ui.seletor_mes("Mês", meses, key=chave, container=container or st.columns([1, 3])[0])


def _usuarios() -> dict[int, str]:
    return {u["id"]: u["nome"] for u in usuarios_repo.listar(apenas_ativos=True) if u["perfil"] != "Motorista"}


def _sem_dados(op: int) -> bool:
    if not obz.contas().empty:
        return False
    st.info("Comece em **📥 Realizado (16.03.01)**: ao subir o relatório, as contas e os departamentos são "
            "cadastrados sozinhos. Depois suba o **🎯 Plan** pela planilha modelo.")
    return True


# --- 📊 Gestão ----------------------------------------------------------------------------------------------
def render_gestao(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "obz_gestao")
    if _sem_dados(op):
        return
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    mes = _seletor_mes(op, "obz_g_mes", c1)
    b = obz.base(op, mes)
    if b.empty:
        st.info(f"Sem plan, real ou tendência em {obz.nome_mes(mes)}.")
        return
    fp = c2.multiselect("Pacote", sorted(b["pacote"].unique()), key="obz_g_pac", placeholder="Todos")
    fd = c3.multiselect("Departamento", sorted(b["nome_depto"].unique()), key="obz_g_dep", placeholder="Todos")
    fdo = c4.multiselect("Dono", sorted(b["dono"].dropna().unique()), key="obz_g_dono", placeholder="Todos")
    if fp:
        b = b[b["pacote"].isin(fp)]
    if fd:
        b = b[b["nome_depto"].isin(fd)]
    if fdo:
        b = b[b["dono"].isin(fdo)]
    if b.empty:
        st.info("Nada com esses filtros.")
        return
    t = b[["plan", "real", "tend", "fechamento", "disp", "desfavoravel"]].sum()
    fechado = obz.fechado(mes)
    crit = b[b["critica"] & (b["desfavoravel"] > 0)]
    pend = b[b["status"] == "aguardando"]
    tema.kpis([
        {"titulo": f"Plan · {obz.nome_mes(mes)}", "valor": _m(t["plan"]), "icone": "🎯", "status": "info"},
        {"titulo": "Real", "valor": _m(t["real"]), "icone": "📥", "status": "info",
         "detalhe": "mês fechado" if fechado else "realizado até agora (16.03.01)"},
        {"titulo": "Tend (fechamento)", "valor": _m(t["tend"]), "icone": "🔮", "status": "info",
         "detalhe": f"{int(b['tend_lancada'].sum())} de {len(b)} lançadas · resto = sugestão"},
        {"titulo": "Dispersão", "valor": _m(t["disp"]), "icone": "⚖️",
         "status": "critico" if t["desfavoravel"] > 0 else "bom",
         "detalhe": f"{_p(t['disp'] / t['plan'] * 100) if t['plan'] else '—'} sobre o plan · "
                    f"{'real' if fechado else 'tend'} − plan"},
        {"titulo": "Contas críticas", "valor": ui.numero(len(crit)), "icone": "🚨",
         "status": "critico" if len(crit) else "bom", "detalhe": "acima do limite de dispersão",
         "dados": _vis_base(crit) if len(crit) else None},
        {"titulo": "Justificativas p/ aprovar", "valor": ui.numero(len(pend)), "icone": "⏳",
         "status": "atencao" if len(pend) else "bom", "detalhe": "aguardando o financeiro"},
    ], key="kp_obz_g")

    ab = ui._escolha("obz_g_ab", ["pacote", "conta", "depto", "detalhe"], "pacote", pills=True,
                     formatar={"pacote": "📦 Por pacote", "conta": "🧾 Por conta", "depto": "🏢 Por departamento",
                               "detalhe": "🔎 Conta × depto"}.get)
    if ab == "detalhe":
        ui.tabela(_vis_base(b), baixar=f"obz_{mes}_detalhe")
        _drill(op, mes, b)
    else:
        chave = {"pacote": ["pacote"], "conta": ["conta", "nome_conta"], "depto": ["depto", "nome_depto"]}[ab]
        g = b.groupby(chave, as_index=False)[["plan", "real", "tend", "fechamento", "disp", "desfavoravel"]].sum()
        g["disp_pct"] = g["disp"] / g["plan"].where(g["plan"] != 0) * 100
        g = g.sort_values("desfavoravel", ascending=False).reset_index(drop=True)
        rot = g[chave[-1]] if len(chave) == 1 else g[chave[0]].astype(str) + " · " + g[chave[1]].fillna("")
        graficos.mostrar(graficos.barras_h(rot.head(15), g["disp"].head(15).round(0),
                                           cores=["#c0392b" if d > 0 else graficos.CATEGORICAS[0]
                                                  for d in g["desfavoravel"].head(15)],
                                           textos=[_m(v) for v in g["disp"].head(15)],
                                           titulo="Dispersão (fechamento − plan) — maiores desvios"), key=f"g_obz_{ab}")
        vis = pd.DataFrame({"": [("🔴" if d > 0 else "🟢") for d in g["desfavoravel"]], "Grupo": rot,
                            "Plan": g["plan"].map(_m), "Real": g["real"].map(_m), "Tend": g["tend"].map(_m),
                            "Dispersão": g["disp"].map(_m), "Disp. %": g["disp_pct"].map(_p)})
        vis.loc[len(vis)] = ["Σ", "TOTAL", _m(t["plan"]), _m(t["real"]), _m(t["tend"]), _m(t["disp"]),
                             _p(t["disp"] / t["plan"] * 100) if t["plan"] else "—"]
        ui.tabela(vis, baixar=f"obz_{mes}_{ab}")
        if ab == "conta":
            _drill(op, mes, b)

    tema.secao("📆 L-E do ano (latest estimate)",
               "Real dos meses fechados + tend do mês aberto + plan dos meses que faltam × plan do ano.")
    _le(op, mes[:4])


def _vis_base(b: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "": [_farol(d, c) for d, c in zip(b["desfavoravel"], b["critica"])],
        "Conta": b["conta"].astype(str) + " · " + b["nome_conta"].fillna(""), "Depto": b["nome_depto"],
        "Pacote": b["pacote"], "Plan": b["plan"].map(_m), "Real": b["real"].map(_m),
        "Fech. mês anterior": b["fech_ant"].map(_m), "Tend": b["tend"].map(_m),
        "Dispersão": b["disp"].map(_m), "Disp. %": b["disp_pct"].map(_p),
        "Limite": b["limite"].map(lambda v: f"{v:.0f}%"), "Status": b["status"].map(obz.STATUS),
        "Justificativa": b["justificativa"].fillna(""), "Dono": b["dono"].fillna(""),
        "Sub-dono": b["subdono"].fillna("")}).reset_index(drop=True)


def _drill(op: int, mes: str, b: pd.DataFrame) -> None:
    with st.expander("🔎 Lançamentos de uma conta (16.03.01)"):
        contas = b.drop_duplicates("conta")
        conta = st.selectbox("Conta", contas["conta"].tolist(), key="obz_drill",
                             format_func=lambda c: f"{c} · {contas.set_index('conta').at[c, 'nome_conta']}")
        lan = obz.lancamentos(op, mes, conta)
        if lan.empty:
            st.info("Sem lançamentos no mês.")
            return
        nd = obz.nomes_deptos()
        ui.tabela(pd.DataFrame({"Data": pd.to_datetime(lan["data"]).dt.strftime("%d/%m/%Y"),
                                "Depto": lan["depto"].map(lambda d: obz.rotulo_depto(d, nd)),
                                "Histórico": lan["historico"], "Débito (H)": lan["debito"].map(_m),
                                "Crédito (I)": lan["credito"].map(_m)}), baixar=f"lancamentos_{conta}_{mes}")


def _le(op: int, ano: str) -> None:
    le = obz.le_ano(op, ano)
    if le.empty:
        st.info("Sem plan/real no ano.")
        return
    m = le.groupby(["mes", "fonte"], as_index=False)[["plan", "real", "le"]].sum()
    x = [obz.nome_mes(v) for v in m["mes"]]
    graficos.mostrar(graficos.barras(x, {"Plan": m["plan"].round(0), "L-E (real/tend/plan)": m["le"].round(0)},
                                     titulo=f"Plan × L-E por mês — {ano}"), key="g_obz_le")
    g = le.groupby(["conta", "nome_conta", "pacote"], as_index=False)[["plan", "real", "le"]].sum()
    g["disp"] = g["le"] - g["plan"]
    g = g.sort_values("disp", ascending=False).reset_index(drop=True)
    vis = pd.DataFrame({"Conta": g["conta"].astype(str) + " · " + g["nome_conta"].fillna(""), "Pacote": g["pacote"],
                        "Plan ano": g["plan"].map(_m), "Real acumulado": g["real"].map(_m), "L-E": g["le"].map(_m),
                        "L-E − Plan": g["disp"].map(_m),
                        "%": (g["disp"] / g["plan"].where(g["plan"] != 0) * 100).map(_p)})
    vis.loc[len(vis)] = ["TOTAL", "", _m(g["plan"].sum()), _m(g["real"].sum()), _m(g["le"].sum()),
                         _m(g["disp"].sum()), _p(g["disp"].sum() / g["plan"].sum() * 100) if g["plan"].sum() else "—"]
    ui.tabela(vis, baixar=f"obz_LE_{ano}")


# --- 📝 Tendências --------------------------------------------------------------------------------------
def render_tend(usuario: dict, operacao_id: int) -> None:
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        st.info("Escolha uma revenda no menu para lançar as tendências.")
        return
    if _sem_dados(operacao_id):
        return
    mes = _seletor_mes(operacao_id, "obz_t_mes")
    b = obz.base(operacao_id, mes)
    if b.empty:
        st.info("Sem contas para este mês (suba o plan ou o realizado).")
        return
    minhas = b[[obz.pode_lancar(usuario, c, d) for c, d in zip(b["conta"], b["depto"])]]
    if minhas.empty:
        st.warning("Você não é dono, sub-dono nem lançador de nenhuma conta. Peça o cadastro em ⚙️ Cadastros OBZ.")
        return
    so_crit = st.toggle("Mostrar só as críticas", key="obz_t_crit")
    if so_crit:
        minhas = minhas[minhas["critica"]]
    st.caption(f"💡 Tend sugerida = fechamento de {obz.nome_mes(obz.mes_anterior(mes))} (sem ele, o plan); se o real do "
               f"mês já passou disso, o próprio real. Dispersão ≥ limite da conta (padrão {obz.limite_padrao():.0f}%) é crítica: escreva a "
               "justificativa — vai para aprovação do financeiro.")
    ed = pd.DataFrame({
        "conta": minhas["conta"], "depto": minhas["depto"], "farol": [_farol(d, c) for d, c in
                                                                       zip(minhas["desfavoravel"], minhas["critica"])],
        "Conta": minhas["conta"].astype(str) + " · " + minhas["nome_conta"].fillna(""),
        "Depto": minhas["nome_depto"], "Plan": minhas["plan"], "Real até agora": minhas["real"],
        "Fech. anterior": minhas["fech_ant"], "Sugestão": minhas["sugerido"].round(2),
        "Tend": minhas["tend"].round(2), "Justificativa": minhas["justificativa"].fillna(""),
        "Status": minhas["status"].map(obz.STATUS)}).reset_index(drop=True)
    din = st.column_config.NumberColumn
    editado = st.data_editor(ed, hide_index=True, key=f"obz_t_ed_{mes}", **ui.LARGURA,
                             disabled=[c for c in ed.columns if c not in ("Tend", "Justificativa")],
                             column_order=["farol", "Conta", "Depto", "Plan", "Real até agora", "Fech. anterior",
                                           "Sugestão", "Tend", "Justificativa", "Status"],
                             column_config={"farol": st.column_config.TextColumn("", width="small"),
                                            "Plan": din(format="R$ %.2f"), "Real até agora": din(format="R$ %.2f"),
                                            "Fech. anterior": din(format="R$ %.2f"), "Sugestão": din(format="R$ %.2f"),
                                            "Tend": din("Tend ✏️", format="R$ %.2f"),
                                            "Justificativa": st.column_config.TextColumn("Justificativa ✏️",
                                                                                         width="large")})
    b1, b2, _ = st.columns([1, 1, 2])
    salvar = b1.button("💾 Lançar tendências", type="primary", key="obz_t_salvar")
    aceitar = b2.button("💡 Lançar todas as sugestões", key="obz_t_aceitar",
                        help="Lança a sugestão nas linhas ainda não lançadas (as críticas pedem justificativa).")
    if salvar or aceitar:
        ok, erros = 0, []
        for (_, orig), (_, novo) in zip(ed.iterrows(), editado.iterrows()):
            linha = minhas[(minhas["conta"] == orig["conta"]) & (minhas["depto"] == orig["depto"])].iloc[0]
            mudou = (abs(float(novo["Tend"] or 0) - float(orig["Tend"] or 0)) > 0.005
                     or (novo["Justificativa"] or "") != (orig["Justificativa"] or ""))
            if aceitar and not linha["tend_lancada"]:
                mudou = True
            if not mudou:
                continue
            try:
                obz.salvar_tend(operacao_id, mes, orig["conta"], orig["depto"], float(novo["Tend"] or 0), usuario,
                                novo["Justificativa"] or "", float(linha["plan"]), float(linha["sugerido"]))
                ok += 1
            except RegraNegocioError as e:
                erros.append(f"{orig['Conta']} / {orig['Depto']}: {e}")
        if erros:
            st.error("Não lançadas:\n\n- " + "\n- ".join(erros))
        if ok:
            ui.avisar(f"{ok} tendência(s) lançada(s). As críticas foram para aprovação do financeiro.")
            if not erros:
                st.rerun()


# --- ✔️ Aprovação ----------------------------------------------------------------------------------------
def render_aprovacao(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "obz_aprov")
    pend = obz.pendentes(op)
    pode = obz.pode_aprovar(usuario)
    if pend.empty:
        st.success("Nenhuma justificativa aguardando aprovação. 👏")
    else:
        st.caption("Dispersões críticas justificadas por quem lançou a tendência — o financeiro aprova ou devolve.")
        nd = obz.nomes_deptos()
        for _, r in pend.iterrows():
            disp = float(r["valor"] or 0)
            with st.container(border=True):
                c1, c2 = st.columns([3, 1.3])
                c1.markdown(f"**{r['conta']} · {r['nome_conta'] or ''}** — {obz.rotulo_depto(r['depto'], nd)} · "
                            f"{obz.nome_mes(r['mes'])} · {r['revenda']}  \nTend **{_m(disp)}** (sugestão "
                            f"{_m(r['sugerido'])}) · criticado por **{r['criticado_por']}** em {r['criticado_em']}  \n"
                            f"💬 _{r['justificativa']}_")
                if pode:
                    com = c2.text_input("Comentário", key=f"obz_ap_c_{r['id']}", label_visibility="collapsed",
                                        placeholder="comentário (obrigatório para devolver)")
                    a1, a2 = c2.columns(2)
                    if a1.button("✔️ Aprovar", key=f"obz_ap_ok_{r['id']}", type="primary"):
                        ui.acao(obz.aprovar, int(r["id"]), usuario, True, com, sucesso="Justificativa aprovada.")
                    if a2.button("↩️ Devolver", key=f"obz_ap_no_{r['id']}"):
                        ui.acao(obz.aprovar, int(r["id"]), usuario, False, com, sucesso="Devolvida para revisão.")
        if not pode:
            st.info("Só os aprovadores do financeiro (⚙️ Cadastros OBZ) aprovam.")
    with st.expander("🕒 Histórico de justificativas do mês"):
        mes = _seletor_mes(op, "obz_ap_mes")
        t = obz.tend_df(op, mes)
        t = t[t["justificativa"].notna()] if not t.empty else t
        if t.empty:
            st.info("Sem justificativas no mês.")
        else:
            ui.tabela(pd.DataFrame({"Conta": t["conta"], "Depto": t["depto"], "Tend": t["valor"].map(_m),
                                    "Justificativa": t["justificativa"], "Criticado por": t["criticado_por"],
                                    "Em": t["criticado_em"], "Status": t["status"].map(obz.STATUS),
                                    "Aprovador": t["aprovador"].fillna(""), "Comentário": t["comentario_aprov"].fillna("")}),
                      baixar=f"justificativas_{mes}")


# --- 🗓️ Reunião -------------------------------------------------------------------------------------------
def render_reuniao(usuario: dict, operacao_id: int) -> None:
    op = ui.visao_acompanhamento(usuario, operacao_id, "obz_reun")
    if _sem_dados(op):
        return
    mes = _seletor_mes(op, "obz_r_mes")
    b = obz.base(op, mes)
    neg, pos = obz.top_dispersoes(b)
    for titulo, d in (("🔴 Top 10 dispersões negativas (acima do plano)", neg),
                      ("🟢 Top 10 dispersões positivas (abaixo do plano / economia)", pos)):
        tema.secao(titulo)
        if d.empty:
            st.info("Nenhuma.")
            continue
        vis = pd.DataFrame({"Conta": d["conta"].astype(str) + " · " + d["nome_conta"].fillna(""),
                            "Pacote": d["pacote"], "Plan": d["plan"].map(_m),
                            "Fechamento": d["fechamento"].map(_m), "Dispersão": d["disp"].map(_m),
                            "Disp. %": d["disp_pct"].map(_p), "Justificativa": d["justificativa"].fillna("—")})
        vis.loc[len(vis)] = ["TOTAL", "", _m(d["plan"].sum()), _m(d["fechamento"].sum()), _m(d["disp"].sum()), "", ""]
        ui.tabela(vis, baixar=f"reuniao_{mes}_{titulo[:2]}")

    tema.secao("✅ Plano de ação", "Ações combinadas na reunião — responsável, prazo e status.")
    contas_opc = [""] + sorted(set(b["conta"]) if not b.empty else set())
    with st.form("obz_acao_nova", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1.2, 2.5, 1.2, 1])
        conta = c1.selectbox("Conta", contas_opc, key="obz_ac_conta")
        acao = c2.text_input("Ação")
        resp = c3.text_input("Responsável")
        prazo = c4.date_input("Prazo", value=dt.date.today() + dt.timedelta(days=15), format="DD/MM/YYYY")
        if st.form_submit_button("➕ Adicionar ação", type="primary"):
            ui.acao(obz.salvar_acao, op, mes, {"conta": conta or None, "acao": acao, "responsavel": resp,
                                               "prazo": prazo.isoformat()}, usuario, sucesso="Ação registrada.")
    ac = obz.acoes(op, mes)
    if ac.empty:
        st.info("Nenhuma ação registrada neste mês.")
    else:
        ed = pd.DataFrame({"id": ac["id"], "Conta": ac["conta"].fillna(""), "Ação": ac["acao"],
                           "Responsável": ac["responsavel"].fillna(""), "Prazo": ac["prazo"].fillna(""),
                           "Status": ac["status"].fillna("Aberta"), "Excluir": False})
        novo = st.data_editor(ed, hide_index=True, key=f"obz_ac_ed_{mes}", **ui.LARGURA, disabled=["id"],
                              column_config={"id": None, "Status": st.column_config.SelectboxColumn(
                                  options=["Aberta", "Em andamento", "Concluída", "Cancelada"]),
                                  "Excluir": st.column_config.CheckboxColumn("🗑️")})
        if st.button("💾 Salvar ações", key="obz_ac_salvar"):
            for (_, o), (_, n) in zip(ed.iterrows(), novo.iterrows()):
                if n["Excluir"]:
                    obz.excluir_acao(int(o["id"]))
                elif any(o[c] != n[c] for c in ("Conta", "Ação", "Responsável", "Prazo", "Status")):
                    obz.salvar_acao(op, mes, {"conta": n["Conta"] or None, "acao": n["Ação"],
                                              "responsavel": n["Responsável"], "prazo": n["Prazo"],
                                              "status": n["Status"]}, usuario, int(o["id"]))
            ui.avisar("Ações atualizadas.")
            st.rerun()

    tema.secao("📝 Ata da reunião")
    with st.form("obz_ata", clear_on_submit=True):
        c1, c2 = st.columns([1, 3])
        data = c1.date_input("Data", value=dt.date.today(), format="DD/MM/YYYY")
        part = c2.text_input("Participantes")
        ata = st.text_area("Pontos discutidos / decisões")
        if st.form_submit_button("Salvar ata"):
            ui.acao(obz.salvar_reuniao, op, mes, data.isoformat(), part, ata, usuario, sucesso="Ata salva.")
    for _, r in obz.reunioes(op, mes).iterrows():
        with st.expander(f"🗓️ {r['data']} · {r['participantes'] or ''}"):
            st.write(r["ata"])
            st.caption(f"Registrada por {r['criado_por']}")


# --- 🎯 Plan -------------------------------------------------------------------------------------------------
def render_plan(usuario: dict, operacao_id: int) -> None:
    from repositories import operacoes_repo

    tema.secao("🎯 Plan (metas mensais por conta × departamento)",
               "1) Baixe a planilha modelo · 2) preencha Jan…Dez · 3) suba aqui. Subir de novo substitui o ano.")
    if operacoes_repo.e_consolidada(operacao_id):
        st.info("Escolha uma revenda no menu.")
        return
    c1, c2 = st.columns([1, 3])
    ano = c1.selectbox("Ano", [str(dt.date.today().year + i) for i in (0, 1, -1)], key="obz_p_ano")
    c2.write("")
    c2.download_button("⬇️ Baixar planilha modelo", obz.modelo_plan(operacao_id, ano),
                       file_name=f"modelo_plan_obz_{ano}.xlsx", key="obz_p_baixar",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    arq = st.file_uploader("Planilha do plan preenchida", type=["xlsx", "csv"], key="obz_p_up")
    if arq is not None and st.button("Gravar plan", type="primary", key="obz_p_gravar"):
        try:
            n = obz.importar_plan(arq.getvalue(), arq.name, operacao_id, ano)
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar(f"Plan {ano}: {n} valores gravados.")
            st.rerun()
    pl = obz.plan_df(operacao_id, f"{ano}-01", f"{ano}-12")
    if pl.empty:
        st.info(f"Ainda não há plan para {ano}.")
        return
    piv = pl.pivot_table(index="conta", columns="mes", values="valor", aggfunc="sum", fill_value=0)
    ct = obz.contas().set_index("codigo")["nome"]
    piv.columns = [obz.nome_mes(c)[:3] for c in piv.columns]
    piv["Total"] = piv.sum(axis=1)
    out = piv.map(_m) if hasattr(piv, "map") else piv.applymap(_m)
    out.insert(0, "Conta", [f"{c} · {ct.get(c, '')}" for c in piv.index])
    ui.tabela(out.reset_index(drop=True), baixar=f"plan_obz_{ano}")


# --- 📥 Realizado ----------------------------------------------------------------------------------------
def render_real(usuario: dict, operacao_id: int) -> None:
    from repositories import operacoes_repo

    tema.secao("📥 Realizado — relatório 16.03.01",
               "Coluna H = débito, coluna I = crédito. Despesa: real = débito − crédito; receita: crédito − débito. "
               "Subir de novo um mês substitui o mês. Contas e departamentos novos são cadastrados sozinhos.")
    if operacoes_repo.e_consolidada(operacao_id):
        st.info("Escolha uma revenda no menu.")
        return
    arq = st.file_uploader("16.03.01 (.csv)", type=["csv", "zip"], key="obz_r_up")
    if arq is not None and st.button("Gravar realizado", type="primary", key="obz_r_gravar"):
        try:
            r = obz.importar_real(arq.getvalue(), arq.name, operacao_id, usuario.get("nome", ""))
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar(f"16.03.01: {r['lancamentos']} lançamentos · {r['contas']} contas · {r['deptos']} deptos · "
                      f"{', '.join(obz.nome_mes(m) for m in r['meses'])}.")
            st.rerun()
    meses = [m for m in obz.meses(operacao_id)]
    tab = []
    for m in meses:
        rl = obz.real_df(operacao_id, m, m)
        if not rl.empty:
            tab.append({"Mês": obz.nome_mes(m), "Contas": rl["conta"].nunique(), "Débito": _m(rl["debito"].sum()),
                        "Crédito": _m(rl["credito"].sum())})
    if tab:
        ui.tabela(pd.DataFrame(tab), baixar=False)


# --- ⚙️ Cadastros -------------------------------------------------------------------------------------------
def render_cadastros(usuario: dict, operacao_id: int) -> None:
    from core.auth import e_master

    users = _usuarios()
    opc_u = [None] + list(users)
    fmt_u = lambda i: "—" if i is None else users.get(i, str(i))  # noqa: E731
    pode = e_master(usuario) or obz.pode_aprovar(usuario)
    if not pode:
        st.info("Somente o Master e os aprovadores do financeiro alteram os cadastros do OBZ.")
    aba = ui._escolha("obz_c_aba", ["deptos", "contas", "subdonos", "papeis"], "deptos", pills=True,
                      formatar={"deptos": "🏢 Departamentos", "contas": "🧾 Contas & donos",
                                "subdonos": "👥 Sub-donos (conta × depto)", "papeis": "🔑 Lançadores & aprovadores"}.get)
    if aba == "deptos":
        d = obz.departamentos()
        ed = pd.DataFrame({"codigo": d["codigo"], "nome": d["nome"].fillna(""), "ativo": d["ativo"].astype(int) == 1,
                           "excluir": False})
        novo = st.data_editor(ed, hide_index=True, num_rows="dynamic", key="obz_c_dep", **ui.LARGURA,
                              disabled=not pode,
                              column_config={"codigo": "Código", "nome": st.column_config.TextColumn("Nome ✏️"),
                                             "ativo": "Ativo", "excluir": st.column_config.CheckboxColumn("🗑️")})
        if pode and st.button("💾 Salvar departamentos", key="obz_c_dep_s", type="primary"):
            for _, r in novo.iterrows():
                if not str(r["codigo"] or "").strip() or str(r["codigo"]) == "nan":
                    continue
                if r["excluir"]:
                    obz.excluir_depto(str(r["codigo"]))
                else:
                    obz.salvar_depto(str(r["codigo"]), r["nome"] or "", bool(r["ativo"]))
            ui.avisar("Departamentos salvos.")
            st.rerun()
    elif aba == "contas":
        c1, c2 = st.columns([1, 3])
        lim = c1.number_input("Limite de dispersão padrão (%)", min_value=1.0, max_value=100.0, value=obz.limite_padrao(),
                              step=1.0, key="obz_c_lim")
        if pode and c2.button("Salvar limite padrão", key="obz_c_lim_s"):
            ui.acao(obz.salvar_limite_padrao, lim, sucesso="Limite padrão salvo.")
        ct = obz.contas()
        ed = pd.DataFrame({"codigo": ct["codigo"], "nome": ct["nome"].fillna(""), "pacote": ct["pacote"].fillna(""),
                           "natureza": ct["natureza"].fillna("despesa"), "no_obz": ct["no_obz"].astype(int) == 1,
                           "limite_pct": pd.to_numeric(ct["limite_pct"], errors="coerce"),
                           "dono": [users.get(i) if pd.notna(i) else None for i in ct["dono_id"]], "excluir": False})
        pacotes = sorted(set(ed["pacote"]) | {p for _, p in obz._PACOTES} | {"Despesas gerais", "Despesas financeiras",
                                                                           "Receitas financeiras", "Patrimonial",
                                                                           "Compras de mercadoria"})
        novo = st.data_editor(ed, hide_index=True, num_rows="dynamic", key="obz_c_ct", **ui.LARGURA, disabled=not pode,
                              column_config={
                                  "codigo": "Conta", "nome": st.column_config.TextColumn("Nome ✏️"),
                                  "pacote": st.column_config.SelectboxColumn("Pacote ✏️", options=pacotes),
                                  "natureza": st.column_config.SelectboxColumn("Natureza", options=["despesa", "receita"]),
                                  "no_obz": st.column_config.CheckboxColumn("Entra no OBZ"),
                                  "limite_pct": st.column_config.NumberColumn("Limite disp. % (vazio = padrão)",
                                                                              min_value=0, max_value=100),
                                  "dono": st.column_config.SelectboxColumn("Dono", options=list(users.values())),
                                  "excluir": st.column_config.CheckboxColumn("🗑️")})
        if pode and st.button("💾 Salvar contas", key="obz_c_ct_s", type="primary"):
            por_nome = {v: k for k, v in users.items()}
            for _, r in novo.iterrows():
                if not str(r["codigo"] or "").strip() or str(r["codigo"]) == "nan":
                    continue
                if r["excluir"]:
                    obz.excluir_conta(str(r["codigo"]))
                    continue
                obz.salvar_conta(str(r["codigo"]), r["nome"] or "", r["pacote"] or None, r["natureza"] or "despesa",
                                 bool(r["no_obz"]), None if pd.isna(r["limite_pct"]) else float(r["limite_pct"]),
                                 por_nome.get(r["dono"]))
            ui.avisar("Contas salvas.")
            st.rerun()
    elif aba == "subdonos":
        st.caption("O sub-dono responde pela conta naquele departamento e pode lançar a tendência dela.")
        ct = obz.contas(so_obz=True)
        dp = obz.departamentos(so_ativos=True)
        with st.form("obz_c_sd"):
            c1, c2, c3 = st.columns([2, 2, 2])
            conta = c1.selectbox("Conta", ct["codigo"].tolist(),
                                 format_func=lambda c: f"{c} · {ct.set_index('codigo').at[c, 'nome']}")
            depto = c2.selectbox("Departamento", dp["codigo"].tolist(), format_func=obz.rotulo_depto)
            uid = c3.selectbox("Sub-dono", opc_u, format_func=fmt_u)
            if st.form_submit_button("Salvar sub-dono", disabled=not pode):
                ui.acao(obz.salvar_subdono, conta, depto, uid, sucesso="Sub-dono salvo.")
        sd = obz.subdonos()
        if not sd.empty:
            nd = obz.nomes_deptos()
            cn = ct.set_index("codigo")["nome"]
            ui.tabela(pd.DataFrame({"Conta": sd["conta"] + " · " + sd["conta"].map(cn).fillna(""),
                                    "Departamento": sd["depto"].map(lambda d: obz.rotulo_depto(d, nd)),
                                    "Sub-dono": sd["subdono"]}), baixar="obz_subdonos")
    else:
        for papel, rot in obz.PAPEIS.items():
            atuais = obz.usuarios_papel(papel)
            sel = st.multiselect(rot, list(users), default=[u for u in atuais if u in users], format_func=fmt_u,
                                 key=f"obz_c_pap_{papel}")
            if pode and st.button("Salvar", key=f"obz_c_pap_s_{papel}"):
                ui.acao(obz.salvar_papel, papel, sel, sucesso="Salvo.")
        st.caption("Donos (por conta) e sub-donos (conta × depto) também lançam tendências das suas contas. "
                   "Aprovadores recebem notificação quando chega justificativa crítica.")
