"""💰 Financeiro › 📑 DRE › 🧾 Financeiro contabilidade — sobe o financeiro fechado (fecha o DRE) e lança outras contas."""
import pandas as pd
import streamlit as st

from core import arquivos, tema, ui
from repositories import operacoes_repo
from services import contabilidade_service as cs
from services import estoque_valor_service as ev
from services.erros import RegraNegocioError


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _meses(op: int, meses_dre: list[str]) -> list[str]:
    ms = {ev.mes_atual()}
    m = ev.mes_atual()
    for _ in range(12):
        m = ev.mes_anterior(m)
        ms.add(m)
    return sorted(ms | set(meses_dre or []) | set(cs.meses(op)), reverse=True)


def render(usuario: dict, op: int, meses_dre: list[str] | None = None) -> None:
    ms = _meses(op, meses_dre or [])
    padrao = (cs.meses(op) or meses_dre or ms)[0]
    if st.session_state.get("ctb_mes") not in ms:
        st.session_state["ctb_mes"] = padrao if padrao in ms else ms[0]
    c1, c2 = st.columns([1, 2.2])
    mes = c1.selectbox("Mês do fechamento", ms, key="ctb_mes", format_func=ui.nome_mes)
    with c2:
        if cs.fechado(op, mes):
            ca = cs.carga(op, mes) or {}
            st.success(f"🔒 {ui.nome_mes(mes)} fechado pela contabilidade — {ca.get('contas', 0)} contas "
                       f"({ca.get('arquivo') or '—'}, por {ca.get('por') or '—'}).")
        else:
            st.info(f"⏳ {ui.nome_mes(mes)} ainda sem o Financeiro contabilidade — o DRE fica como prévia (OBZ).")
    aba = ui._escolha("ctb_aba", ["relatorio", "outras"], "relatorio", pills=True,
                      formatar={"relatorio": "📥 Relatório", "outras": "✍️ Outras contas"}.get)
    if aba == "outras":
        _outras(usuario, op, mes)
    else:
        _relatorio(usuario, op, mes)


def card_upload(usuario: dict, op: int, mes: str, chave: str = "ctb") -> None:
    """Upload do relatório do mês (também usado em 📥 Relatórios)."""
    v = st.session_state.get(f"{chave}_up_v", 0)
    arq = st.file_uploader("Financeiro contabilidade", type=arquivos.FORMATOS, key=f"{chave}_up_{v}",
                           label_visibility="collapsed")
    st.caption("A = código · B = classificação (1.1 departamento, 1.1.01 subpacote, 3.03… conta) · C = nome · "
               "D = valor (negativo = despesa). Subir de novo o mês substitui o mês inteiro.")
    if arq is not None and st.button(f"Gravar {ui.nome_mes(mes)}", type="primary", key=f"{chave}_gravar"):
        try:
            r = None
            if str(arq.name).lower().endswith((".xlsx", ".xlsm", ".xls")):  # planilha com abas OBZ01…OBZ12
                r = cs.importar_planilha_mes(arq.getvalue(), arq.name, op, mes, usuario.get("nome", ""))
            if r is None:
                a2 = arquivos.preparar(arq)
                r = cs.importar(a2.getvalue(), a2.name, op, mes, usuario.get("nome", ""))
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar(f"🧾 Financeiro contabilidade de {ui.nome_mes(mes)}: {r['contas']} contas · "
                      f"{r['departamentos']} departamentos · despesa {ui.moeda(r['despesa'])}. DRE fechado 🔒.")
            for a in r["avisos"]:
                ui.avisar("⚠️ Conferir total — " + a, "warning")
            st.session_state[f"{chave}_up_v"] = v + 1
            st.rerun()
    _acoes(usuario, op, mes, chave)


