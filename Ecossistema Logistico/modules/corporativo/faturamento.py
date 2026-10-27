"""Gestão Corporativa › 📈 Vendas › 💵 Faturamento  e  💰 Financeiro › 🛒 Compras de Mercadoria.

Faturamento (03.02.37 vendas): total faturado (coluna Z) separado por operação (coluna C). R$ e HL têm filtros
próprios em ⚙️ Cadastros: R$ = operações de venda; HL = venda + bonificação (a bonificação ajuda a vender).
R$/HL = R$ de venda ÷ HL (venda + bonificação). Compras: a mesma regra (HL = compra + bonificação recebida).
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
    """Uma linha por dia/mês: venda R$, HL (venda + bonificação), R$/HL, bonificação R$ e HL, notas."""
    out = fs.serie_combinada(df, grupos["venda"], grupos["hl"], chave)
    b = fs.serie(fs.separar(df, {"b": grupos["bonif"]})["b"], chave)
    out = out.merge(b[[chave, "valor", "hl"]].rename(columns={"valor": "bonif", "hl": "hl_bonif"}), on=chave,
                    how="outer")
    for c in ("valor", "hl", "notas", "qtde", "desconto", "bonif", "hl_bonif"):
        out[c] = pd.to_numeric(out.get(c), errors="coerce").fillna(0.0)
    out["rs_hl"] = out["valor"] / out["hl"].where(out["hl"] > 0)
    out["pct_bonif"] = out["bonif"] / out["valor"].where(out["valor"] > 0) * 100
    return out.sort_values(chave).reset_index(drop=True)


def _vis_fat(s: pd.DataFrame, chave: str) -> pd.DataFrame:
    rot = (s[chave].map(lambda x: f"{dt.date.fromisoformat(x):%d/%m} ({_SEMANA[dt.date.fromisoformat(x).weekday()]})")
           if chave == "data" else s[chave].map(lambda x: f"{_MESES[int(x[5:]) - 1]}/{x[:4]}"))
    vis = pd.DataFrame({"Dia" if chave == "data" else "Mês": rot, "Faturado venda": s["valor"].map(_m),
                        "HL vendido (c/ bonif.)": s["hl"].map(_n), "R$/HL": s["rs_hl"].map(_m),
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
    def marca(c) -> str:
        c = str(c)
        r = ("R$ venda" if c in grupos.get("venda", []) else "R$ bonif." if c in grupos.get("bonif", [])
             else "R$ compra" if c in grupos.get("compra", []) else "")
        h = "HL" if c in grupos.get("hl", []) else ""
        return " + ".join(x for x in (r, h) if x) or "—"

    vis = pd.DataFrame({"Operação": po["operacao"], "Tipo movto": po["tipo_movto"],
                        "Conta em": po["operacao_cod"].map(marca),
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
    cod_, nome_ = ("produto", "descricao") if "produto" in d else ("cliente", "nome")
    return pd.DataFrame({rotulo: d[cod_].astype(str) + " · " + d[nome_].fillna("").astype(str),
                         "Valor": d["valor"].map(_m), "% do total": (d["valor"] / tot * 100).map(_p),
                         "HL (c/ bonif.)": d["hl"].map(lambda v: _n(v, 1)), "R$/HL": d["rs_hl"].map(_m)})


# --- Faturamento (vendas) ----------------------------------------------------------------------------
def render_faturamento(usuario: dict, operacao_id: int, titulo: str = "📈 Vendas › **💵 Faturamento**") -> None:
    st.markdown(f"##### {titulo}")
    op = ui.visao_acompanhamento(usuario, operacao_id, "faturamento")
    meses = fs.meses(op, "venda")
    if not meses:
        st.info("Ainda não há notas de venda. Suba a 03.02.37 vendas em 📥 Relatórios.")
        _ir_relatorios("fat")
        return
    grupos = {"venda": fs.operacoes_do_setor("fat_venda"), "bonif": fs.operacoes_do_setor("fat_bonif"),
              "hl": fs.operacoes_do_setor("hl_venda")}
    nomes = fs.nomes_operacoes()
    lista = lambda cs: ", ".join(fs.rotulo_op(c, nomes) for c in cs)  # noqa: E731
    st.caption(f"R$: {lista(grupos['venda'])} · HL: {lista(grupos['hl'])} (a bonificação soma no HL) · "
               f"Bonificação à parte: {lista(grupos['bonif'])} — ajuste em ⚙️ Cadastros.")
    status = _filtro_status(op, "venda", "fat")
    visao, de, ate, rotulo, dia = _escolher_periodo(meses, "fat", op, "venda")
    df = fs.dia_df(op, "venda", de if visao != "dia" else dia, ate if visao != "dia" else dia, status)
    if df.empty:
        st.info(f"Sem notas em {rotulo}.")
        return
    v = fs.combinar(df, grupos["venda"], grupos["hl"])
    b = fs.totais(fs.separar(df, {"b": grupos["bonif"]})["b"])
    tema.kpis([
        {"titulo": f"Faturado venda · {rotulo}", "valor": _m(v["valor"]), "icone": "💵", "status": "info",
         "detalhe": f"{_n(v['notas'])} notas · ticket {_m(_div(v['valor'], v['notas']))}"},
        {"titulo": "HL vendido (venda + bonif.)", "valor": f"{_n(v['hl'])} HL", "icone": "🍺", "status": "info",
         "detalhe": f"{_n(v['hl_rs'])} HL de venda + {_n(v['hl'] - v['hl_rs'])} HL de bonificação"},
        {"titulo": "R$ por HL", "valor": _m(v["rs_hl"]), "icone": "📐", "status": "info",
         "detalhe": "faturado de venda ÷ HL (venda + bonificação)"},
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
    tema.secao("🏆 Produtos (venda)")
    ui.tabela(_top(fs.produto_combinado(op, "venda", m_de, m_ate, status, grupos["venda"], grupos["hl"]),
                   "Produto"), baixar="faturamento_produtos")
    tema.secao("👥 Clientes (venda)")
    ui.tabela(_top(fs.cliente_combinado(op, "venda", m_de, m_ate, status, grupos["venda"], grupos["hl"]),
                   "Cliente"), baixar="faturamento_clientes")


# --- Compras (investimento em mercadoria) -----------------------------------------------------------------
def render_compras(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 💰 Financeiro › **🛒 Compras**")
    op = ui.visao_acompanhamento(usuario, operacao_id, "compras")
    meses = fs.meses(op, "compra")
    if not meses:
        st.info("Ainda não há notas de compra. Suba a 03.02.37 compra em 📥 Relatórios.")
        _ir_relatorios("cmp")
        return
    g_compra, gh_compra = fs.operacoes_do_setor("compra"), fs.operacoes_do_setor("hl_compra")
    g_venda, gh_venda = fs.operacoes_do_setor("fat_venda"), fs.operacoes_do_setor("hl_venda")
    nomes = fs.nomes_operacoes()
    lista = lambda cs: ", ".join(fs.rotulo_op(c, nomes) for c in cs)  # noqa: E731
    st.caption(f"Compra — R$: {lista(g_compra)} · HL: {lista(gh_compra)} │ Venda — R$: {lista(g_venda)} · HL: "
               f"{lista(gh_venda)} (a bonificação soma no HL) — ajuste em ⚙️ Cadastros.")
    status = _filtro_status(op, "compra", "cmp")
    visao, de, ate, rotulo, dia = _escolher_periodo(meses, "cmp", op, "compra")
    a, b_ = (dia, dia) if visao == "dia" else (de, ate)
    dc = fs.dia_df(op, "compra", a, b_, status)
    dv = fs.dia_df(op, "venda", a, b_, fs.STATUS_PADRAO["venda"])
    c = fs.combinar(dc, g_compra, gh_compra)
    v = fs.combinar(dv, g_venda, gh_venda)
    margem_hl = (v["rs_hl"] - c["rs_hl"]) if v["rs_hl"] and c["rs_hl"] else None
    margem_pct = margem_hl / v["rs_hl"] * 100 if margem_hl is not None else None
    tema.kpis([
        {"titulo": f"Investido em mercadoria · {rotulo}", "valor": _m(c["valor"]), "icone": "🛒", "status": "info",
         "detalhe": f"{_n(c['notas'])} notas de compra"},
        {"titulo": "HL comprado (compra + bonif.)", "valor": f"{_n(c['hl'])} HL", "icone": "🍺", "status": "info",
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
        sc = fs.serie_combinada(dc, g_compra, gh_compra, chave)
        sv = fs.serie_combinada(dv, g_venda, gh_venda, chave)
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
    ui.tabela(_vis_operacoes(dc, {"compra": g_compra, "hl": gh_compra}), baixar="compras_por_operacao")
    if visao != "dia":
        mg = fs.margem(op, de[:7], ate[:7], fs.STATUS_PADRAO["venda"], status)
        if mg.empty:
            return
        tema.secao("🏆 Top 10 e 🔻 Bottom 10 — margem bruta por produto",
                   "Venda − custo (HL vendido × R$/HL de compra). Abertura completa em 💰 Financeiro › 📊 Resumo & Lucro Bruto.")
        top_bottom(mg, "cmp")


# --- Margem bruta -------------------------------------------------------------------------------------
_ABERTURAS = {"tipo": "🍺 Tipo", "embalagem": "📦 Embalagem", "marca": "🏷️ Marca", "produto": "🔎 Produto"}


def _vis_margem(d: pd.DataFrame, rotulo: str, col: str) -> pd.DataFrame:
    nome = (d["produto"].astype(str) + " · " + d["descricao"].fillna("")) if col == "produto" else d[col]
    return pd.DataFrame({
        "": d["margem_pct"].map(lambda p: "⚪" if p is None or pd.isna(p) else "🟢" if p >= 20 else "🟡" if p >= 10
                                else "🟠" if p >= 0 else "🔴"),
        rotulo: nome, "Venda (R$)": d["venda"].map(_m), "HL vendido": d["hl_venda"].map(lambda v: _n(v, 1)),
        "Preço/HL": (d["venda"] / d["hl_venda"].where(d["hl_venda"] > 0)).map(_m),
        "Custo/HL": (d["cmv"] / d["hl_venda"].where(d["hl_venda"] > 0)).map(_m), "CMV (R$)": d["cmv"].map(_m),
        "Margem (R$)": d["margem"].map(_m), "Margem %": d["margem_pct"].map(_p), "Margem/HL": d["margem_hl"].map(_m),
    }).reset_index(drop=True)


def _linha_total(d: pd.DataFrame, rotulo: str) -> pd.DataFrame:
    t = d[["venda", "hl_venda", "cmv", "margem"]].sum()
    return pd.DataFrame([{"": "Σ", rotulo: "TOTAL", "Venda (R$)": _m(t["venda"]), "HL vendido": _n(t["hl_venda"], 1),
                          "Preço/HL": _m(_div(t["venda"], t["hl_venda"])), "Custo/HL": _m(_div(t["cmv"], t["hl_venda"])),
                          "CMV (R$)": _m(t["cmv"]), "Margem (R$)": _m(t["margem"]),
                          "Margem %": _p(_div(t["margem"], t["venda"]) * 100 if t["venda"] else None),
                          "Margem/HL": _m(_div(t["margem"], t["hl_venda"]))}])


def top_bottom(mg: pd.DataFrame, chave: str) -> None:
    com = mg[mg["cmv"].notna() & (mg["venda"] > 0)]
    if com.empty:
        st.info("Sem produtos com custo para calcular a margem.")
        return
    ordem = st.segmented_control("Ordenar por", ["Margem (R$)", "Margem %"], default="Margem (R$)",
                                 key=f"{chave}_tb_ordem") or "Margem (R$)"
    col = "margem" if ordem == "Margem (R$)" else "margem_pct"
    base = com if col == "margem" else com[com["hl_venda"] >= com["hl_venda"].quantile(.25)]  # % sem itens mínimos
    top, bot = base.nlargest(10, col), base.nsmallest(10, col)
    for titulo, d, cor in (("🏆 Top 10", top, graficos.CATEGORICAS[0]), ("🔻 Bottom 10", bot, "#c0392b")):
        with st.container():  # um abaixo do outro: tabela inteira visível
            st.markdown(f"**{titulo}** — {ordem.lower()}")
            graficos.mostrar(graficos.barras_h([f"{str(x)[:28]}" for x in d["descricao"].fillna(d["produto"])],
                                               d[col].round(1 if col == "margem_pct" else 0), cores=cor,
                                               sufixo="%" if col == "margem_pct" else "",
                                               textos=[_p(v) if col == "margem_pct" else _m(v) for v in d[col]]),
                             key=f"g_{chave}_{titulo[:3]}")
            ui.tabela(_vis_margem(d, "Produto", "produto"), baixar=f"margem_{titulo[2:].strip().lower()}")


_CSS_FLUXO = """
<style>
.fx { display:flex; align-items:stretch; gap:.35rem; flex-wrap:wrap; margin:.4rem 0 1rem; }
.fx .b { flex:1 1 150px; background:#fff; border:1px solid #dfe5ee; border-radius:14px; padding:.7rem .85rem;
    border-top:5px solid var(--c); box-shadow:0 2px 6px rgba(11,31,58,.06); }
