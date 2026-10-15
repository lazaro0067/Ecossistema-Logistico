"""Gestão Corporativa › 💰 Financeiro › 🏬 Estoque (02.05.02 inicial × final) e 📑 DRE."""
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from services import estoque_valor_service as ev
from services import faturamento_service as fs

_TELAS = {"dep": "🏬 Por depósito", "prod": "📦 Por produto", "cat": "🧩 Por categoria", "neg": "⚠️ Saldos negativos"}
_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _n(v, casas=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, casas)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%".replace(".", ",")


def _div(a, b):
    return a / b if a is not None and b else None


def _ir_relatorios(chave: str) -> None:
    if st.button("📥 Abrir Relatórios", key=f"ir_rel_{chave}", type="primary"):
        st.session_state["nav_corporativo_grupo"] = st.session_state["nav_corporativo_grupo__ultima"] = "📥 Relatórios"
        st.rerun()


def _nome_mes(m: str) -> str:
    return f"{_MESES[int(m[5:]) - 1]}/{m[:4]}"


# --- Estoque -------------------------------------------------------------------------------------------
def _config_depositos(op: int) -> None:
    fim, _ = ev.saldo(op, ev.meses(op)[0], "final")
    ini, _ = ev.saldo(op, ev.meses(op)[0], "inicial")
    base = pd.concat([fim, ini])
    if base.empty:
        return
    nomes = ev.nomes_depositos()
    codigos = sorted({f"{a}-{d}" for a, d in zip(base["armazem"], base["deposito"])})
    rot = lambda c: ev.rotulo_deposito(*c.split("-"), nomes)  # noqa: E731
    with st.expander("⚙️ Depósitos que entram no CMV / DRE e nomes dos depósitos"):
        atuais = ev.depositos_cmv() or codigos
        sel = st.multiselect("Depósitos considerados no estoque do CMV", codigos,
                             default=[c for c in atuais if c in codigos], format_func=rot, key="ev_deps")
        if st.button("Salvar depósitos", key="ev_deps_salvar"):
            ui.acao(ev.salvar_depositos_cmv, sel if len(sel) < len(codigos) else [], sucesso="Depósitos salvos.")
        st.caption("Dê nome aos depósitos (ex.: 01 = Principal, 03 = Avaria):")
        cols = st.columns(4)
        for i, c in enumerate(codigos):
            a, d = c.split("-")
            novo = cols[i % 4].text_input(f"Arm. {a} · Dep. {d}", value=nomes.get((a, d), ""), key=f"ev_nome_{c}")
            if novo != nomes.get((a, d), ""):
                ev.salvar_nome_deposito(a, d, novo)


def _tab_itens(d: pd.DataFrame) -> pd.DataFrame:
    d = d.sort_values("valor", ascending=False).reset_index(drop=True)
    vis = pd.DataFrame({"Produto": d["produto"].astype(str) + " · " + d["descricao"].fillna(""),
                        "Unid.": d["unidade"], "Qtd (unid. venda)": d["qtd_venda"].map(lambda v: _n(v, 1)),
                        "Qtd (unidades)": d["qtd_unid"].map(_n), "HL": d["hl"].map(lambda v: _n(v, 1)),
                        "Custo médio": d["custo_medio"].map(lambda v: f"R$ {v:,.4f}".replace(",", "X").replace(".", ",")
                                                            .replace("X", ".")),
                        "Valor (R$)": d["valor"].map(_m)})
    vis.loc[len(vis)] = ["TOTAL", "", _n(d["qtd_venda"].sum(), 1), _n(d["qtd_unid"].sum()), _n(d["hl"].sum(), 1), "",
                         _m(d["valor"].sum())]
    return vis


