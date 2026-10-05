"""Módulo Financeiro & OBZ — relatório diário, contas a pagar, vencimentos, fluxo de caixa,
diagnóstico e OBZ por pacote."""
import datetime as dt

import pandas as pd
import streamlit as st

from core import graficos, tema, tempo, ui
from modules.componentes.autosave import editor_autosave
from modules.componentes.bases import card_base
from modules.componentes.registro_generico import Campo, Indicador, tela_registros
from repositories import financeiro_repo
from services import financeiro_service

PACOTES = ["Frete Puxada", "Frete Distribuição", "Manutenção Frota", "Combustível",
           "Pessoal", "Armazém", "Utilidades", "TI", "Outros"]

CAMPOS = [
    Campo("mes_ano", "Mês (AAAA-MM)", obrigatorio=True),
    Campo("pacote", "Pacote", "opcao", PACOTES),
    Campo("orcado", "Orçado (R$)", "numero"),
    Campo("realizado", "Realizado (R$)", "numero"),
]


def _calcular(df):
    df = df.copy()
    df["desvio"] = df["realizado"] - df["orcado"]
    df["desvio_%"] = (df["desvio"] / df["orcado"].where(df["orcado"] > 0) * 100).round(1)
    return df


def _grafico(df):
    por_pacote = df.groupby("pacote", as_index=False)[["realizado", "orcado"]].sum()
    graficos.mostrar(graficos.real_x_meta(por_pacote, "pacote", "realizado", "orcado",
                                          "Realizado x orçado por pacote (R$)", "R$", invertido=True), key="g_fin")


INDICADORES = [
    Indicador("Orçado", lambda d: d["orcado"].sum(), ui.moeda, "📒"),
    Indicador("Realizado", lambda d: d["realizado"].sum(), ui.moeda, "💸"),
    Indicador("Desvio (real − orçado)", lambda d: d["realizado"].sum() - d["orcado"].sum(), ui.moeda, "⚖️",
              lambda v: "bom" if v <= 0 else "atencao" if v < 5000 else "critico"),
]


# --- Relatório diário -----------------------------------------------------
def aba_diario(usuario: dict, operacao_id: int) -> None:
    c1, c2 = st.columns([1, 2])
    with c1:
        card_base("financeiro", operacao_id, usuario, "Relatório diário de pagamentos",
                  "Diário · substitui os dados da filial (fornecedor col. B, vencimento col. K, valor col. N)")
    with c2:
        df = financeiro_repo.contas_df(operacao_id)
        if df.empty:
            st.info("Nenhum título importado para esta filial.")
        else:
            st.caption(f"{len(df)} títulos na base · última carga {df['dt_atualizacao'].max()}")
            ui.tabela(df.drop(columns=["id", "operacao_id"]).head(300))
            ui.downloads(df, "contas_pagar", key="dl_cp_base")