def _acoes(usuario: dict, op: int, mes: str, chave: str) -> None:
    """🗑️ Apagar o mês que subiu errado · 📚 retroativo: zerar e subir a planilha consolidada (uma aba por mês)."""
    if operacoes_repo.e_consolidada(op) or not ev.pode_editar_dre(usuario):
        return
    revenda = (operacoes_repo.buscar(op) or {}).get("nome", "revenda")
    c1, c2 = st.columns(2)
    with c1.popover(f"🗑️ Apagar {ui.nome_mes(mes)}", disabled=not cs.fechado(op, mes), **ui.LARGURA):
        st.markdown(f"Apagar o Financeiro contabilidade de **{ui.nome_mes(mes)}** — {revenda}?")
        st.caption("O DRE do mês volta a ser prévia pelo OBZ. As ✍️ Outras contas ficam.")
        if st.button("Apagar o mês", key=f"{chave}_del_{mes}", type="primary"):
            ui.acao(cs.excluir_mes, op, mes, sucesso=f"{ui.nome_mes(mes)} apagado — suba de novo o arquivo certo.")
    with c2.popover("📚 Zerar e subir consolidado (retroativo)", **ui.LARGURA):
        st.markdown(f"**Retroativo de uma vez — {revenda}**")
        st.caption("Planilha com uma aba por mês (OBZ01 = jan … OBZ12 = dez). Zera o ano desta revenda e grava "
                   "cada mês que tiver contas; abas vazias (meses que não fecharam) ficam de fora. Depois volte a "
                   "subir mês a mês normalmente.")
        anos = sorted({mes[:4], str(int(mes[:4]) - 1)}, reverse=True)
        ano = st.selectbox("Ano", anos, key=f"{chave}_cons_ano")
        vc = st.session_state.get(f"{chave}_cons_v", 0)
        arq = st.file_uploader("Planilha consolidada", type=["xlsx", "xlsm", "xls"], key=f"{chave}_cons_up_{vc}")
        zerar = st.checkbox(f"Zerar {ano} antes (recomendado)", value=True, key=f"{chave}_cons_zerar")
        conf = st.text_input("Digite ZERAR para confirmar", key=f"{chave}_cons_conf") if zerar else "ZERAR"
        if st.button("Subir consolidado", type="primary", key=f"{chave}_cons_go",
                     disabled=arq is None or str(conf).strip().upper() != "ZERAR"):
            try:
                r = cs.importar_consolidado(arq.getvalue(), arq.name, op, ano, usuario.get("nome", ""), zerar)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ms = r["meses"]
                ui.avisar(f"📚 {revenda}: {len(ms)} mês(es) gravado(s) — "
                          + ", ".join(f"{ui.nome_mes(m)} {ui.moeda(x['despesa'])}" for m, x in ms.items())
                          + (f". Sem contas (ficaram de fora): {', '.join(ui.nome_mes(m) for m in r['vazios'])}"
                             if r["vazios"] else "") + ".")
                for m, x in ms.items():
                    for a in x["avisos"]:
                        ui.avisar(f"⚠️ {ui.nome_mes(m)} — conferir total: {a}", "warning")
                st.session_state[f"{chave}_cons_v"] = vc + 1
                st.rerun()
        st.divider()
        if st.button(f"🧹 Só zerar {ano} (sem subir)", key=f"{chave}_zerar_ano",
                     disabled=str(conf).strip().upper() != "ZERAR"):
            ui.acao(cs.zerar, op, ano, sucesso=f"Financeiro contabilidade de {ano} zerado — {revenda}.")