def render_estoque(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 💰 Financeiro › **🏬 Estoque**")
    op = ui.visao_acompanhamento(usuario, operacao_id, "estoque_valor")
    meses = ev.meses(op)
    if not meses:
        st.info("Ainda não há saldo de estoque. Suba o 02.05.02 (saldo inicial e saldo final do mês) em 📥 Relatórios.")
        _ir_relatorios("ev")
        return
    _config_depositos(op)
    mes = ui.seletor_mes("Mês", meses, key="ev_mes", container=st.columns([1, 3])[0])
    c = ev.cmv_real(op, mes)
    comp, origens = ev.comparativo(op, mes, so_cmv=True)
    dias = ev.dias_mes(mes)
    cobertura = _div(c["ef"], (c["cmv"] or 0) / dias) if c["cmv"] else None
    tema.kpis([
        {"titulo": "Estoque inicial", "valor": _m(c["ei"]), "icone": "📦", "status": "info",
         "detalhe": f"{_n(c['ei_hl'])} HL · {origens['inicial']}"},
        {"titulo": "(+) Compras do mês", "valor": _m(c["compras"]), "icone": "🛒", "status": "info",
         "detalhe": f"{_n(c['compras_hl'])} HL (03.02.37 compra)"},
        {"titulo": "(−) Estoque final", "valor": _m(c["ef"]), "icone": "🏬", "status": "info",
         "detalhe": f"{_n(c['ef_hl'])} HL · {origens['final']}"},
        {"titulo": "(=) CMV real", "valor": _m(c["cmv"]) if c["ok"] else "falta saldo", "icone": "🧮",
         "status": "info" if c["ok"] else "atencao",
         "detalhe": f"{_n(c['cmv_hl'])} HL saíram · {_m(_div(c['cmv'], c['cmv_hl']))}/HL" if c["ok"] else
         "suba o saldo inicial e o final"},
        {"titulo": "Variação do estoque", "valor": _m(c["ef"] - c["ei"]), "icone": "↕️",
         "status": "bom" if c["ef"] <= c["ei"] else "atencao", "detalhe": f"{_n(c['ef_hl'] - c['ei_hl'])} HL"},
        {"titulo": "Cobertura do estoque final", "valor": f"{_n(cobertura, 1)} dias" if cobertura else "—",
         "icone": "⏳", "status": "info", "detalhe": "estoque final ÷ CMV médio por dia"},
    ], key="kp_ev")
    st.caption("CMV = estoque inicial + compras − estoque final (depósitos marcados em ⚙️). O 📊 Resumo e o 📑 DRE "
               "usam este CMV para o lucro bruto real.")

    tela = ui._escolha("ev_tela", list(_TELAS), "dep", formatar=_TELAS.get, pills=True)
    fim, _ = ev.saldo(op, mes, "final")
    ini, _ = ev.saldo(op, mes, "inicial")
    fim, ini = ev.enriquecer(fim), ev.enriquecer(ini)
    if tela == "dep":
        if fim.empty:
            st.info("Sem saldo final neste mês.")
            return
        g = fim.groupby("deposito_nome").agg(itens=("produto", "nunique"), qtd=("qtd_venda", "sum"), hl=("hl", "sum"),
                                             valor=("valor", "sum")).reset_index()
        gi = ini.groupby("deposito_nome")["valor"].sum() if not ini.empty else pd.Series(dtype=float)
        g["ini"] = g["deposito_nome"].map(gi).fillna(0.0)
        tot = g["valor"].sum()
        vis = pd.DataFrame({"Depósito": g["deposito_nome"], "Itens": g["itens"].map(_n),
                            "Qtd (unid. venda)": g["qtd"].map(_n), "HL": g["hl"].map(lambda v: _n(v, 1)),
                            "Valor final (R$)": g["valor"].map(_m), "% do estoque": (g["valor"] / tot * 100).map(_p),
                            "Valor inicial (R$)": g["ini"].map(_m), "Variação": (g["valor"] - g["ini"]).map(_m)})
        vis.loc[len(vis)] = ["TOTAL", _n(fim["produto"].nunique()), _n(g["qtd"].sum()), _n(g["hl"].sum(), 1), _m(tot),
                             "100%", _m(g["ini"].sum()), _m(tot - g["ini"].sum())]
        graficos.mostrar(graficos.barras_h(g["deposito_nome"], g["valor"].round(0),
                                           textos=[_m(v) for v in g["valor"]], titulo="Estoque final por depósito"),
                         key="g_ev_dep")
        ui.tabela(vis, baixar=f"estoque_por_deposito_{mes}")
        tema.secao("🔎 O que tem em cada depósito")
        dep = st.selectbox("Depósito", g["deposito_nome"].tolist(), key="ev_dep_sel")
        qual = st.segmented_control("Saldo", ["final", "inicial"], default="final", key="ev_dep_qual",
                                    format_func=lambda t: ev.TIPOS_SALDO[t]) or "final"
        base = fim if qual == "final" else ini
        d = base[base["deposito_nome"] == dep]
        busca = st.text_input("Buscar produto", key="ev_dep_busca").strip().upper()
        if busca:
            d = d[d["descricao"].str.upper().str.contains(busca, regex=False) | d["produto"].str.contains(busca)]
        ui.tabela(_tab_itens(d) if not d.empty else d, baixar=f"deposito_{dep}_{mes}")
    elif tela == "prod":
        f1, f2, f3, f4 = st.columns(4)
        ft = f1.multiselect("Tipo", sorted(comp["tipo_prod"].dropna().unique()), key="ev_ft", placeholder="Todos")
        fe = f2.multiselect("Embalagem", sorted(comp["embalagem"].dropna().unique()), key="ev_fe",
                            placeholder="Todas")
        fm = f3.multiselect("Marca", sorted(comp["marca"].dropna().unique()), key="ev_fm", placeholder="Todas")
        busca = f4.text_input("Buscar", key="ev_busca").strip().upper()
        d = comp
        for col, sel in (("tipo_prod", ft), ("embalagem", fe), ("marca", fm)):
            if sel:
                d = d[d[col].isin(sel)]
        if busca:
            d = d[d["descricao"].fillna("").str.upper().str.contains(busca, regex=False)
                  | d["produto"].astype(str).str.contains(busca)]
        d = d.sort_values("valor_fim", ascending=False).reset_index(drop=True)
        vis = pd.DataFrame({"Produto": d["produto"].astype(str) + " · " + d["descricao"].fillna(""),
                            "Inicial (qtd)": d["qtd_venda_ini"].map(lambda v: _n(v, 1)),
                            "Final (qtd)": d["qtd_venda_fim"].map(lambda v: _n(v, 1)),
                            "Inicial HL": d["hl_ini"].map(lambda v: _n(v, 1)), "Final HL": d["hl_fim"].map(lambda v: _n(v, 1)),
                            "Inicial (R$)": d["valor_ini"].map(_m), "Final (R$)": d["valor_fim"].map(_m),
                            "Variação (R$)": d["var_valor"].map(_m)})
        vis.loc[len(vis)] = ["TOTAL", _n(d["qtd_venda_ini"].sum(), 1), _n(d["qtd_venda_fim"].sum(), 1),
                             _n(d["hl_ini"].sum(), 1), _n(d["hl_fim"].sum(), 1), _m(d["valor_ini"].sum()),
                             _m(d["valor_fim"].sum()), _m(d["var_valor"].sum())]
        ui.tabela(vis, baixar=f"estoque_por_produto_{mes}")
    elif tela == "cat":
        ab = st.segmented_control("Abrir por", ["tipo_prod", "embalagem", "marca"], default="embalagem", key="ev_cat_ab",
                                  format_func={"tipo_prod": "Tipo", "embalagem": "Embalagem", "marca": "Marca"}.get) \
            or "embalagem"
        g = comp.groupby(ab)[["hl_ini", "hl_fim", "valor_ini", "valor_fim", "var_valor"]].sum().reset_index() \
            .sort_values("valor_fim", ascending=False).reset_index(drop=True)
        graficos.mostrar(graficos.barras(g[ab], {"Inicial (R$ mil)": (g["valor_ini"] / 1000).round(1),
                                                 "Final (R$ mil)": (g["valor_fim"] / 1000).round(1)},
                                         titulo="Estoque inicial × final"), key=f"g_ev_cat_{ab}")
        vis = pd.DataFrame({"Grupo": g[ab], "Inicial HL": g["hl_ini"].map(_n), "Final HL": g["hl_fim"].map(_n),
                            "Inicial (R$)": g["valor_ini"].map(_m), "Final (R$)": g["valor_fim"].map(_m),
                            "Variação (R$)": g["var_valor"].map(_m),
                            "% do estoque final": (g["valor_fim"] / g["valor_fim"].sum() * 100).map(_p)})
        vis.loc[len(vis)] = ["TOTAL", _n(g["hl_ini"].sum()), _n(g["hl_fim"].sum()), _m(g["valor_ini"].sum()),
                             _m(g["valor_fim"].sum()), _m(g["var_valor"].sum()), "100%"]
        ui.tabela(vis, baixar=f"estoque_por_{ab}_{mes}")
    else:
        neg = fim[(fim["qtd_unid"] < 0) | (fim["valor"] < 0)] if not fim.empty else fim
        if neg.empty:
            st.success("Nenhum saldo negativo no saldo final. 👏")
            return
        st.warning(f"{len(neg)} item(ns) com saldo negativo no saldo final — somam {_m(neg['valor'].sum())}. "
                   "Saldo negativo distorce o CMV; vale acertar no sistema.")
        neg = neg.assign(Depósito=neg["deposito_nome"])
        vis = _tab_itens(neg)
        vis.insert(0, "Depósito", list(neg.sort_values("valor", ascending=False)["deposito_nome"]) + [""])
        ui.tabela(vis, baixar=f"saldos_negativos_{mes}")


# --- DRE -------------------------------------------------------------------------------------------------
def _linhas_dre(r: dict) -> list[tuple[str, object, str]]:
    """(rótulo, valor, tipo) — tipo: m = R$, p = %, n = HL, h = R$/HL."""
    lb, rec, bruta = r["lucro_bruto"], r["receita"], r["receita_bruta"]
    ops = ", ".join(r["ops_venda"]) or "—"
    linhas = [
        (f"Receita bruta de vendas (operações {ops})", bruta, "m"),
        ("(−) ICMS ✏️", -abs(r["icms"]) if r["icms"] else 0.0, "m"),
        ("(−) PIS/COFINS ✏️", -abs(r["pis_cofins"]) if r["pis_cofins"] else 0.0, "m"),
        ("(=) RECEITA LÍQUIDA", rec, "m"),
        ("(−) CMV — custo da mercadoria vendida", -r["cmv"] if r["cmv"] is not None else None, "m"),
        ("      Estoque inicial", r["ei"] if r["ok"] else None, "m"),
        ("      (+) Compras", r["compras"], "m"),
        ("      (−) Estoque final", -r["ef"] if r["ok"] else None, "m"),
        ("(=) LUCRO BRUTO", lb, "m"),
        ("Margem bruta %", _div(lb, bruta) * 100 if lb is not None and bruta else None, "p"),
        ("(−) Despesas operacionais (OBZ por departamento)", -r["despesas"] if r["despesas"] is not None else None,
         "m"),
    ]
    if r["despesas"] is not None and not r["obz"].empty:
        linhas += [(f"      {p}", -v, "m") for p, v in zip(r["obz"]["pacote"], r["obz"]["realizado"])]
    linhas += [
        ("(±) Conta corrente ✏️", r["conta_corrente"], "m"),
        ("(=) RESULTADO OPERACIONAL", r["resultado"], "m"),
        ("Margem operacional %", _div(r["resultado"], bruta) * 100 if r["resultado"] is not None and bruta else None,
         "p"),
    ]
    return linhas


def _fmt(v, tipo) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return {"m": _m, "p": _p, "n": lambda x: _n(x), "h": _m}[tipo](v)


def _kpis_dre(r: dict, rotulo: str, key: str = "kp_dre") -> None:
    lb, bruta, res = r["lucro_bruto"], r["receita_bruta"], r["resultado"]
    mb = _div(lb, bruta)
    tema.kpis([
        {"titulo": "Faturamento", "valor": _m(bruta), "icone": "💵", "status": "info",
         "detalhe": f"{rotulo} · líquida {_m(r['receita'])}"},
        {"titulo": "CMV", "valor": _m(r["cmv"]), "icone": "📦", "status": "info" if r["ok"] else "atencao",
         "detalhe": "estoque inicial + compras − estoque final" if r["ok"]
         else "falta saldo de estoque"},
        {"titulo": "Lucro bruto", "valor": _m(lb), "icone": "💰",
         "status": "neutro" if mb is None else "bom" if mb >= .2 else "atencao" if mb >= .1 else "critico",
         "detalhe": f"margem {_p(mb * 100 if mb is not None else None)}"},
        {"titulo": "OBZ (despesas)", "valor": _m(r["despesas"]), "icone": "🎯",
         "status": "neutro" if r["despesas"] is None or not r["orcado"] else
         "bom" if r["despesas"] <= r["orcado"] else "critico",
         "detalhe": (f"plan {_m(r['orcado'])} · {len(r['obz'])} departamento(s)" if r["despesas"] is not None
                     else "aguardando OBZ"),
         "dados": pd.DataFrame({"Departamento": r["obz"]["pacote"], "Plan": r["obz"]["orcado"].map(_m),
                                "Realizado": r["obz"]["realizado"].map(_m)}) if not r["obz"].empty else None},
        {"titulo": "Resultado operacional", "valor": _m(res), "icone": "📑",
         "status": "neutro" if res is None else "bom" if res >= 0 else "critico",
         "detalhe": (f"margem {_p(_div(res, bruta) * 100 if res is not None and bruta else None)}"
                     if r["despesas"] is not None else "aguardando OBZ")},
    ], key=key)


def _manuais(usuario: dict, op: int, lista: list[str]) -> None:
    from repositories import operacoes_repo
    from services import obz_service as obz
    from services.erros import RegraNegocioError

    consolidada = operacoes_repo.e_consolidada(op)
    pode = not consolidada and (obz.pode_plan(usuario) or obz.pode_aprovar(usuario))
    with st.expander("✏️ Valores manuais do DRE — ICMS, PIS/COFINS e Conta corrente", expanded=False):
        if consolidada:
            st.caption("Na visão consolidada os valores são a soma das revendas — escolha uma revenda para lançar.")
        elif not pode:
            st.caption("Só o Master, quem lança o Plan ou os aprovadores do financeiro alteram estes valores.")
        st.caption("ICMS e PIS/COFINS são sempre abatidos da receita (pode digitar com ou sem sinal). Conta corrente: "
                   "positivo = crédito (soma no resultado), negativo = débito (diminui).")
        ed = pd.DataFrame([{"mes": m, "Mês": _nome_mes(m), **{k: v for k, v in ev.manual(op, [m]).items()
                                                               if k in ev.CAMPOS_MANUAIS}} for m in lista])
        din = st.column_config.NumberColumn
        novo = st.data_editor(ed, hide_index=True, key=f"dre_man_{op}_{lista[0]}_{lista[-1]}", **ui.LARGURA,
                              disabled=["mes", "Mês"] if pode else list(ed.columns),
                              column_order=["Mês", "icms", "pis_cofins", "conta_corrente"],
                              column_config={"icms": din("ICMS ✏️", format="R$ %.2f"),
                                             "pis_cofins": din("PIS/COFINS ✏️", format="R$ %.2f"),
                                             "conta_corrente": din("Conta corrente ✏️", format="R$ %.2f")})
        if pode and st.button("💾 Salvar valores do DRE", type="primary", key="dre_man_salvar"):
            try:
                for _, r in novo.iterrows():
                    ev.salvar_manual(op, r["mes"], {k: r[k] for k in ev.CAMPOS_MANUAIS},
                                     usuario.get("nome") or usuario.get("login") or "")
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar("Valores do DRE salvos.")
                st.rerun()


def render_dre(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 💰 Financeiro › **📑 DRE**")
    op = ui.visao_acompanhamento(usuario, operacao_id, "dre")
    meses = sorted(set(fs.meses(op, "venda")) | set(ev.meses(op)), reverse=True)
    if not meses:
        st.info("Para o DRE, suba a 03.02.37 vendas, a 03.02.37 compra e o 02.05.02 (saldo inicial e final).")
        _ir_relatorios("dre")
        return
    visao = ui._escolha("dre_visao", ["gerado", "editado", "email"], "gerado", pills=True,
                        formatar={"gerado": "📑 DRE gerado", "editado": "✏️ DRE editado",
                                  "email": "📧 Para e-mail"}.get)
    c1, c2, _ = st.columns([1.2, 1, 2])
    with c1:
        modo = ui._escolha("dre_modo", ["mes", "ano"], "mes", pills=True, formatar={"mes": "🗓️ Mês", "ano": "📆 Ano"}.get)
    if modo == "mes":
        lista = [ui.seletor_mes("Mês", meses, key="dre_mes", container=c2)]
        rotulo = _nome_mes(lista[0])
    else:
        a = c2.selectbox("Ano", sorted({m[:4] for m in meses}, reverse=True), key="dre_ano")
        lista = sorted(m for m in meses if m.startswith(a))
        rotulo = f"ano {a}" if len(lista) > 1 else _nome_mes(lista[0])
    if visao == "editado":
        from modules.corporativo import dre_editado

        dre_editado.render(usuario, op, lista, rotulo)
        return
    if visao == "email":
        from modules.corporativo import dre_editado

        dre_editado.render_email(usuario, op, lista, rotulo)
        return
    with st.spinner("Montando o DRE..."):
        res = [ev.dre_mes(op, m) for m in lista]
        tot = ev.dre_periodo(op, lista) if len(lista) > 1 else res[0]
    _faltas(res)
    _kpis_dre(tot, rotulo)
    _manuais(usuario, op, lista)
    tabela_dre(lista, res, tot, rotulo, "DRE")


def _faltas(res: list[dict]) -> None:
    faltas = []
    if not all(r["ok"] for r in res):
        faltas.append("saldo de estoque (02.05.02 inicial e final) — sem ele não há CMV nem lucro bruto")
    if any(r["despesas"] is None for r in res):
        faltas.append("OBZ (despesas) — o resultado operacional aparece quando o OBZ for lançado")
    if faltas:
        st.warning("Falta para fechar o DRE: " + " · ".join(faltas) + ".")


def montar_tabela(lista: list[str], res: list[dict], tot: dict, rotulo: str) -> pd.DataFrame:
    rotulos = [l_[0] for l_ in _linhas_dre(tot)]
    for r in res:  # departamento que só existe num mês e não no total (não deve acontecer, mas não some)
        for l_ in _linhas_dre(r):
            if l_[0] not in rotulos:
                rotulos.insert(rotulos.index("(±) Conta corrente ✏️"), l_[0])
    tabela = {"Conta": rotulos}
    if len(lista) > 1:
        for m, r in zip(lista, res):
            d = {l_[0]: _fmt(l_[1], l_[2]) for l_ in _linhas_dre(r)}
            tabela[_nome_mes(m)[:3]] = [d.get(rt, "—") for rt in rotulos]
        d = {l_[0]: _fmt(l_[1], l_[2]) for l_ in _linhas_dre(tot)}
        tabela[f"Total {rotulo}"] = [d.get(rt, "—") for rt in rotulos]
    else:
        ls = _linhas_dre(tot)
        tabela[rotulo] = [_fmt(v, t) for _, v, t in ls]
        tabela["% da receita bruta"] = [_p(_div(v, tot["receita_bruta"]) * 100) if t == "m" and v is not None
                                        and tot["receita_bruta"] else "" for _, v, t in ls]
    return pd.DataFrame(tabela)


def tabela_dre(lista: list[str], res: list[dict], tot: dict, rotulo: str, prefixo: str) -> None:
    vis = montar_tabela(lista, res, tot, rotulo)
    ui.tabela(vis, baixar=f"{prefixo}_{lista[0]}_{lista[-1]}", height=(len(vis) + 1) * 35 + 25)
    if len(lista) > 1:
        x = [_nome_mes(m)[:3] for m in lista]
        series = {"Faturamento (R$ mil)": [r["receita_bruta"] / 1000 for r in res],
                  "CMV (R$ mil)": [(r["cmv"] or 0) / 1000 for r in res],
                  "Lucro bruto (R$ mil)": [(r["lucro_bruto"] or 0) / 1000 for r in res],
                  "OBZ (R$ mil)": [(r["despesas"] or 0) / 1000 for r in res],
                  "Resultado operacional (R$ mil)": [(r["resultado"] or 0) / 1000 for r in res]}
        graficos.mostrar(graficos.barras(x, series, titulo="Faturamento, CMV, lucro bruto, OBZ e resultado por mês"),
                         key=f"g_{prefixo}")
    st.caption("Receita bruta = total das notas (coluna Z) só das operações de R$ de venda (⚙️ Cadastros) · "
               "CMV = estoque inicial + compras − estoque final (02.05.02, depósitos "
               "marcados em 🏬 Estoque) — o mesmo do 📊 Resumo & Lucro Bruto · Despesas = OBZ realizado por "
               "departamento (sem bonificação) · ✏️ = valores manuais. No total do ano, o CMV usa o estoque inicial "
               "do 1º mês e o final do último.")