# --- Contas a pagar --------------------------------------------------------
def aba_contas(usuario: dict, operacao_id: int) -> None:
    df = financeiro_repo.contas_df(operacao_id)
    if df.empty:
        st.info("Importe o relatório diário na aba **📂 Relatório Diário**.")
        return
    f1, f2, f3 = st.columns([2, 2, 1])
    forn = f1.multiselect("Fornecedor", sorted(df["fornecedor"].dropna().unique()), key="cp_forn", placeholder="Todos")
    datas = df["data_vencimento"].dropna()
    ini, fim = (datas.min(), datas.max()) if not datas.empty else (tempo.hoje(), tempo.hoje())
    periodo = f2.date_input("Período de vencimento", value=(ini, fim), format="DD/MM/YYYY", key="cp_periodo")
    so_pend = f3.toggle("Só pendentes", value=True, key="cp_pend")
    vis = df
    if forn:
        vis = vis[vis["fornecedor"].isin(forn)]
    if isinstance(periodo, tuple) and len(periodo) == 2:
        vis = vis[(vis["data_vencimento"] >= periodo[0]) & (vis["data_vencimento"] <= periodo[1])]
    if so_pend:
        vis = vis[vis["pendente"] > 0]
    hoje = tempo.hoje()
    venc = vis[(vis["data_vencimento"] < hoje) & (vis["pendente"] > 0)]
    forn_tab = vis.groupby("fornecedor", as_index=False).agg(titulos=("documento", "count"),
                                                              pendente=("pendente", "sum")).sort_values(
        "pendente", ascending=False)
    tema.kpis([
        {"titulo": "Pendente no filtro", "valor": ui.moeda(vis["pendente"].sum()), "icone": "💳", "status": "info",
         "dados": _titulos(vis[vis["pendente"] > 0]), "colunas": FMT_TITULOS},
        {"titulo": "Títulos", "valor": len(vis), "icone": "📄", "status": "info", "dados": _titulos(vis),
         "colunas": FMT_TITULOS},
        {"titulo": "Vencidos", "valor": ui.moeda(venc["pendente"].sum()), "icone": "⏰",
         "detalhe": f"{len(venc)} título(s)", "status": "critico" if len(venc) else "bom",
         "selo": "pagar já" if len(venc) else "nada vencido", "dados": _titulos(venc), "colunas": FMT_TITULOS},
        {"titulo": "Fornecedores", "valor": vis["fornecedor"].nunique(), "icone": "🏢", "status": "info",
         "dados": forn_tab, "colunas": FMT_TITULOS},
    ], key="kp_cp")
    t1, t2 = st.tabs(["📋 Títulos", "🏢 Por fornecedor"])
    with t1:
        cols = ["fornecedor", "documento", "data_vencimento", "pendente", "valor", "realizado", "departamento",
                "conta_gerencial", "pacote"]
        tab = vis[cols].assign(situacao=vis["data_vencimento"].map(
            lambda d: "🔴 Vencido" if d and d < hoje else "🟡 Vence em 7 dias" if d and d <= hoje + dt.timedelta(days=7)
            else "🟢 No prazo"))
        ui.tabela(tab, column_config={
            "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "pendente": st.column_config.NumberColumn("Pendente", format="R$ %.2f"),
            "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "realizado": st.column_config.NumberColumn("Pago", format="R$ %.2f")})
        ui.downloads(tab, "contas_pagar_filtrado", key="dl_cp")
    with t2:
        cons = vis.groupby("fornecedor", as_index=False)["pendente"].sum().sort_values("pendente", ascending=False)
        graficos.mostrar(graficos.barras_h(cons["fornecedor"].head(12), cons["pendente"].head(12),
                                           titulo="Maiores valores pendentes por fornecedor (R$)"), key="g_cp_forn",
                         detalhe=(_titulos(vis), "fornecedor"), colunas=FMT_TITULOS, titulo="Fornecedor")
        ui.tabela(cons, column_config={"pendente": st.column_config.NumberColumn("Pendente", format="R$ %.2f")})


FMT_TITULOS = {"data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
          "pendente": st.column_config.NumberColumn("Pendente", format="R$ %.2f"),
          "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
          "realizado": st.column_config.NumberColumn("Pago", format="R$ %.2f")}
COLS_TITULOS = ["fornecedor", "documento", "data_vencimento", "pendente", "valor", "realizado", "departamento",
                "conta_gerencial"]


def _titulos(df: pd.DataFrame) -> pd.DataFrame:
    return df[[c for c in COLS_TITULOS if c in df.columns]].sort_values("pendente", ascending=False)


# --- Vencimentos -----------------------------------------------------------
def aba_vencimentos(usuario: dict, operacao_id: int) -> None:
    df = financeiro_repo.contas_df(operacao_id)
    if df.empty:
        st.info("Importe o relatório diário na aba **📂 Relatório Diário**.")
        return
    hoje = tempo.hoje()
    pend = df[df["pendente"] > 0]
    prox = pend[(pend["data_vencimento"] >= hoje) & (pend["data_vencimento"] <= hoje + dt.timedelta(days=30))]
    por_dia = prox.groupby("data_vencimento")["pendente"].sum()
    if not por_dia.empty:
        graficos.mostrar(graficos.barras([d.strftime("%d/%m") for d in por_dia.index], {"A pagar": por_dia.values},
                                         titulo="A pagar nos próximos 30 dias (R$)"), key="g_venc",
                         colunas=FMT_TITULOS, titulo="Vencimento",
                         detalhe=lambda rot: _titulos(prox[prox["data_vencimento"].map(lambda d: d.strftime("%d/%m")) == rot]))
    c1, _ = st.columns([1, 3])
    dia = c1.date_input("Dia", value=hoje, format="DD/MM/YYYY", key="venc_dia")
    do_dia = pend[pend["data_vencimento"] == dia]
    tema.kpis([{"titulo": f"A pagar em {dia:%d/%m/%Y}", "valor": ui.moeda(do_dia["pendente"].sum()), "icone": "📅",
                "detalhe": f"{len(do_dia)} título(s)", "status": "critico" if dia < hoje and len(do_dia) else "info",
                "dados": _titulos(do_dia), "colunas": FMT_TITULOS}], key="kp_venc")
    if do_dia.empty:
        st.info("Nenhum título pendente neste dia.")
        return
    g = do_dia.groupby("fornecedor", as_index=False)["pendente"].sum().sort_values("pendente", ascending=False)
    ui.tabela(g, column_config={"pendente": st.column_config.NumberColumn("Pendente", format="R$ %.2f")})
    with st.expander("Títulos do dia"):
        ui.tabela(do_dia[["fornecedor", "documento", "conta_gerencial", "pendente"]],
                  column_config={"pendente": st.column_config.NumberColumn("Pendente", format="R$ %.2f")})


# --- Fluxo de caixa --------------------------------------------------------
def aba_fluxo(usuario: dict, operacao_id: int) -> None:
    st.caption("Projeção de 15 dias. As contas a pagar entram automaticamente (sem Ambev); a compra Ambev, o "
               "recebimento previsto e o saldo do banco você informa na tabela — salva sozinho.")
    c1, _ = st.columns([1, 3])
    saldo_ini = c1.number_input("💵 Saldo inicial (hoje)", value=0.0, step=1000.0, key="fc_saldo")
    proj = financeiro_service.fluxo_projetado(operacao_id, saldo_ini)
    negativos = proj[proj["saldo_projetado"] < 0]
    menor = proj["saldo_projetado"].min()
    fmt_fc = {c: st.column_config.NumberColumn(c.replace("_", " ").capitalize(), format="R$ %.2f")
              for c in ("saldo_banco", "previsao_recebimento", "compra_ambev", "contas_pagar", "saldo_projetado")}
    fmt_fc["data"] = st.column_config.DateColumn("Dia", format="DD/MM/YYYY")
    pend_15 = financeiro_repo.contas_df(operacao_id)
    if not pend_15.empty:
        hoje_ = tempo.hoje()
        dv = pd.to_datetime(pend_15["data_vencimento"], errors="coerce")
        pend_15 = pend_15[(pend_15["pendente"] > 0) & (dv >= pd.Timestamp(hoje_))
                          & (dv <= pd.Timestamp(hoje_ + dt.timedelta(days=15)))]
    tema.kpis([
        {"titulo": "Saldo projetado em 15 dias", "valor": ui.moeda(proj["saldo_projetado"].iloc[-1]), "icone": "📈",
         "status": "bom" if proj["saldo_projetado"].iloc[-1] >= 0 else "critico", "dados": proj, "colunas": fmt_fc},
        {"titulo": "Menor saldo do período", "valor": ui.moeda(menor), "icone": "📉",
         "status": "bom" if menor >= 0 else "critico", "selo": "caixa positivo" if menor >= 0 else "faltará caixa",
         "dados": proj.sort_values("saldo_projetado"), "colunas": fmt_fc},
        {"titulo": "Dias com saldo negativo", "valor": len(negativos), "icone": "⚠️",
         "status": "critico" if len(negativos) else "bom", "dados": negativos, "colunas": fmt_fc},
        {"titulo": "Contas a pagar (15 dias)", "valor": ui.moeda(proj["contas_pagar"].sum()), "icone": "💳",
         "status": "info", "dados": _titulos(pend_15) if not pend_15.empty else pend_15, "colunas": FMT_TITULOS},
    ], key="kp_fluxo")
    rot = [d.strftime("%d/%m") for d in proj["data"]]
    fig = graficos.linhas(rot, {"Saldo projetado": proj["saldo_projetado"]}, titulo="Saldo projetado (R$)")
    fig.add_hline(y=0, line_color=tema.STATUS["critico"][0], line_width=1)
    graficos.mostrar(fig, key="g_fluxo")

    if ui.somente_leitura(operacao_id):
        ui.tabela(proj)
        return
    tab = proj.assign(dia=rot)[["dia", "saldo_banco", "previsao_recebimento", "compra_ambev", "contas_pagar",
                                "saldo_projetado", "data"]]

    def alterar(linha, alt):
        financeiro_repo.salvar_fluxo(
            operacao_id, linha["data"].isoformat(),
            alt.get("saldo_banco", linha["saldo_banco"] if pd.notna(linha["saldo_banco"]) else None),
            float(alt.get("compra_ambev", linha["compra_ambev"]) or 0),
            float(alt.get("previsao_recebimento", linha["previsao_recebimento"]) or 0))

    editor_autosave(tab, f"ed_fluxo_{operacao_id}", ["saldo_banco", "previsao_recebimento", "compra_ambev"], alterar,
                    column_config={
                        "data": None, "dia": "Dia",
                        "saldo_banco": st.column_config.NumberColumn("Saldo banco (se souber) ✏️", format="R$ %.2f"),
                        "previsao_recebimento": st.column_config.NumberColumn("Recebimento previsto ✏️", format="R$ %.2f"),
                        "compra_ambev": st.column_config.NumberColumn("Compra Ambev ✏️", format="R$ %.2f"),
                        "contas_pagar": st.column_config.NumberColumn("Contas a pagar", format="R$ %.2f"),
                        "saldo_projetado": st.column_config.NumberColumn("Saldo projetado", format="R$ %.2f")})
    ui.downloads(proj, "fluxo_caixa", key="dl_fluxo")


# --- Saúde financeira --------------------------------------------------------
def aba_analise(usuario: dict, operacao_id: int) -> None:
    d = financeiro_service.diagnostico(operacao_id)
    if not d:
        st.info("Importe o relatório diário para gerar o diagnóstico.")
        return
    todas = financeiro_repo.contas_df(operacao_id)
    hoje = tempo.hoje()
    pend = todas[todas["pendente"] > 0] if not todas.empty else todas
    dv = pd.to_datetime(pend["data_vencimento"], errors="coerce") if not pend.empty else None
    venc = pend[dv < pd.Timestamp(hoje)] if not pend.empty else pend
    p7 = pend[(dv >= pd.Timestamp(hoje)) & (dv <= pd.Timestamp(hoje + dt.timedelta(days=7)))] \
        if not pend.empty else pend
    top3 = pend.groupby("fornecedor", as_index=False)["pendente"].sum().sort_values("pendente", ascending=False) \
        if not pend.empty else pend
    tema.kpis([
        {"titulo": "Total pendente", "valor": ui.moeda(d["pendente"]), "icone": "💳", "status": "info",
         "dados": _titulos(pend) if not pend.empty else pend, "colunas": FMT_TITULOS},
        {"titulo": "Vencido", "valor": ui.moeda(d["vencidos"]), "icone": "⏰", "detalhe": f"{d['qtd_vencidos']} título(s)",
         "status": "critico" if d["vencidos"] else "bom", "dados": _titulos(venc) if not venc.empty else venc,
         "colunas": FMT_TITULOS},
        {"titulo": "Vence em 7 dias", "valor": ui.moeda(d["prox7"]), "icone": "📅", "detalhe": f"{d['qtd_prox7']} título(s)",
         "status": "atencao" if d["prox7"] else "bom", "dados": _titulos(p7) if not p7.empty else p7,
         "colunas": FMT_TITULOS},
        {"titulo": "Concentração nos 3 maiores", "valor": ui.pct(d["concentracao_top3"]), "icone": "🎯",
         "status": "atencao" if d["concentracao_top3"] > 60 else "bom", "detalhe": "do valor pendente",
         "dados": top3, "colunas": FMT_TITULOS, "ver": "por fornecedor"},
    ], key="kp_fin_an")
    alertas = []
    if d["vencidos"]:
        alertas.append(f"🔴 **{ui.moeda(d['vencidos'])}** em títulos vencidos — priorize ou renegocie.")
    if d["prox7"]:
        alertas.append(f"🟡 **{ui.moeda(d['prox7'])}** vencem nos próximos 7 dias — confira o fluxo de caixa.")
    if d["concentracao_top3"] > 60:
        alertas.append("🟠 Mais de 60% do pendente está em 3 fornecedores — risco de concentração.")
    if not alertas:
        alertas.append("🟢 Nenhum alerta: sem vencidos e sem concentração relevante.")
    st.markdown("\n\n".join(alertas))
    g1, g2 = st.columns(2)
    with g1:
        graficos.mostrar(graficos.barras_h(d["por_conta"].index, d["por_conta"].values,
                                           titulo="Pendente por conta gerencial (R$)"), key="g_an_conta",
                         detalhe=(_titulos(pend), "conta_gerencial") if not pend.empty else None,
                         colunas=FMT_TITULOS, titulo="Conta")
    with g2:
        graficos.mostrar(graficos.barras_h(d["top_fornecedores"].index, d["top_fornecedores"].values,
                                           titulo="Top fornecedores pendentes (R$)"), key="g_an_forn",
                         detalhe=(_titulos(pend), "fornecedor") if not pend.empty else None,
                         colunas=FMT_TITULOS, titulo="Fornecedor")


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("financeiro")
    CAMPOS[0].padrao = ui.mes_atual()
    tela_registros(modulo="financeiro", usuario=usuario, tabela="financeiro_obz", operacao_id=operacao_id,
                   campos=CAMPOS, coluna_data="mes_ano", indicadores=INDICADORES, calculados=_calcular,
                   grafico_extra=_grafico, extras={
                       "diario": lambda: aba_diario(usuario, operacao_id),
                       "contas": lambda: aba_contas(usuario, operacao_id),
                       "vencimentos": lambda: aba_vencimentos(usuario, operacao_id),
                       "fluxo": lambda: aba_fluxo(usuario, operacao_id),
                       "analise": lambda: aba_analise(usuario, operacao_id),
                   })