def _relatorio(usuario: dict, op: int, mes: str) -> None:
    if not operacoes_repo.e_consolidada(op):
        with st.expander("📥 Subir o Financeiro contabilidade", expanded=not cs.fechado(op, mes)):
            card_upload(usuario, op, mes)
    c = cs.contas(op, mes)
    if c.empty:
        st.caption("Nada lançado neste mês ainda.")
        return
    dep = c.groupby("departamento", sort=False).agg(despesa=("despesa", "sum"), contas=("nome", "size")).reset_index()

    def tab_contas(x: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"Departamento": x["departamento"].values, "Subpacote": x["subpacote"].fillna("").values,
                             "Classificação": x["classificacao"].fillna("").values, "Conta": x["nome"].values,
                             "Despesa": x["despesa"].map(_m).values, "Origem": x["origem"].values})
    cards = [{"titulo": "Despesa total", "valor": _m(c["despesa"].sum()), "icone": "🧾", "status": "info",
              "detalhe": f"{len(dep)} departamento(s) · {len(c)} conta(s)", "dados": tab_contas(c)}]
    for r in dep.itertuples():
        cards.append({"titulo": str(r.departamento), "valor": _m(r.despesa), "icone": "🏷️", "status": "neutro",
                      "detalhe": f"{r.contas} conta(s)",
                      "dados": tab_contas(c[c["departamento"] == r.departamento])})
    tema.kpis(cards, key=f"kp_ctb_{mes}")
    tema.secao("🏷️ Por departamento e subpacote", "É assim que entra no 📑 DRE (despesas por departamento).")
    sp = (c.assign(subpacote=c["subpacote"].replace("", "—"))
          .groupby(["departamento", "subpacote"], sort=False)["despesa"].sum().reset_index())
    ui.tabela(pd.DataFrame({"Departamento": sp["departamento"], "Subpacote": sp["subpacote"],
                            "Despesa": sp["despesa"].map(_m)}), baixar=f"contabilidade_subpacotes_{mes}")
    tema.secao("🔎 Contas")
    deps = ["__todos__"] + dep["departamento"].tolist()
    d = st.selectbox("Departamento", deps, key="ctb_dep",
                     format_func=lambda x: "Todos" if x == "__todos__" else x)
    x = c if d == "__todos__" else c[c["departamento"] == d]
    ui.tabela(tab_contas(x.sort_values("despesa", ascending=False)), baixar=f"contabilidade_contas_{mes}")
    if not operacoes_repo.e_consolidada(op) and ev.pode_editar_dre(usuario):
        if st.button("🗑️ Excluir o relatório deste mês", key="ctb_excluir"):
            ui.acao(cs.excluir_mes, op, mes, sucesso="Relatório excluído — o DRE volta a ser prévia pelo OBZ.")


def _outras(usuario: dict, op: int, mes: str) -> None:
    tema.secao("✍️ Outras contas",
               "Contas que não vieram no relatório da contabilidade. Entram no 📑 DRE somadas no departamento. "
               "Valor positivo = despesa · negativo = crédito/estorno.")
    o = cs.outras(op, mes)
    deps = cs.departamentos(op)
    base = pd.DataFrame({"Departamento": o["departamento"].astype(str), "Conta": o["conta"].astype(str),
                         "Despesa (R$)": pd.to_numeric(o["despesa"], errors="coerce"),
                         "Observação": o["obs"].fillna("").astype(str)}) if not o.empty else pd.DataFrame(
        {"Departamento": pd.Series(dtype=str), "Conta": pd.Series(dtype=str),
         "Despesa (R$)": pd.Series(dtype=float), "Observação": pd.Series(dtype=str)})
    consol = operacoes_repo.e_consolidada(op)
    opcoes = sorted(set(deps) | set(base["Departamento"].tolist()))
    cfg = {"Despesa (R$)": st.column_config.NumberColumn("Despesa (R$)", format="R$ %.2f"),
           "Departamento": (st.column_config.SelectboxColumn("Departamento", options=opcoes, required=True)
                            if opcoes else st.column_config.TextColumn("Departamento", required=True))}
    ed = st.data_editor(base, num_rows="dynamic", hide_index=True, key=f"ctb_outras_{mes}", column_config=cfg,
                        disabled=consol, **ui.LARGURA)
    if not opcoes:
        st.caption("Suba o relatório da contabilidade para escolher o departamento na lista.")
    tot = pd.to_numeric(ed["Despesa (R$)"], errors="coerce").fillna(0).sum() if len(ed) else 0
    st.caption(f"Total de outras contas: {ui.moeda(tot)}")
    if consol:
        st.info("Escolha uma revenda para lançar outras contas.")
        return
    if st.button("💾 Salvar outras contas", type="primary", key="ctb_outras_salvar"):
        linhas = [{"departamento": r["Departamento"], "conta": r["Conta"], "despesa": r["Despesa (R$)"],
                   "obs": r["Observação"]} for _, r in ed.iterrows()]
        ui.acao(cs.salvar_outras, op, mes, linhas, usuario.get("nome", ""), sucesso="Outras contas salvas.")
