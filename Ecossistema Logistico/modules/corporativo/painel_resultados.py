"""🏛️ Gestão Corporativa › 📊 Gestão › 🏆 Painel de Resultados — todos os resultados da operação no mês, em cartões
que abrem o detalhe ao clicar (comparando com o mês anterior)."""
import pandas as pd
import streamlit as st

from core import graficos, tema, ui
from services import resultados_service as rs


def _m(v) -> str:
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else ui.moeda(v)


def _n(v, c=0) -> str:
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else ui.numero(v, c)


def _p(v) -> str:
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:.1f}%".replace(".", ",")


def _var(a, b) -> str:
    """Variação contra o mês anterior."""
    try:
        if a is None or b in (None, 0) or pd.isna(a) or pd.isna(b):
            return "sem mês anterior"
        v = (a / b - 1) * 100
        return f"{'▲' if v >= 0 else '▼'} {abs(v):.1f}% vs mês anterior".replace(".", ",")
    except Exception:  # noqa: BLE001
        return ""


def _g(d: dict, k: str):
    return d.get(k) if isinstance(d, dict) else None


def render(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 📊 Gestão › **🏆 Painel de Resultados**")
    op = ui.visao_acompanhamento(usuario, operacao_id, "painel_res")
    c1, c2 = st.columns([1, 2.5])
    meses = rs.meses_disponiveis(op)
    mes = c1.selectbox("Mês", meses, format_func=ui.nome_mes, key="painel_res_mes")
    with st.spinner("Juntando os resultados…"):
        r = rs.resumo_mes(op, mes)
    v, va, c, d, da, e, ea, sh, ac = (r["vendas"], r["vendas_ant"], r["compras"], r["dre"], r["dre_ant"], r["entrega"],
                                      r["entrega_ant"], r["shelf"], r["acuracidade"])
    c2.caption(f"Resultados de **{ui.nome_mes(mes)}** comparados com {ui.nome_mes(r['anterior'])}. Clique nos cartões "
               "para abrir o detalhe.")

    tema.secao("💵 Vendas")
    top_p = rs._seguro(rs.top, op, mes, "produtos", 20)
    top_c = rs._seguro(rs.top, op, mes, "clientes", 20)
    tabp = (pd.DataFrame({"Cód": top_p["produto"], "Produto": top_p["descricao"], "Faturamento": top_p["valor"].map(_m),
                          "HL": top_p["hl"].map(lambda x: _n(x, 1)), "R$/HL": top_p["rs_hl"].map(_m)})
            if isinstance(top_p, pd.DataFrame) and not top_p.empty else None)
    tabc = (pd.DataFrame({"Cliente": top_c["cliente"], "Nome": top_c["nome"], "Faturamento": top_c["valor"].map(_m),
                          "HL": top_c["hl"].map(lambda x: _n(x, 1))})
            if isinstance(top_c, pd.DataFrame) and not top_c.empty else None)
    dia = _g(v, "por_dia")
    tabd = (pd.DataFrame({"Dia": pd.to_datetime(dia["data"]).dt.strftime("%d/%m"), "Faturamento": dia["valor"].map(_m),
                          "HL": dia["hl"].map(lambda x: _n(x, 1)), "R$/HL": dia["rs_hl"].map(_m)})
            if isinstance(dia, pd.DataFrame) and not dia.empty else None)
    tema.kpis([
        {"titulo": "Faturamento", "valor": _m(_g(v, "faturamento")), "icone": "💵", "status": "info",
         "detalhe": _var(_g(v, "faturamento"), _g(va, "faturamento")), "dados": tabd},
        {"titulo": "HL vendido", "valor": _n(_g(v, "hl"), 1), "icone": "🍺", "status": "info",
         "detalhe": _var(_g(v, "hl"), _g(va, "hl")), "dados": tabp},
        {"titulo": "R$/HL", "valor": _m(_g(v, "rs_hl")), "icone": "🏷️", "status": "info",
         "detalhe": _var(_g(v, "rs_hl"), _g(va, "rs_hl")), "dados": tabp},
        {"titulo": "Clientes (top 20)", "valor": _n(len(top_c)) if isinstance(top_c, pd.DataFrame) else "—",
         "icone": "🧑‍🤝‍🧑", "status": "info", "detalhe": "maiores do mês", "dados": tabc},
        {"titulo": "Compras", "valor": _m(_g(c, "compras")), "icone": "🛒", "status": "info",
         "detalhe": f"{_n(_g(c, 'hl'), 1)} HL · {_var(_g(c, 'compras'), _g(r['compras_ant'], 'compras'))}"},
    ], key=f"kp_res_v_{op}_{mes}")

    tema.secao("📑 Resultado (DRE)")
    deps = _g(d, "departamentos")
    tabdep = (pd.DataFrame({"Departamento": deps["departamento"], "Realizado": deps["realizado"].map(_m),
                            "Plan": deps["orcado"].map(_m)})
              if isinstance(deps, pd.DataFrame) and not deps.empty else None)
    tabdre = None
    if isinstance(d, dict) and "_bruto" in d:
        from modules.corporativo import estoque_dre

        tabdre = estoque_dre.montar_tabela([mes], [d["_bruto"]], d["_bruto"], ui.nome_mes(mes))
    mb, mo = _g(d, "margem_bruta"), _g(d, "margem_operacional")
    res = _g(d, "resultado")
    tema.kpis([
        {"titulo": "Receita líquida", "valor": _m(_g(d, "receita_liquida")), "icone": "💰", "status": "info",
         "detalhe": _var(_g(d, "receita_liquida"), _g(da, "receita_liquida")), "dados": tabdre},
        {"titulo": "Lucro bruto", "valor": _m(_g(d, "lucro_bruto")), "icone": "📦",
         "status": "neutro" if mb is None else "bom" if mb >= 20 else "atencao" if mb >= 10 else "critico",
         "detalhe": f"margem {_p(mb)}" if _g(d, "estoque_ok") else "falta o 02.05.02 (estoque)", "dados": tabdre},
        {"titulo": "Despesas", "valor": _m(_g(d, "despesas")), "icone": "🧾", "status": "info",
         "detalhe": ("🔒 contabilidade" if _g(d, "fechado") else "prévia OBZ") + " · "
                    + _var(_g(d, "despesas"), _g(da, "despesas")), "dados": tabdep},
        {"titulo": "Resultado operacional", "valor": _m(res), "icone": "🏆",
         "status": "neutro" if res is None else "bom" if res >= 0 else "critico",
         "detalhe": f"margem {_p(mo)}", "dados": tabdre},
    ], key=f"kp_res_d_{op}_{mes}")

    tema.secao("🚚 Entrega")
    pv = _g(e, "por_veiculo")
    tabv = (pd.DataFrame({"Veículo": pv["veiculo"], "Viagens": pv["viagens"].map(_n), "Placas": pv["placas"].map(_n),
                          "HL": pv["hl"].map(lambda x: _n(x, 1))})
            if isinstance(pv, pd.DataFrame) and not pv.empty and "viagens" in pv else None)
    fsug = _g(e, "frota_sugerida")
    tabf = (pd.DataFrame({"Modal": fsug["modal"], "Placas usadas": fsug["placas_atuais"].map(_n),
                          "Pico de uso": fsug["atual_max"].map(_n), "Frota sugerida": fsug["sugerido"].map(_n)})
            if isinstance(fsug, pd.DataFrame) and not fsug.empty else None)
    mc = _g(e, "modal_certo_pct")
    tema.kpis([
        {"titulo": "Viagens", "valor": _n(_g(e, "viagens")), "icone": "🚚", "status": "info",
         "detalhe": f"{_n(_g(e, 'placas'))} placas · " + _var(_g(e, "viagens"), _g(ea, "viagens")), "dados": tabv},
        {"titulo": "HL por viagem", "valor": _n(_g(e, "hl_viagem"), 1), "icone": "🍺", "status": "info",
         "detalhe": _var(_g(e, "hl_viagem"), _g(ea, "hl_viagem")), "dados": tabv},
        {"titulo": "Ocupação média", "valor": _p(_g(e, "ocup_efetiva")), "icone": "📦",
         "status": "neutro" if _g(e, "ocup_efetiva") is None else "bom" if _g(e, "ocup_efetiva") >= 85
         else "atencao" if _g(e, "ocup_efetiva") >= 70 else "critico", "detalhe": "caixas ou peso (o maior)"},
        {"titulo": "Viagens no modal certo", "valor": _p(mc), "icone": "✅",
         "status": "neutro" if mc is None else "bom" if mc >= 80 else "atencao" if mc >= 65 else "critico",
         "detalhe": f"{_n(_g(e, 'cabe_menor'))} cabiam em menor", "dados": tabf},
    ], key=f"kp_res_e_{op}_{mes}")

    tema.secao("📦 Estoque")
    lst = _g(sh, "lista")
    tabs = (pd.DataFrame({"Cód": lst["produto"], "Produto": lst["descricao"], "Urgência": lst["urgencia"],
                          "Vai vencer (cx)": lst["vencer_cx"].map(_n), "Vai vencer (R$)": lst["vencer_valor"].map(_m)})
            if isinstance(lst, pd.DataFrame) and not lst.empty else None)
    la = _g(ac, "lista")
    taba = (pd.DataFrame({"Cód": la["produto"], "Produto": la["descricao"], "Situação": la["situacao"],
                          "Diferença (cx)": la["dif_cx"].map(lambda x: f"{x:+.1f}".replace(".", ","))})
            .loc[la["situacao"] != "✅ ok"] if isinstance(la, pd.DataFrame) and not la.empty else None)
    acu = _g(ac, "acuracidade")
    tema.kpis([
        {"titulo": "Risco de vencer (shelf)", "valor": _m(_g(sh, "valor")), "icone": "🧊",
         "status": "critico" if _g(sh, "valor") else "bom", "detalhe": f"{_n(_g(sh, 'produtos'))} produto(s)",
         "dados": tabs},
        {"titulo": "Acuracidade do inventário", "valor": _p(acu), "icone": "🎯",
         "status": "neutro" if acu is None else "bom" if acu >= 98 else "atencao" if acu >= 95 else "critico",
         "detalhe": _g(ac, "inventario") or "sem inventário", "dados": taba},
        {"titulo": "Sobra / falta (inventário)", "valor": f"{_n(_g(ac, 'sobra_cx'), 1)} / {_n(_g(ac, 'falta_cx'), 1)} cx",
         "icone": "⚖️", "status": "info", "detalhe": "último inventário mensal", "dados": taba},
    ], key=f"kp_res_s_{op}_{mes}")

    with st.expander("📈 Evolução dos últimos 12 meses"):
        ev = rs._seguro(rs.evolucao, op, 12, mes)
        if isinstance(ev, pd.DataFrame) and not ev.empty:
            x = [ui.nome_mes(m)[:3] + "/" + m[2:4] for m in ev["mes"]]
            graficos.mostrar(graficos.barras(x, {"Faturamento (R$ mil)": (ev["faturamento"].fillna(0) / 1000).tolist(),
                                                 "Compras (R$ mil)": (ev["compras"].fillna(0) / 1000).tolist(),
                                                 "Resultado (R$ mil)": (ev["resultado"].fillna(0) / 1000).tolist()},
                                             titulo="Faturamento, compras e resultado operacional por mês"),
                             key=f"g_res_ev_{op}")
            ui.tabela(pd.DataFrame({"Mês": [ui.nome_mes(m) for m in ev["mes"]], "Faturamento": ev["faturamento"].map(_m),
                                    "HL": ev["hl"].map(lambda x: _n(x, 1)), "Compras": ev["compras"].map(_m),
                                    "Resultado": ev["resultado"].map(_m)}), baixar=f"evolucao_{op}")
        else:
            st.caption("Sem dados suficientes para a evolução.")
