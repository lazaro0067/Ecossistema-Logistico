"""Gestão Corporativa › 📈 Vendas › 💵 Faturamento  e  💰 Financeiro › 🛒 Compras de Mercadoria.

Faturamento (03.02.37 vendas): total faturado (coluna Z) separado por operação (coluna C) — venda e bonificação
conforme ⚙️ Cadastros —, HL vendido (coluna T × fator HL da 01.11) e R$/HL (faturamento das operações de venda ÷ HL).
Compras (03.02.37 compra): o mesmo para o que foi investido em mercadoria, com o comparativo compra × venda
(R$/HL comprado × R$/HL vendido = margem por HL).
Cada tela tem as visões 📅 Dia, 🗓️ Mês e 📆 Ano.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from services import faturamento_service as fs

_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_VISOES = {"dia": "📅 Dia", "mes": "🗓️ Mês", "ano": "📆 Ano"}


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _n(v, casas=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, casas)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%".replace(".", ",")


def _div(a, b):
    return a / b if b else None


def _ir_relatorios(chave: str) -> None:
    if st.button("📥 Abrir Relatórios", key=f"ir_rel_{chave}", type="primary"):
        st.session_state["nav_corporativo_grupo"] = st.session_state["nav_corporativo_grupo__ultima"] = "📥 Relatórios"
        st.rerun()


# --- Período ---------------------------------------------------------------------------------------
def _escolher_periodo(meses: list[str], chave: str, operacao_id: int, origem: str):
    c1, c2, c3 = st.columns([1.3, 1, 1.4])
    with c1:
        visao = ui._escolha(f"{chave}_visao", list(_VISOES), "mes", formatar=_VISOES.get, pills=True)
    if visao == "ano":
        anos = sorted({m[:4] for m in meses}, reverse=True)
        ano = c2.selectbox("Ano", anos, key=f"{chave}_ano")
        return visao, f"{ano}-01-01", f"{ano}-12-31", f"ano {ano}", None
    mes = ui.seletor_mes("Mês", meses, key=f"{chave}_mes", container=c2)
    de, ate = fs.periodo_mes(mes)
    if visao == "mes":
        return visao, de, ate, ui.nome_mes(mes), None
    datas = fs.dia_df(operacao_id, origem, de, ate, None)["data"].drop_duplicates().sort_values(ascending=False)
    if datas.empty:
        return visao, de, ate, ui.nome_mes(mes), None
    dia = c3.selectbox("Dia", datas.tolist(), key=f"{chave}_dia",
                       format_func=lambda x: f"{dt.date.fromisoformat(x):%d/%m/%Y} "
                                             f"({_SEMANA[dt.date.fromisoformat(x).weekday()]})")
    return visao, de, ate, f"{dt.date.fromisoformat(dia):%d/%m/%Y}", dia


def _filtro_status(operacao_id: int, origem: str, chave: str) -> list[str]:
    disp = fs.status_disponiveis(operacao_id, origem)
    padrao = [s for s in fs.STATUS_PADRAO[origem] if s in disp] or disp
    with st.expander(f"🧾 Status das notas: {', '.join(padrao)} (padrão) — clique para mudar"):
        sel = st.multiselect("Status", disp, default=padrao, key=f"{chave}_status",
                             format_func=lambda s: fs._STATUS_NOME.get(s, s))
        st.caption("A = nota ativa · C = cancelada · D = devolvida · E = entrada/estorno. Operações de cada visão: "
                   "⚙️ Cadastros.")
    return sel or padrao


# --- Tabelas -------------------------------------------------------------------------------------
def _serie_fat(df: pd.DataFrame, grupos: dict, chave: str) -> pd.DataFrame:
    """Uma linha por dia/mês: venda R$, HL, R$/HL, bonificação R$ e HL, notas."""
    partes = fs.separar(df, grupos)
    v, b = fs.serie(partes["venda"], chave), fs.serie(partes["bonif"], chave)
    out = v.merge(b[[chave, "valor", "hl"]].rename(columns={"valor": "bonif", "hl": "hl_bonif"}), on=chave, how="outer")
    for c in ("valor", "hl", "notas", "qtde", "desconto", "bonif", "hl_bonif"):
        out[c] = pd.to_numeric(out.get(c), errors="coerce").fillna(0.0)
    out["rs_hl"] = out["valor"] / out["hl"].where(out["hl"] > 0)
    out["pct_bonif"] = out["bonif"] / out["valor"].where(out["valor"] > 0) * 100
    return out.sort_values(chave).reset_index(drop=True)


def _vis_fat(s: pd.DataFrame, chave: str) -> pd.DataFrame:
    rot = (s[chave].map(lambda x: f"{dt.date.fromisoformat(x):%d/%m} ({_SEMANA[dt.date.fromisoformat(x).weekday()]})")
           if chave == "data" else s[chave].map(lambda x: f"{_MESES[int(x[5:]) - 1]}/{x[:4]}"))
    vis = pd.DataFrame({"Dia" if chave == "data" else "Mês": rot, "Faturado venda": s["valor"].map(_m),
                        "HL vendido": s["hl"].map(_n), "R$/HL": s["rs_hl"].map(_m),
                        "Bonificação": s["bonif"].map(_m), "HL bonificado": s["hl_bonif"].map(_n),
                        "% bonif.": s["pct_bonif"].map(_p), "Desconto": s["desconto"].map(_m),
                        "Notas": s["notas"].map(_n)})
    t = s[["valor", "hl", "bonif", "hl_bonif", "desconto", "notas"]].sum()
    vis.loc[len(vis)] = ["TOTAL", _m(t["valor"]), _n(t["hl"]), _m(_div(t["valor"], t["hl"])), _m(t["bonif"]),
                         _n(t["hl_bonif"]), _p(_div(t["bonif"], t["valor"]) * 100 if t["valor"] else None),
                         _m(t["desconto"]), _n(t["notas"])]
    return vis


def _vis_operacoes(df: pd.DataFrame, grupos: dict) -> pd.DataFrame:
    po = fs.por_operacao(df)
    if po.empty:
        return po
    marca = {c: "💵 venda" for c in grupos.get("venda", [])}
    marca.update({c: "🎁 bonificação" for c in grupos.get("bonif", [])})
    marca.update({c: "🛒 compra" for c in grupos.get("compra", [])})
    vis = pd.DataFrame({"Operação": po["operacao"], "Tipo movto": po["tipo_movto"],
                        "Conta em": po["operacao_cod"].map(lambda c: marca.get(str(c), "—")),
                        "Valor (coluna Z)": po["valor"].map(_m), "HL": po["hl"].map(_n), "R$/HL": po["rs_hl"].map(_m),
                        "Notas": po["notas"].map(_n)})
    t = po[["valor", "hl", "notas"]].sum()
    vis.loc[len(vis)] = ["TOTAL", "", "", _m(t["valor"]), _n(t["hl"]), _m(_div(t["valor"], t["hl"])), _n(t["notas"])]
    return vis


def _top(df: pd.DataFrame, rotulo: str, n: int = 30) -> pd.DataFrame:
    if df.empty:
        return df
    tot = df["valor"].sum()
    d = df.head(n)
    return pd.DataFrame({rotulo: d.iloc[:, 0].astype(str) + " · " + d.iloc[:, 1].fillna("").astype(str),
                         "Valor": d["valor"].map(_m), "% do total": (d["valor"] / tot * 100).map(_p),
                         "HL": d["hl"].map(lambda v: _n(v, 1)), "R$/HL": d["rs_hl"].map(_m)})


# --- Faturamento (vendas) ----------------------------------------------------------------------------
def render_faturamento(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 📈 Vendas › **💵 Faturamento** (03.02.37 vendas)")
    op = ui.visao_acompanhamento(usuario, operacao_id, "faturamento")
    meses = fs.meses(op, "venda")
    if not meses:
        st.info("Ainda não há notas de venda. Suba a 03.02.37 vendas em 📥 Relatórios.")
        _ir_relatorios("fat")
        return
    grupos = {"venda": fs.operacoes_do_setor("fat_venda"), "bonif": fs.operacoes_do_setor("fat_bonif")}
    nomes = fs.nomes_operacoes()
    st.caption("Venda: " + ", ".join(fs.rotulo_op(c, nomes) for c in grupos["venda"]) + " · Bonificação: "
               + ", ".join(fs.rotulo_op(c, nomes) for c in grupos["bonif"]) + " — ajuste em ⚙️ Cadastros.")
    status = _filtro_status(op, "venda", "fat")
    visao, de, ate, rotulo, dia = _escolher_periodo(meses, "fat", op, "venda")
    df = fs.dia_df(op, "venda", de if visao != "dia" else dia, ate if visao != "dia" else dia, status)
    if df.empty:
        st.info(f"Sem notas em {rotulo}.")
        return
    partes = fs.separar(df, grupos)
    v, b = fs.totais(partes["venda"]), fs.totais(partes["bonif"])
    tema.kpis([
        {"titulo": f"Faturado venda · {rotulo}", "valor": _m(v["valor"]), "icone": "💵", "status": "info",
         "detalhe": f"{_n(v['notas'])} notas · ticket {_m(_div(v['valor'], v['notas']))}"},
        {"titulo": "HL vendido", "valor": f"{_n(v['hl'])} HL", "icone": "🍺", "status": "info",
         "detalhe": f"{_n(v['qtde'])} caixas/unidades"},
        {"titulo": "R$ por HL (venda)", "valor": _m(v["rs_hl"]), "icone": "📐", "status": "info",
         "detalhe": "faturado das operações de venda ÷ HL"},
        {"titulo": "Bonificação", "valor": _m(b["valor"]), "icone": "🎁",
         "status": "atencao" if v["valor"] and b["valor"] / v["valor"] > .05 else "info",
         "detalhe": f"{_n(b['hl'])} HL · {_p(_div(b['valor'], v['valor']) * 100 if v['valor'] else None)} da venda"},
        {"titulo": "Desconto concedido", "valor": _m(v["desconto"]), "icone": "🏷️", "status": "info",
         "detalhe": f"{_p(_div(v['desconto'], v['valor_bruto']) * 100 if v['valor_bruto'] else None)} do valor bruto"},
    ], key=f"kp_fat_{visao}")

    if visao == "dia":
        mes_df = fs.dia_df(op, "venda", de, dia, status)
        s = _serie_fat(mes_df, grupos, "data")
        tema.secao(f"📈 Acumulado do mês até {rotulo}")
        acc = s[["valor", "hl", "bonif", "hl_bonif", "notas"]].sum()
        st.markdown(f"**{_m(acc['valor'])}** faturados · **{_n(acc['hl'])} HL** · R$/HL **"
                    f"{_m(_div(acc['valor'], acc['hl']))}** · bonificação {_m(acc['bonif'])} "
                    f"({_n(acc['hl_bonif'])} HL) em {len(s)} dia(s).")
        tema.secao("🧾 Por operação no dia")
        ui.tabela(_vis_operacoes(df, grupos), baixar=f"faturamento_operacoes_{dia}")
        return

    chave = "data" if visao == "mes" else "mes"
    s = _serie_fat(df, grupos, chave)
    x = (s[chave].map(lambda d_: dt.date.fromisoformat(d_).strftime("%d/%m")) if chave == "data"
         else s[chave].map(lambda m: _MESES[int(m[5:]) - 1]))
    g1, g2 = st.columns(2)
    with g1:
        graficos.mostrar(graficos.barras(x, {"Venda (R$ mil)": (s["valor"] / 1000).round(1),
                                             "Bonificação (R$ mil)": (s["bonif"] / 1000).round(1)},
                                         titulo="Faturamento", empilhado=True), key=f"g_fat_{visao}_rs")
    with g2:
        graficos.mostrar(graficos.linhas(x, {"R$/HL": s["rs_hl"].round(2)}, titulo="R$ por HL vendido"),
                         key=f"g_fat_{visao}_rshl")
    tema.secao("📅 Dia a dia" if chave == "data" else "🗓️ Mês a mês")
    ui.tabela(_vis_fat(s, chave), baixar=f"faturamento_{rotulo}")
    tema.secao("🧾 Por operação", "Todas as operações das notas no período — a coluna “Conta em” mostra a visão.")
    ui.tabela(_vis_operacoes(df, grupos), baixar="faturamento_por_operacao")
    m_de, m_ate = de[:7], ate[:7]
    c1, c2 = st.columns(2)
    with c1:
        tema.secao("🏆 Produtos (venda)")
        ui.tabela(_top(fs.produto_df(op, "venda", m_de, m_ate, status, grupos["venda"]), "Produto"),
                  baixar="faturamento_produtos")
    with c2:
        tema.secao("👥 Clientes (venda)")
        ui.tabela(_top(fs.cliente_df(op, "venda", m_de, m_ate, status, grupos["venda"]), "Cliente"),
                  baixar="faturamento_clientes")


# --- Compras (investimento em mercadoria) -----------------------------------------------------------------
def render_compras(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 💰 Financeiro › **🛒 Compras de Mercadoria** (03.02.37 compra)")
    op = ui.visao_acompanhamento(usuario, operacao_id, "compras")
    meses = fs.meses(op, "compra")
    if not meses:
        st.info("Ainda não há notas de compra. Suba a 03.02.37 compra em 📥 Relatórios.")
        _ir_relatorios("cmp")
        return
    g_compra = fs.operacoes_do_setor("compra")
    g_venda = fs.operacoes_do_setor("fat_venda")
    nomes = fs.nomes_operacoes()
    st.caption("Compra: " + ", ".join(fs.rotulo_op(c, nomes) for c in g_compra) + " · comparado com a venda ("
               + ", ".join(fs.rotulo_op(c, nomes) for c in g_venda) + ") — ajuste em ⚙️ Cadastros.")
    status = _filtro_status(op, "compra", "cmp")
    visao, de, ate, rotulo, dia = _escolher_periodo(meses, "cmp", op, "compra")
    a, b_ = (dia, dia) if visao == "dia" else (de, ate)
    dc = fs.dia_df(op, "compra", a, b_, status)
    dv = fs.dia_df(op, "venda", a, b_, fs.STATUS_PADRAO["venda"])
    c = fs.totais(dc[dc["operacao_cod"].astype(str).isin(g_compra)])
    v = fs.totais(dv[dv["operacao_cod"].astype(str).isin(g_venda)]) if not dv.empty else fs.totais(dv)
    margem_hl = (v["rs_hl"] - c["rs_hl"]) if v["rs_hl"] and c["rs_hl"] else None
    margem_pct = margem_hl / v["rs_hl"] * 100 if margem_hl is not None else None
    tema.kpis([
        {"titulo": f"Investido em mercadoria · {rotulo}", "valor": _m(c["valor"]), "icone": "🛒", "status": "info",
         "detalhe": f"{_n(c['notas'])} notas de compra"},
        {"titulo": "HL comprado", "valor": f"{_n(c['hl'])} HL", "icone": "🍺", "status": "info",
         "detalhe": f"cobre {_p(_div(c['hl'], v['hl']) * 100 if v['hl'] else None)} do HL vendido"},
        {"titulo": "R$ por HL (compra)", "valor": _m(c["rs_hl"]), "icone": "📐", "status": "info",
         "detalhe": f"venda: {_m(v['rs_hl'])} por HL"},
        {"titulo": "Margem bruta por HL", "valor": _m(margem_hl), "icone": "📈",
         "status": "neutro" if margem_pct is None else "bom" if margem_pct >= 20 else "atencao" if margem_pct >= 10
         else "critico", "detalhe": f"{_p(margem_pct)} sobre o preço de venda"},
        {"titulo": "Compra ÷ venda (R$)", "valor": _p(_div(c["valor"], v["valor"]) * 100 if v["valor"] else None),
         "icone": "⚖️", "status": "info", "detalhe": f"venda no período: {_m(v['valor'])}"},
    ], key=f"kp_cmp_{visao}")
    if not v["valor"]:
        st.caption("ℹ️ Sem notas de venda no mesmo período para comparar — suba a 03.02.37 vendas.")

    if visao != "dia":
        chave = "data" if visao == "mes" else "mes"
        sc = fs.serie(dc[dc["operacao_cod"].astype(str).isin(g_compra)], chave)
        sv = fs.serie(dv[dv["operacao_cod"].astype(str).isin(g_venda)], chave) if not dv.empty else fs.serie(dv, chave)
        s = sc.merge(sv[[chave, "valor", "hl", "rs_hl"]].rename(columns={"valor": "v_valor", "hl": "v_hl",
                                                                          "rs_hl": "v_rs_hl"}), on=chave, how="outer")
        s = s.sort_values(chave).reset_index(drop=True)
        x = (s[chave].map(lambda d_: dt.date.fromisoformat(d_).strftime("%d/%m")) if chave == "data"
             else s[chave].map(lambda m: _MESES[int(m[5:]) - 1]))
        g1, g2 = st.columns(2)
        with g1:
            graficos.mostrar(graficos.barras(x, {"Compra (R$ mil)": (s["valor"].fillna(0) / 1000).round(1),
                                                 "Venda (R$ mil)": (s["v_valor"].fillna(0) / 1000).round(1)},
                                             titulo="Compra × venda"), key=f"g_cmp_{visao}_rs")
        with g2:
            graficos.mostrar(graficos.linhas(x, {"R$/HL compra": s["rs_hl"].round(2),
                                                 "R$/HL venda": s["v_rs_hl"].round(2)},
                                             titulo="R$ por HL — compra × venda"), key=f"g_cmp_{visao}_hl")
        rot = (s[chave].map(lambda x_: f"{dt.date.fromisoformat(x_):%d/%m}") if chave == "data"
               else s[chave].map(lambda x_: f"{_MESES[int(x_[5:]) - 1]}/{x_[:4]}"))
        vis = pd.DataFrame({"Dia" if chave == "data" else "Mês": rot, "Compra (R$)": s["valor"].map(_m),
                            "HL comprado": s["hl"].map(_n), "R$/HL compra": s["rs_hl"].map(_m),
                            "Venda (R$)": s["v_valor"].map(_m), "HL vendido": s["v_hl"].map(_n),
                            "R$/HL venda": s["v_rs_hl"].map(_m),
                            "Margem/HL": (s["v_rs_hl"] - s["rs_hl"]).map(_m),
                            "Notas compra": s["notas"].map(_n)})
        vis.loc[len(vis)] = ["TOTAL", _m(c["valor"]), _n(c["hl"]), _m(c["rs_hl"]), _m(v["valor"]), _n(v["hl"]),
                             _m(v["rs_hl"]), _m(margem_hl), _n(c["notas"])]
        tema.secao("📅 Dia a dia" if chave == "data" else "🗓️ Mês a mês")
        ui.tabela(vis, baixar=f"compras_{rotulo}")
    tema.secao("🧾 Por operação de entrada", "Todas as operações das notas de entrada — “Conta em” mostra o que "
               "entra como compra de mercadoria.")
    ui.tabela(_vis_operacoes(dc, {"compra": g_compra}), baixar="compras_por_operacao")
    if visao != "dia":
        tema.secao("🏷️ Produtos: custo × preço de venda", "R$/HL de compra e de venda de cada produto no período.")
        pc = fs.produto_df(op, "compra", de[:7], ate[:7], status, g_compra)
        pv = fs.produto_df(op, "venda", de[:7], ate[:7], fs.STATUS_PADRAO["venda"], g_venda)
        if pc.empty:
            st.info("Sem produtos comprados no período.")
            return
        mg = pc.merge(pv[["produto", "valor", "hl", "rs_hl"]].rename(columns={"valor": "v_valor", "hl": "v_hl",
                                                                              "rs_hl": "v_rs_hl"}),
                      on="produto", how="left")
        mg["margem"] = mg["v_rs_hl"] - mg["rs_hl"]
        mg["margem_pct"] = mg["margem"] / mg["v_rs_hl"] * 100
        ui.tabela(pd.DataFrame({
            "Produto": mg["produto"].astype(str) + " · " + mg["descricao"].fillna(""),
            "Compra (R$)": mg["valor"].map(_m), "HL comprado": mg["hl"].map(lambda x_: _n(x_, 1)),
            "R$/HL compra": mg["rs_hl"].map(_m), "Venda (R$)": mg["v_valor"].map(_m),
            "HL vendido": mg["v_hl"].map(lambda x_: _n(x_, 1)), "R$/HL venda": mg["v_rs_hl"].map(_m),
            "Margem/HL": mg["margem"].map(_m), "Margem %": mg["margem_pct"].map(_p)}).head(60),
            baixar="compras_custo_x_venda_produtos")
