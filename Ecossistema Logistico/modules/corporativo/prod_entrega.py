"""Gestão Corporativa › 🚚 Logística › 📦 Produtividade › Produtividade Entrega.

Bases: PCD (mapas) + 03.02.37 vendas (notas — HL pela coluna T × fator HL da 01.11).
Telas: 📊 Visão geral · 🚚 Por placa · 📅 Gestão anual · 🔮 Previsão de modais · ⬆️ Atualizar dados.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from config.settings import MODAIS
from core import graficos, tema, ui
from repositories import operacoes_repo
from services import produtividade_entrega_service as svc
from services.erros import RegraNegocioError

_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_TELAS = {"geral": "📊 Visão geral", "placa": "🚚 Por placa", "anual": "📅 Gestão anual",
          "modais": "🔮 Previsão de modais"}
_OPER = {"1": "1 · Venda", "2": "2 · Bonificação", "5": "5 · Troca", "9": "9 · Comodato"}
_STATUS = {"A": "A · Ativa", "C": "C · Cancelada", "D": "D · Devolvida", "E": "E · Estornada"}


def _farol(p) -> str:
    if p is None or pd.isna(p):
        return "⚪"
    return "🟢" if p >= 85 else "🟡" if p >= 70 else "🔴"


def _st_ocup(p) -> str:
    return "neutro" if p is None or pd.isna(p) else "bom" if p >= 85 else "atencao" if p >= 70 else "critico"


def _n(v, casas=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, casas)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%".replace(".", ",")


def _tabela_kpi(g: pd.DataFrame, primeira: dict[str, str]) -> pd.DataFrame:
    """Formata a tabela padrão de produtividade (agrupada)."""
    out = {rot: g[col] for col, rot in primeira.items()}
    out.update({
        "": g["ocup_efetiva"].map(_farol),
        "Viagens": g["viagens"].map(_n),
        "Entregas": g["entregas"].map(_n),
        "HL entregue": g["hl"].map(_n),
        "HL/viagem": g["hl_viagem"].map(lambda v: _n(v, 1)),
        "Entregas/viagem": g["entregas_viagem"].map(lambda v: _n(v, 1)),
        "Ocup. caixas": g["ocup_cx"].map(_p),
        "Ocup. peso": g["ocup_peso"].map(_p),
        "Peso médio (kg)": g["peso_medio"].map(_n),
        "Média caixas": g["caixas_media"].map(lambda v: _n(v, 1)),
        "KM previsto": g["km_total"].map(_n),
        "KM/viagem": g["km_medio"].map(lambda v: _n(v, 1)),
        "Eficiência": g["eficiencia"].map(_p),
    })
    df = pd.DataFrame(out)
    return df[[""] + [c for c in df.columns if c != ""]].reset_index(drop=True)


def _total(df: pd.DataFrame, primeira: dict[str, str], rotulo: str = "TOTAL") -> pd.DataFrame:
    """Linha de total (das viagens filtradas) no mesmo formato da tabela."""
    g = svc._agrupar(df.assign(_t=rotulo), ["_t"])
    linha = _tabela_kpi(g, {"_t": list(primeira.values())[0]})
    for rot in list(primeira.values())[1:]:
        linha[rot] = ""
    linha[""] = "Σ"
    return linha


def _com_total(vis: pd.DataFrame, df: pd.DataFrame, primeira: dict[str, str], extras: dict | None = None) -> pd.DataFrame:
    tot = _total(df, primeira)
    for k, v in (extras or {}).items():
        tot[k] = v
    return pd.concat([vis, tot[[c for c in vis.columns if c in tot.columns]]], ignore_index=True).fillna("")


# --- Filtros ---------------------------------------------------------------------------------------
def _periodo(operacao_id: int, chave: str) -> tuple[str, str, str] | None:
    meses = svc.meses_disponiveis(operacao_id)
    if not meses:
        return None
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        modo = ui._escolha(f"{chave}_modo", ["mes", "ano", "per"], "mes", pills=True,
                           formatar={"mes": "📅 Mês", "ano": "🗓️ Ano", "per": "↔️ Período"}.get)
    if modo == "mes":
        m = ui.seletor_mes("Mês", meses, key=f"{chave}_mes", container=c2)
        a, mm = map(int, m.split("-"))
        fim = (dt.date(a + (mm == 12), mm % 12 + 1, 1) - dt.timedelta(days=1))
        return f"{m}-01", fim.isoformat(), ui.nome_mes(m)
    if modo == "ano":
        anos = sorted({m[:4] for m in meses}, reverse=True)
        a = c2.selectbox("Ano", anos, key=f"{chave}_ano")
        return f"{a}-01-01", f"{a}-12-31", f"ano {a}"
    de0, ate0 = svc.periodo_disponivel(operacao_id)
    de = c2.date_input("De", value=dt.date.fromisoformat(de0), format="DD/MM/YYYY", key=f"{chave}_de")
    ate = c3.date_input("Até", value=dt.date.fromisoformat(ate0), format="DD/MM/YYYY", key=f"{chave}_ate")
    de, ate = min(de, ate), max(de, ate)
    return de.isoformat(), ate.isoformat(), f"{de:%d/%m/%Y} a {ate:%d/%m/%Y}"


def _filtro_notas(operacao_id: int, chave: str) -> dict:
    opc = svc.opcoes_filtro(operacao_id)
    padrao = svc.filtro_padrao(opc)
    if not any(opc.values()):
        return {}
    resumo = " · ".join(f"{k}: {', '.join(v)}" for k, v in (("Operação", padrao["operacao"]),
                                                             ("Tipo movto", padrao["tipo_movto"]),
                                                             ("Status", padrao["status"])))
    with st.expander(f"🧾 Filtro das notas (03.02.37 vendas) — padrão: {resumo}"):
        c1, c2, c3 = st.columns(3)
        f = {"operacao": c1.multiselect("Operação", opc["operacao"], default=padrao["operacao"],
                                        format_func=lambda x: _OPER.get(x, x), key=f"{chave}_fo"),
             "tipo_movto": c2.multiselect("Tipo de movimento", opc["tipo_movto"], default=padrao["tipo_movto"],
                                          key=f"{chave}_ft"),
             "status": c3.multiselect("Status", opc["status"], default=padrao["status"],
                                      format_func=lambda x: _STATUS.get(x, x), key=f"{chave}_fs")}
        st.caption("O HL de cada mapa soma só as notas que passam neste filtro. Padrão: venda (1/51) e nota ativa (A).")
    return f


def _filtros_viagem(df: pd.DataFrame, chave: str) -> pd.DataFrame:
    c1, c2, c3 = st.columns(3)
    veic = c1.multiselect("Veículo", sorted(df["veiculo"].dropna().unique()), key=f"{chave}_fv",
                          placeholder="Todos")
    cla = c2.multiselect("Classificação", sorted(df["classificacao"].dropna().unique()), key=f"{chave}_fc",
                         placeholder="Todas")
    pla = c3.multiselect("Placa", sorted(df["placa"].dropna().unique()), key=f"{chave}_fp", placeholder="Todas")
    if veic:
        df = df[df["veiculo"].isin(veic)]
    if cla:
        df = df[df["classificacao"].isin(cla)]
    if pla:
        df = df[df["placa"].isin(pla)]
    return df


# --- Telas ----------------------------------------------------------------------------------------
def _cards(r: dict, chave: str, df: pd.DataFrame) -> None:
    tema.kpis([
        {"titulo": "Viagens (mapas)", "valor": _n(r["viagens"]), "icone": "🚚", "status": "info",
         "detalhe": f"{r['placas']} placas · {r['dias']} dias"},
        {"titulo": "Entregas feitas", "valor": _n(r["entregas"]), "icone": "📍", "status": "info",
         "detalhe": f"{_n(r['entregas_viagem'], 1)} por viagem"},
        {"titulo": "HL entregue", "valor": f"{_n(r['hl'])} HL", "icone": "🍺", "status": "info",
         "detalhe": f"{_n(r['hl_viagem'], 1)} HL/viagem · {_n(r['hl_entrega'], 2)} HL/entrega"},
        {"titulo": "Média ocupação", "valor": _p(r["ocup_efetiva"]), "icone": "📦",
         "status": _st_ocup(r["ocup_efetiva"]),
         "detalhe": f"caixas {_p(r['ocup_cx'])} · peso {_p(r['ocup_peso'])}"},
        {"titulo": "Média peso", "valor": f"{_n(r['peso_medio'])} kg", "icone": "⚖️",
         "status": _st_ocup(r["ocup_peso"]), "detalhe": f"ocupação de peso {_p(r['ocup_peso'])}"},
        {"titulo": "KM previsto", "valor": f"{_n(r['km_total'])} km", "icone": "🛣️", "status": "info",
         "detalhe": f"{_n(r['km_medio'], 1)} km por viagem"},
        {"titulo": "Média caixas", "valor": _n(r["caixas_media"], 1), "icone": "🧃", "status": "info",
         "detalhe": "caixas por viagem (roteirizador)"},
        {"titulo": "Eficiência", "valor": _p(r["eficiencia"]), "icone": "⏱️",
         "status": _st_ocup(r["eficiencia"]), "detalhe": "média do relatório de mapas"},
    ], key=f"kp_{chave}")
    if r.get("sem_hl"):
        st.caption(f"⚠️ {r['sem_hl']} viagem(ns) sem nota na 03.02.37 (HL zerado) — suba a 03.02.37 vendas do mesmo "
                   "período ou revise o filtro das notas.")


def _visao_geral(df: pd.DataFrame, chave: str) -> None:
    r = svc.resumo(df)
    _cards(r, chave, df)
    d = svc.diario(df)
    g1, g2 = st.columns(2)
    with g1:
        graficos.mostrar(graficos.barras(d["data"].dt.strftime("%d/%m"), {"HL entregue": d["hl"].round(0)},
                                         titulo="HL entregue por dia", sufixo=" HL"), key=f"g_{chave}_hl")
    with g2:
        graficos.mostrar(graficos.linhas(d["data"].dt.strftime("%d/%m"),
                                         {"Ocupação caixas": d["ocup_cx"].round(1),
                                          "Ocupação peso": d["ocup_peso"].round(1)},
                                         titulo="Ocupação média por dia", sufixo="%"), key=f"g_{chave}_oc")
    tema.secao("🚛 Por tipo de veículo")
    pv = svc.por_veiculo(df)
    vis = _tabela_kpi(pv, {"veiculo": "Veículo"}).assign(Placas=pv["placas"].map(_n).values)
    ui.tabela(_com_total(vis, df, {"veiculo": "Veículo"}, {"Placas": _n(df["placa"].nunique())}),
              baixar="produtividade_por_veiculo")
    tema.secao("🗺️ Por classificação da rota")
    ui.tabela(_com_total(_tabela_kpi(svc.por_classificacao(df), {"classificacao": "Classificação"}), df,
                         {"classificacao": "Classificação"}), baixar="produtividade_por_classificacao")
    tema.secao("📅 Dia a dia")
    dd = _tabela_kpi(d, {"data": "Dia"})
    dd["Dia"] = d["data"].map(lambda x: f"{x:%d/%m} ({_SEMANA[x.weekday()]})").values
    dd.insert(2, "Placas", d["placas"].map(_n).values)
    ui.tabela(_com_total(dd, df, {"data": "Dia"}, {"Placas": _n(df["placa"].nunique())}),
              baixar="produtividade_dia_a_dia")


def _por_placa(df: pd.DataFrame, chave: str) -> None:
    pp = svc.por_placa(df)
    if pp.empty:
        st.info("Sem viagens no período.")
        return
    tem_cad = pp["proprietario"].notna().any() or pp["area"].notna().any()
    if not tem_cad:
        st.caption("💡 Cadastre as placas em 🔧 Frota › ⚙️ Cadastros › 🚚 Placas para trazer proprietário, aluguel, "
                   "locadora e área de cada placa aqui.")
    # filtros da tabela — o total embaixo soma só o que ficou visível
    f1, f2, f3, f4 = st.columns([1, 1, 1, 1.3])
    veic = f1.multiselect("Veículo", sorted(pp["veiculo"].dropna().unique()), key=f"{chave}_tv", placeholder="Todos")
    far = f2.multiselect("Farol", ["🟢", "🟡", "🔴"], key=f"{chave}_tf", placeholder="Todos")
    props = sorted(pp["proprietario"].dropna().unique()) + sorted(pp["area"].dropna().map(lambda a: f"Área: {a}")
                                                                  .unique())
    prop = f3.multiselect("Proprietário / área", props, key=f"{chave}_tp", placeholder="Todos")
    busca = f4.text_input("Buscar placa", key=f"{chave}_tb", placeholder="ex.: SCM").strip().upper()
    sel = pp.copy()
    if veic:
        sel = sel[sel["veiculo"].isin(veic)]
    if far:
        sel = sel[sel["ocup_efetiva"].map(_farol).isin(far)]
    if prop:
        sel = sel[sel["proprietario"].isin(prop) | sel["area"].map(lambda a: f"Área: {a}").isin(prop)]
    if busca:
        sel = sel[sel["placa"].str.upper().str.contains(busca, regex=False)]
    if sel.empty:
        st.info("Nenhuma placa com esses filtros.")
        return
    vis = _tabela_kpi(sel, {"placa": "Placa", "veiculo": "Veículo"})
    extras = {"Revenda": sel["revenda"], "Proprietário": sel["proprietario"],
              "Aluguel": sel["aluguel"].map(lambda v: "—" if v is None or pd.isna(v) else ("Sim" if v else "Não")),
              "Locadora": sel["locadora"], "Área": sel["area"], "Dias rodados": sel["dias"].map(_n)}
    for i, (k, v) in enumerate(extras.items()):
        vis.insert(3 + i, k, v.fillna("—").values)
    viagens_sel = df[df["placa"].isin(sel["placa"])]
    vis = _com_total(vis, viagens_sel, {"placa": "Placa", "veiculo": "Veículo"},
                     {"Revenda": f"{len(sel)} placas", "Dias rodados": _n(viagens_sel["data"].nunique())})
    st.caption(f"🟢 ocupação média ≥ 85% · 🟡 70–84% · 🔴 abaixo de 70% (ocupação = maior entre caixas e peso) · "
               f"Σ = total das {len(sel)} placas filtradas")
    ui.tabela(vis, baixar="produtividade_por_placa")

    tema.secao("🔎 Detalhe da placa")
    placa = st.selectbox("Placa", sel["placa"].tolist(), key=f"{chave}_placa_det")
    v = df[df["placa"] == placa].sort_values("data")
    r = svc.resumo(v)
    _cards(r, f"{chave}_pl", v)
    graficos.mostrar(graficos.barras(v["data"].dt.strftime("%d/%m") + " · " + v["mapa"],
                                     {"HL": v["hl"].round(1)}, titulo=f"{placa} — HL por viagem", sufixo=" HL"),
                     key=f"g_{chave}_pl")
    ui.tabela(pd.DataFrame({
        "Dia": v["data"].dt.strftime("%d/%m/%Y"), "Mapa": v["mapa"], "Classificação": v["classificacao"],
        "Entregas": v["entregas"].map(_n), "HL": v["hl"].map(lambda x: _n(x, 1)),
        "Caixas": v["caixas"].map(lambda x: _n(x, 1)), "Ocup. caixas": v["ocup_cx"].map(_p),
        "Peso (kg)": v["peso"].map(_n), "Ocup. peso": v["ocup_peso"].map(_p), "KM prev.": v["km_prev"].map(_n),
        "Eficiência": v["eficiencia"].map(_p), "Cidades": v["cidades"].fillna(""),
    }), baixar=f"viagens_{placa}")


def _anual(operacao_id: int, filtro: dict, chave: str) -> None:
    meses = svc.meses_disponiveis(operacao_id)
    anos = sorted({m[:4] for m in meses}, reverse=True)
    ano = st.selectbox("Ano", anos, key=f"{chave}_ano_g")
    df = svc.base(operacao_id, f"{ano}-01-01", f"{ano}-12-31", filtro)
    if df.empty:
        st.info("Sem viagens neste ano.")
        return
    r = svc.resumo(df)
    _cards(r, f"{chave}_an", df)
    m = svc.mensal(df).set_index("mes").reindex([f"{ano}-{i:02d}" for i in range(1, 13)]).reset_index()
    rot = [_MESES[int(x[5:]) - 1] for x in m["mes"]]
    g1, g2 = st.columns(2)
    with g1:
        graficos.mostrar(graficos.barras(rot, {"HL entregue": m["hl"].fillna(0).round(0)},
                                         titulo=f"HL entregue por mês — {ano}", sufixo=" HL"), key=f"g_{chave}_an_hl")
    with g2:
        graficos.mostrar(graficos.linhas(rot, {"Ocupação caixas": m["ocup_cx"].round(1),
                                               "Ocupação peso": m["ocup_peso"].round(1),
                                               "Eficiência": m["eficiencia"].round(1)},
                                         titulo="Ocupação e eficiência por mês", sufixo="%"), key=f"g_{chave}_an_oc")
    com = m[m["viagens"].notna()]
    vis = _tabela_kpi(com, {"mes": "Mês"})
    vis["Mês"] = [f"{_MESES[int(x[5:]) - 1]}/{x[:4]}" for x in com["mes"]]
    vis.insert(2, "Placas", com["placas"].map(_n).values)
    tot = _tabela_kpi(svc._agrupar(df.assign(t="Total do ano"), ["t"]), {"t": "Mês"})
    tot.insert(2, "Placas", [_n(df["placa"].nunique())])
    ui.tabela(pd.concat([vis, tot], ignore_index=True), baixar=f"produtividade_anual_{ano}")

    tema.secao("🚚 Placa × mês", "HL entregue por placa em cada mês do ano.")
    piv = df.pivot_table(index="placa", columns="mes", values="hl", aggfunc="sum", fill_value=0)
    piv = piv.reindex(columns=[c for c in m["mes"] if c in piv.columns])
    piv["Total"] = piv.sum(axis=1)
    piv = piv.sort_values("Total", ascending=False)
    out = piv.apply(lambda c: c.map(_n)).reset_index()
    out.columns = ["Placa"] + [f"{_MESES[int(c[5:]) - 1]}" for c in piv.columns[:-1]] + ["Total"]
    ui.tabela(out, baixar=f"placa_x_mes_{ano}")


def _modais(df: pd.DataFrame, chave: str) -> None:
    base = df[df["veiculo"].isin(list(MODAIS))]
    if base.empty:
        st.info("Sem viagens com tipo de veículo (VUC, Toco, Truck, Carreta) no período.")
        return
    lim = st.slider("Ocupação máxima aceitável no modal ideal (%)", 80, 110, 100, 5, key=f"{chave}_lim",
                    help="A viagem vai para o menor veículo em que caixas E peso cabem até este limite.")
    m = svc.modais(base, lim)
    t = m["total"]
    tema.kpis([
        {"titulo": "Viagens no modal certo", "valor": _p(m["certo"] / t * 100), "icone": "✅",
         "status": "bom" if m["certo"] / t >= .8 else "atencao" if m["certo"] / t >= .65 else "critico",
         "detalhe": f"{m['certo']} de {t} viagens",
         "dados": m["viagens"][m["viagens"]["ajuste"] == "✅ Modal certo"][_COLS_MOD].rename(columns=_ROT_MOD)},
        {"titulo": "Cabiam em veículo menor", "valor": _n(m["menor"]), "icone": "⬇️",
         "status": "atencao" if m["menor"] else "bom", "detalhe": f"{_p(m['menor'] / t * 100)} das viagens · clique",
         "dados": m["viagens"][m["viagens"]["ajuste"] == "⬇️ Cabe em menor"][_COLS_MOD].rename(columns=_ROT_MOD)},
        {"titulo": "Precisavam de veículo maior", "valor": _n(m["maior"]), "icone": "⬆️",
         "status": "critico" if m["maior"] else "bom", "detalhe": f"{_p(m['maior'] / t * 100)} das viagens · clique",
         "dados": m["viagens"][m["viagens"]["ajuste"] == "⬆️ Precisa maior"][_COLS_MOD].rename(columns=_ROT_MOD)},
        {"titulo": "Dias analisados", "valor": _n(base["data"].nunique()), "icone": "📅", "status": "info",
         "detalhe": f"{base['placa'].nunique()} placas"},
    ], key=f"kp_{chave}_mod")

    tema.secao("🔮 Frota sugerida por modal",
               "Quantos veículos de cada tipo o dia precisa, se cada carga fosse no modal ideal. "
               "Frota sugerida = atende 80% dos dias (P80); os dias de pico (P90/máx.) ficam para frete spot.")
    p = m["previsao"]
    sug = pd.DataFrame({
        "Modal": p["modal"],
        "Capacidade": [f"{_n(a)} cx · {_n(b)} kg" for a, b in zip(p["cap_cx"], p["cap_kg"])],
        "Placas usadas hoje": p["placas_atuais"].map(_n),
        "Uso médio/dia hoje": p["atual_media"].map(lambda v: _n(v, 1)),
        "Pico hoje": p["atual_max"].map(_n),
        "Necessidade média/dia": p["ideal_media"].map(lambda v: _n(v, 1)),
        "P80": p["ideal_p80"].map(lambda v: _n(v, 1)), "P90": p["ideal_p90"].map(lambda v: _n(v, 1)),
        "Pico": p["ideal_max"].map(_n),
        "Frota sugerida": [("spot/sob demanda" if s_ == 0 and mx > 0 else _n(s_))
                           for s_, mx in zip(p["sugerido"], p["ideal_max"])],
        "Diferença": [f"{int(s_ - a):+d}" for s_, a in zip(p["sugerido"], p["atual_max"])],
    })
    ui.tabela(sug, baixar="previsao_modais")
    st.caption("Capacidade: mediana real da frota (caixas ÷ % ocupação do relatório) — ou padrão do sistema quando "
               "não há viagens daquele tipo. Diferença = frota sugerida − pico de uso de hoje.")
    for linha in _leitura(m, base):
        st.markdown(f"- {linha}")

    tema.secao("🔀 Modal usado × modal ideal", "Linhas: veículo que rodou · colunas: modal ideal.")
    ui.tabela(m["matriz"].reset_index().rename(columns={"veiculo": "Rodou com"}), baixar="matriz_modais")
    tema.secao("📆 Necessidade média por dia da semana", "Viagens por modal ideal (média do dia da semana).")
    s = m["semana"].copy()
    s.index = [_SEMANA[i] for i in s.index]
    ui.tabela(s.reset_index(names="Dia"), baixar="modais_dia_semana")
    tema.secao("🗺️ Modal ideal por classificação da rota")
    ui.tabela(m["classificacao"].reset_index().rename(columns={"classificacao": "Classificação"}),
              baixar="modais_classificacao")
    with st.expander("📋 Todas as viagens com o modal ideal"):
        ui.tabela(m["viagens"][_COLS_MOD].rename(columns=_ROT_MOD), baixar="viagens_modal_ideal")


_COLS_MOD = ["data", "mapa", "placa", "veiculo", "ideal", "ajuste", "classificacao", "entregas", "caixas", "ocup_cx",
             "peso", "ocup_peso", "km_prev", "hl"]
_ROT_MOD = {"data": "Dia", "mapa": "Mapa", "placa": "Placa", "veiculo": "Rodou com", "ideal": "Modal ideal",
            "ajuste": "Leitura", "classificacao": "Classificação", "entregas": "Entregas", "caixas": "Caixas",
            "ocup_cx": "Ocup. caixas %", "peso": "Peso (kg)", "ocup_peso": "Ocup. peso %", "km_prev": "KM prev.",
            "hl": "HL"}


def _leitura(m: dict, base: pd.DataFrame) -> list[str]:
    """Frases de leitura automática da previsão."""
    out = []
    mat, p = m["matriz"], m["previsao"].set_index("modal")
    for de, para in (("Truck", "Toco"), ("Toco", "VUC"), ("Truck", "VUC")):
        if de in mat.index and para in mat.columns and mat.at[de, para]:
            out.append(f"**{mat.at[de, para]}** viagens de **{de}** caberiam em **{para}** "
                       f"({_p(mat.at[de, para] / max(mat.loc[de].sum(), 1) * 100)} das viagens de {de}).")
    for de, para in (("VUC", "Toco"), ("Toco", "Truck"), ("Truck", "Carreta")):
        if de in mat.index and para in mat.columns and mat.at[de, para]:
            out.append(f"⚠️ **{mat.at[de, para]}** viagens de **{de}** passaram da capacidade — o ideal seria "
                       f"**{para}** (ou dividir a carga).")
    for t, r in p.iterrows():
        dif = r["sugerido"] - r["atual_max"]
        if r["viagens_atual"] or r["viagens_ideal"]:
            if r["sugerido"] == 0:
                out.append(f"**{t}**: uso eventual (pico de {_n(max(r['atual_max'], r['ideal_max']))} no período) "
                           f"→ melhor atender com frete spot do que manter placa fixa.")
            elif dif > 0:
                out.append(f"**{t}**: o dia pede até **{_n(r['sugerido'])}** (P80) e hoje o pico é "
                           f"{_n(r['atual_max'])} → avaliar **+{int(dif)}** {t}.")
            elif dif < 0:
                out.append(f"**{t}**: pico de {_n(r['atual_max'])} em uso, mas {_n(r['sugerido'])} atendem 80% dos "
                           f"dias → espaço para **{int(dif)}** {t} (ou realocar).")
    if not out:
        out.append("A frota atual está aderente à necessidade de modais do período. 👏")
    return out


def ir_relatorios(chave: str) -> None:
    if st.button("📥 Abrir Relatórios", key=f"ir_rel_{chave}", type="primary"):
        st.session_state["nav_corporativo_grupo"] = st.session_state["nav_corporativo_grupo__ultima"] = "📥 Relatórios"
        st.rerun()


def _d(iso: str) -> str:
    return dt.date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def render(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 🚚 Logística › 📦 Produtividade › **Produtividade Entrega**")
    operacao_id = ui.visao_acompanhamento(usuario, operacao_id, "prod_entrega")
    meses = svc.meses_disponiveis(operacao_id)
    if not meses:
        st.info("Ainda não há dados de entrega para esta revenda. Suba o PCD e a 03.02.37 vendas em 📥 Relatórios.")
        ir_relatorios("pe")
        return
    telas = list(_TELAS)
    tela = ui._escolha("pe_tela", telas, telas[0], formatar=_TELAS.get, pills=True)
    filtro = _filtro_notas(operacao_id, "pe")
    if tela == "anual":
        _anual(operacao_id, filtro, "pe")
        return
    per = _periodo(operacao_id, "pe")
    if not per:
        return
    de, ate, rotulo = per
    df = svc.base(operacao_id, de, ate, filtro)
    if df.empty:
        st.info(f"Sem viagens em {rotulo}.")
        return
    df = _filtros_viagem(df, f"pe_{tela}")
    if df.empty:
        st.info("Nenhuma viagem com esses filtros.")
        return
    st.caption(f"📅 {rotulo} · {len(df)} viagens")
    if tela == "geral":
        _visao_geral(df, "pe_g")
    elif tela == "placa":
        _por_placa(df, "pe_p")
    elif tela == "modais":
        _modais(df, "pe_m")