.fx .b .t { font-size:.78rem; font-weight:800; color:#52514e; text-transform:uppercase; letter-spacing:.03em; }
.fx .b .v { font-size:1.2rem; font-weight:900; color:#0B1F3A; margin:.2rem 0 .1rem; }
.fx .b .m { font-size:.76rem; color:#6b6a65; }
.fx .op { display:flex; align-items:center; font-size:1.5rem; font-weight:900; color:#2a78d6; padding:0 .1rem; }
.fx .b.res { background:linear-gradient(135deg,#0B1F3A 0%,#2a78d6 100%); border:none; }
.fx .b.res .t, .fx .b.res .m { color:#d6e4f7; } .fx .b.res .v { color:#fff; }
</style>
"""


def _fluxo(c: dict, venda: float, um_mes: bool) -> None:
    """Início + Compra − Fim = CMV · Venda − CMV = Resultado (pelo estoque 02.05.02) — o mesmo cálculo do DRE."""
    import html as _h

    ok, ei, ef, compras, cmv = c["ok"], c["ei"], c["ef"], c["compras"], c["cmv"]
    ini = fim = c
    res = venda - cmv if cmv is not None else None
    e = _h.escape

    def caixa(t, v, m, cor, res=False):
        return (f'<div class="b{" res" if res else ""}" style="--c:{cor}"><div class="t">{e(t)}</div>'
                f'<div class="v">{e(_m(v))}</div><div class="m">{e(m)}</div></div>')

    def op_(x):
        return f'<div class="op">{x}</div>'

    hl_c = f"{_n(c['compras_hl'])} HL comprados" if um_mes else f"compras do período · {_n(c['compras_hl'])} HL"
    pct = _p(_div(res, venda) * 100 if res is not None and venda else None)
    linha1 = (caixa("📦 Início", ei if ok else None, f"estoque inicial · {_n(ini['ei_hl'])} HL" if ok
                    else "suba o 02.05.02", "#9aa3b2") + op_("+")
              + caixa("🛒 Compra", compras, hl_c, "#2a78d6") + op_("−")
              + caixa("🏬 Fim", ef if ok else None, f"estoque final · {_n(fim['ef_hl'])} HL" if ok
                      else "suba o 02.05.02", "#9aa3b2") + op_("=")
              + caixa("🧮 CMV", cmv, "custo da mercadoria vendida", "#eda100"))
    linha2 = (caixa("💵 Venda", venda, "faturamento (operações de venda)", "#1baf7a") + op_("−")
              + caixa("🧮 CMV", cmv, "início + compra − fim", "#eda100") + op_("=")
              + caixa("💰 Resultado", res, f"lucro bruto real · margem {pct}", "#0B1F3A", True))
    html = [f'<div class="fx">{linha1}</div><div class="fx">{linha2}</div>']
    tema.secao("🔄 Início + Compra − Fim = CMV · Venda − CMV = Resultado",
               "Lucro bruto real pelo estoque (02.05.02 saldo inicial e final) e pelas notas de compra e venda.")
    st.markdown(_CSS_FLUXO + "".join(html), unsafe_allow_html=True)
    if not ok:
        st.caption("📦 Para fechar a conta, suba o 02.05.02 (saldo inicial e saldo final) em 🏛️ › 📥 Relatórios.")


def _clientes_lucro(op: int, de: str, ate: str) -> None:
    tema.secao("👥 Lucro por cliente — 20 que mais e 20 que menos deram lucro",
               "Lucro = venda − HL (venda + bonificação) × custo/HL de cada produto comprado. Inclui o efeito da "
               "bonificação dada ao cliente. Em %, entram só clientes com venda relevante (acima do 1º quartil).")
    cl = fs.lucro_clientes(op, de, ate)
    if cl.empty:
        st.info("Suba de novo a 03.02.37 vendas do período (esta versão passou a guardar cliente × produto) para ver o "
                "lucro por cliente.")
        return
    visao = st.segmented_control("Visão", ["R$ (lucro)", "% (margem)"], default="R$ (lucro)",
                                 key="cli_lucro_ordem") or "R$ (lucro)"
    em_pct = visao.startswith("%")
    base = cl[cl["venda"] >= cl["venda"].quantile(.25)] if em_pct else cl
    col = "margem_pct" if em_pct else "lucro"
    melhor = base.nlargest(20, col)
    pior = base.nsmallest(20, col)
    neg = cl[cl["lucro"] < 0]
    tot_l, tot_v = cl["lucro"].sum(), cl["venda"].sum()
    tema.kpis([
        {"titulo": "Lucro dos 20 melhores", "valor": _m(melhor["lucro"].sum()), "icone": "🏆", "status": "bom",
         "detalhe": f"{_p(_div(melhor['lucro'].sum(), tot_l) * 100 if tot_l else None)} do lucro · margem "
                    f"{_p(_div(melhor['lucro'].sum(), melhor['venda'].sum()) * 100 if melhor['venda'].sum() else None)}",
         "dados": _vis_clientes(melhor)},
        {"titulo": "Lucro dos 20 piores", "valor": _m(pior["lucro"].sum()), "icone": "📉", "status": "atencao",
         "detalhe": f"venda {_m(pior['venda'].sum())} · margem "
                    f"{_p(_div(pior['lucro'].sum(), pior['venda'].sum()) * 100 if pior['venda'].sum() else None)}",
         "dados": _vis_clientes(pior)},
        {"titulo": "Clientes com prejuízo", "valor": _n(len(neg)), "icone": "🔻",
         "status": "critico" if len(neg) else "bom", "detalhe": f"{_m(neg['lucro'].sum())} de lucro negativo",
         "dados": _vis_clientes(neg) if len(neg) else None},
        {"titulo": "Clientes analisados", "valor": _n(len(cl)), "icone": "👥", "status": "info",
         "detalhe": f"margem média {_p(_div(tot_l, tot_v) * 100 if tot_v else None)}"},
    ], key="kp_cli_lucro")
    g1, g2 = st.columns(2)
    for colg, d, titulo, chave in ((g1, melhor, "🏆 20 que mais deram lucro", "g_cli_mais"),
                                   (g2, pior, "🔻 20 que menos deram lucro", "g_cli_menos")):
        with colg:
            rot = [f"{str(n or c)[:24]}" for c, n in zip(d["cliente"], d["nome"])]
            cores = ["#c0392b" if v < 0 else "#1baf7a" if chave == "g_cli_mais" else "#eda100" for v in d["lucro"]]
            graficos.mostrar(graficos.barras_h(rot, d[col].round(1 if em_pct else 0), cores=cores,
                                               textos=[_p(v) if em_pct else _m(v) for v in d[col]],
                                               titulo=f"{titulo} ({'margem %' if em_pct else 'R$'})"), key=chave)
    t1, t2 = st.columns(2)
    with t1.expander("📋 Tabela — 20 que mais deram lucro"):
        ui.tabela(_vis_clientes(melhor, total=True), baixar="clientes_maior_lucro")
    with t2.expander("📋 Tabela — 20 que menos deram lucro"):
        ui.tabela(_vis_clientes(pior, total=True), baixar="clientes_menor_lucro")
    with st.expander("📋 Todos os clientes (do menor para o maior lucro)"):
        ui.tabela(pd.DataFrame({"Cliente": cl["cliente"].astype(str) + " · " + cl["nome"].fillna(""),
                                "Venda (R$)": cl["venda"].map(_m), "Custo (R$)": cl["cmv"].map(_m),
                                "Lucro (R$)": cl["lucro"].map(_m), "Margem %": cl["margem_pct"].map(_p)}),
                  baixar="clientes_lucro_todos", height=600)


def _vis_clientes(d: pd.DataFrame, total: bool = False) -> pd.DataFrame:
    vis = pd.DataFrame({"Cliente": d["cliente"].astype(str) + " · " + d["nome"].fillna(""),
                        "Venda (R$)": d["venda"].map(_m), "HL (c/ bonif.)": d["hl"].map(lambda v: _n(v, 1)),
                        "Custo (R$)": d["cmv"].map(_m), "Lucro (R$)": d["lucro"].map(_m),
                        "Margem %": d["margem_pct"].map(_p), "Lucro/HL": d["lucro_hl"].map(_m),
                        "Produtos": d["produtos"].map(_n)}).reset_index(drop=True)
    if total and len(d):
        vis.loc[len(vis)] = [f"TOTAL ({len(d)})", _m(d["venda"].sum()), _n(d["hl"].sum(), 1), _m(d["cmv"].sum()),
                             _m(d["lucro"].sum()), _p(_div(d["lucro"].sum(), d["venda"].sum()) * 100
                                                      if d["venda"].sum() else None), "", ""]
    return vis


def render_margem(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 💰 Financeiro › **📊 Resumo & Lucro Bruto**")
    op = ui.visao_acompanhamento(usuario, operacao_id, "margem")
    meses = fs.meses(op, "venda")
    if not meses or not fs.meses(op, "compra"):
        st.info("Para a margem é preciso ter a 03.02.37 vendas e a 03.02.37 compra carregadas.")
        _ir_relatorios("mg")
        return
    c1, c2, c3 = st.columns([1.3, 1, 1])
    with c1:
        modo = ui._escolha("mg_modo", ["mes", "ano", "per"], "mes", pills=True,
                           formatar={"mes": "🗓️ Mês", "ano": "📆 Ano", "per": "↔️ Meses"}.get)
    if modo == "mes":
        m = ui.seletor_mes("Mês", meses, key="mg_mes", container=c2)
        de, ate, rotulo = m, m, ui.nome_mes(m)
    elif modo == "ano":
        a = c2.selectbox("Ano", sorted({x[:4] for x in meses}, reverse=True), key="mg_ano")
        de, ate, rotulo = f"{a}-01", f"{a}-12", f"ano {a}"
    else:
        de = ui.seletor_mes("De", sorted(meses), key="mg_de", container=c2)
        ate = ui.seletor_mes("Até", meses, key="mg_ate", container=c3)
        de, ate = min(de, ate), max(de, ate)
        rotulo = f"{ui.nome_mes(de)} a {ui.nome_mes(ate)}"
    mg = fs.margem(op, de, ate)
    if mg.empty:
        st.info(f"Sem vendas em {rotulo}.")
        return
    com = mg[mg["cmv"].notna()]
    t = com[["venda", "hl_venda", "cmv", "margem"]].sum()
    sem = mg[mg["cmv"].isna()]
    pct = _div(t["margem"], t["venda"]) * 100 if t["venda"] else None
    # resumo total: venda, bonificação, compra (investido), CMV e lucro bruto
    m_de, m_ate = fs.periodo_mes(de)[0], fs.periodo_mes(ate)[1]
    dv = fs.dia_df(op, "venda", m_de, m_ate, fs.STATUS_PADRAO["venda"])
    dc = fs.dia_df(op, "compra", m_de, m_ate, fs.STATUS_PADRAO["compra"])
    bonif = fs.totais(fs.separar(dv, {"b": fs.operacoes_do_setor("fat_bonif")})["b"])
    compra = fs.combinar(dc, fs.operacoes_do_setor("compra"), fs.operacoes_do_setor("hl_compra"))
    venda = fs.combinar(dv, fs.operacoes_do_setor("fat_venda"), fs.operacoes_do_setor("hl_venda"))
    from services import estoque_valor_service as ev

    ms = sorted(x for x in meses if de <= x <= ate) or [de]
    cr = ev.cmv_periodo(op, ms)  # CMV pelo estoque — o mesmo do 📑 DRE
    if cr["ok"]:
        cmv_k, lucro_k = cr["cmv"], venda["valor"] - cr["cmv"]
        det_cmv = f"início + compra − fim (igual ao DRE) · por custo de produto: {_m(t['cmv'])}"
    else:
        cmv_k, lucro_k = t["cmv"], t["margem"]
        det_cmv = f"pelo custo de compra dos produtos (sem 02.05.02) · {_m(_div(t['cmv'], t['hl_venda']))}/HL"
    pct = _div(lucro_k, venda["valor"]) * 100 if venda["valor"] else None
    tema.secao(f"🧾 Resumo · {rotulo}")
    tema.kpis([
        {"titulo": "Vendas (R$)", "valor": _m(venda["valor"]), "icone": "💵", "status": "info",
         "detalhe": f"{_n(venda['hl'])} HL (venda + bonificação)"},
        {"titulo": "Bonificação concedida", "valor": _m(bonif["valor"]), "icone": "🎁", "status": "info",
         "detalhe": f"{_n(bonif['hl'])} HL · entra no HL, não no R$"},
        {"titulo": "Compras (investido)", "valor": _m(compra["valor"]), "icone": "🛒", "status": "info",
         "detalhe": f"{_n(compra['hl'])} HL · {_m(compra['rs_hl'])} por HL"},
        {"titulo": "Custo da mercadoria vendida", "valor": _m(cmv_k), "icone": "📦", "status": "info",
         "detalhe": det_cmv},
        {"titulo": "Lucro bruto", "valor": _m(lucro_k), "icone": "💰",
         "status": "neutro" if pct is None else "bom" if pct >= 20 else "atencao" if pct >= 10 else "critico",
         "detalhe": f"margem {_p(pct)} · {_m(_div(lucro_k, venda['hl']))} por HL"},
        {"titulo": "Produtos com margem negativa", "valor": _n((com["margem"] < 0).sum()), "icone": "🔻",
         "status": "critico" if (com["margem"] < 0).any() else "bom",
         "detalhe": f"{_m(com.loc[com['margem'] < 0, 'margem'].sum())} de margem negativa",
         "dados": _vis_margem(com[com["margem"] < 0].sort_values("margem"), "Produto", "produto")},
        {"titulo": "Sem custo de compra", "valor": _n(len(sem)), "icone": "❔",
         "status": "atencao" if len(sem) else "bom", "detalhe": f"{_m(sem['venda'].sum())} de venda fora da conta",
         "dados": pd.DataFrame({"Produto": sem["produto"].astype(str) + " · " + sem["descricao"].fillna(""),
                                "Venda": sem["venda"].map(_m), "HL": sem["hl_venda"].map(lambda v: _n(v, 1))})
         if len(sem) else None},
    ], key="kp_margem")
    _fluxo(cr, float(venda["valor"]), len(ms) == 1)
    if de != ate:  # mais de um mês: lucro bruto mês a mês
        linhas = []
        for m in sorted(x for x in meses if de <= x <= ate):
            d0, d1 = fs.periodo_mes(m)
            vm = fs.combinar(fs.dia_df(op, "venda", d0, d1, fs.STATUS_PADRAO["venda"]),
                             fs.operacoes_do_setor("fat_venda"), fs.operacoes_do_setor("hl_venda"))
            cm = ev.cmv_real(op, m)["cmv"]
            if cm is None:  # sem 02.05.02 no mês: custo de compra por produto
                mm = fs.margem(op, m, m)
                c_ = mm[mm["cmv"].notna()] if not mm.empty else mm
                if c_.empty:
                    continue
                cm = float(c_["cmv"].sum())
            linhas.append({"Mês": f"{ui.nome_mes(m)}", "venda": vm["valor"], "cmv": cm,
                           "margem": vm["valor"] - cm, "hl": vm["hl"]})
        if linhas:
            lm = pd.DataFrame(linhas)
            graficos.mostrar(graficos.barras(lm["Mês"], {"Vendas (R$ mil)": (lm["venda"] / 1000).round(1),
                                                         "CMV (R$ mil)": (lm["cmv"] / 1000).round(1),
                                                         "Lucro bruto (R$ mil)": (lm["margem"] / 1000).round(1)},
                                             titulo="Vendas, custo e lucro bruto por mês"), key="g_mg_meses")
            vis = pd.DataFrame({"Mês": lm["Mês"], "Vendas": lm["venda"].map(_m), "CMV": lm["cmv"].map(_m),
                                "Lucro bruto": lm["margem"].map(_m),
                                "Margem %": (lm["margem"] / lm["venda"] * 100).map(_p),
                                "Lucro/HL": (lm["margem"] / lm["hl"]).map(_m)})
            vis.loc[len(vis)] = ["TOTAL", _m(lm["venda"].sum()), _m(lm["cmv"].sum()), _m(lm["margem"].sum()),
                                 _p(_div(lm["margem"].sum(), lm["venda"].sum()) * 100),
                                 _m(_div(lm["margem"].sum(), lm["hl"].sum()))]
            ui.tabela(vis, baixar="lucro_bruto_mensal")
    origem = com["origem_custo"].value_counts()
    st.caption("Custo/HL: " + " · ".join(f"{k}: {v} produtos" for k, v in origem.items())
               + ". Venda = operações de R$ de venda; HL = venda + bonificação (⚙️ Cadastros).")

    tema.secao("🏆 Top 10 e 🔻 Bottom 10 por produto")
    top_bottom(mg, "mg")
    _clientes_lucro(op, de, ate)

    tema.secao("🧩 Abertura da margem")
    ab = ui._escolha("mg_abertura", list(_ABERTURAS), "tipo", formatar=_ABERTURAS.get, pills=True)
    f1, f2, f3 = st.columns(3)
    ft = f1.multiselect("Tipo", sorted(com["tipo"].unique()), key="mg_ft", placeholder="Todos")
    fe = f2.multiselect("Embalagem", sorted(com["embalagem"].unique()), key="mg_fe", placeholder="Todas")
    fm = f3.multiselect("Marca", sorted(com["marca"].unique()), key="mg_fm", placeholder="Todas")
    d = com
    if ft:
        d = d[d["tipo"].isin(ft)]
    if fe:
        d = d[d["embalagem"].isin(fe)]
    if fm:
        d = d[d["marca"].isin(fm)]
    if d.empty:
        st.info("Nada com esses filtros.")
        return
    rot = _ABERTURAS[ab].split(" ", 1)[1]
    g = d.sort_values("margem", ascending=False) if ab == "produto" else fs.margem_por(d, ab)
    if ab != "produto":
        graficos.mostrar(graficos.barras_h(g[ab], g["margem"].round(0), textos=[
            f"{_m(m)} · {_p(p)}" for m, p in zip(g["margem"], g["margem_pct"])], cores=[
            graficos.CATEGORICAS[0] if m >= 0 else "#c0392b" for m in g["margem"]], titulo=f"Margem bruta por {rot.lower()}"),
            key=f"g_mg_{ab}")
    vis = _vis_margem(g, rot, ab)
    if ab != "produto":
        vis.insert(2, "Produtos", g["produtos"].map(_n).values)
        vis["Part. na margem"] = g["part"].map(_p).values
    ui.tabela(pd.concat([vis, _linha_total(d, rot)], ignore_index=True).fillna(""), baixar=f"margem_por_{ab}")
    if ab == "produto":
        st.caption("Custo de cada produto: " + "compra do período, custo médio histórico ou média da categoria "
                   "(ver coluna no Excel).")
