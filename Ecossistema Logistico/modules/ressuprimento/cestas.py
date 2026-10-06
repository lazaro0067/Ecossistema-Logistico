"""Ressuprimento › Acompanhamento mensal por cesta (META x REAL x TENDÊNCIA)."""
import pandas as pd
import streamlit as st

from core import graficos, tema, tempo, ui
from services import ressuprimento_service as svc

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]
_COR = {"bom": "🟢", "atencao": "🟡", "serio": "🟠", "critico": "🔴", "neutro": "⚪"}


def links_estaticos() -> None:
    from repositories import operacoes_repo

    with st.expander("🔗 Links de visualização direta (somente leitura, sem login)"):
        st.caption("Compartilhe com quem só precisa acompanhar. A página abre direto no acompanhamento da filial.")
        cols = st.columns(4)
        for i, op in enumerate(operacoes_repo.listar(apenas_ativas=True)):
            cols[i % 4].link_button(f"🔗 {op['nome']}", f"?visualizacao=ressuprimento&op={op['id']}", **ui.LARGURA)


def _legivel(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela no formato do relatório: HL inteiro com ponto de milhar (1.307) e '—' quando não há meta."""
    if df.empty:
        return pd.DataFrame(columns=["", "Indicador", "Meta (HL)", "Real (HL)", "Tendência (HL)", "Ating. real",
                                     "Ating. tendência", "Pendência (HL)"])
    tem_meta = df["meta"] > 0
    num = ui.numero  # ponto de milhar a partir de mil: 5.025 · 189.312
    real = df["real"].map(num)
    return pd.DataFrame({
        "": df["ating_tend"].map(lambda p: _COR[tema.status_atingimento(p if pd.notna(p) else None)]),
        "Indicador": df["indicador"],
        "Meta (HL)": [num(m) if t else "—" for m, t in zip(df["meta"], tem_meta)],
        "Real (HL)": real,
        "Tendência (HL)": df["tendencia"].map(num),
        "Ating. real": [ui.pct(a) if t and pd.notna(a) else "—" for a, t in zip(df["ating_real"], tem_meta)],
        "Ating. tendência": [float(a) if t and pd.notna(a) else None for a, t in zip(df["ating_tend"], tem_meta)],
        "Pendência (HL)": [num(p) if t else "—" for p, t in zip(df["pendencia"], tem_meta)],
    }).reset_index(drop=True)


def acompanhamento(operacao_id: int, chave: str = "ces", com_graficos: bool = True) -> None:
    hoje = tempo.hoje()
    c1, c2 = st.columns([1, 3])
    ano = c1.number_input("Ano", min_value=2024, max_value=2035, value=hoje.year, key=f"{chave}_ano")
    meses = c2.multiselect("Meses (vazio = ano inteiro)", list(range(1, 13)), default=[hoje.month],
                           format_func=lambda m: MESES[m - 1], key=f"{chave}_meses")
    df = svc.acompanhamento(operacao_id, int(ano), meses)
    tot = df[df["cesta"] == "TOTAL"].iloc[0]
    det = _legivel(df[df["cesta"] != "TOTAL"])
    neg = _legivel(df[(df["cesta"] != "TOTAL") & (df["meta"] > 0) & (df["pendencia"] < 0)].sort_values("pendencia"))
    preench, periodo = df.attrs.get("dias_preenchidos", 0), df.attrs.get("dias_periodo", 0)
    hl = lambda v: f"{ui.numero(v)} HL"  # noqa: E731 — número inteiro como no relatório (1.307 = mil trezentos e sete)
    tema.kpis([
        {"titulo": "Total Cerveja + Nab — real", "valor": hl(tot["real"]), "icone": "🍺",
         "status": "info", "detalhe": f"{preench} dia(s) com dado no período", "dados": det},
        {"titulo": "Meta do período", "valor": hl(tot["meta"]) if tot["meta"] else "Sem meta",
         "icone": "🎯", "status": "info" if tot["meta"] else "neutro", "dados": det},
        {"titulo": "Tendência de fechamento", "valor": hl(tot["tendencia"]), "icone": "🔮",
         "detalhe": f"{ui.pct(tot['ating_tend'])} da meta" if tot["meta"] else "defina as metas",
         "status": tema.status_atingimento(tot["ating_tend"] if tot["meta"] else None), "dados": det},
        {"titulo": "Pendência (real − meta)", "valor": hl(tot["pendencia"]) if tot["meta"] else "—", "icone": "⚖️",
         "status": ("bom" if tot["pendencia"] >= 0 else "critico") if tot["meta"] else "neutro",
         "detalhe": "cestas abaixo da meta: clique" if len(neg) else "", "dados": neg},
    ], key=f"kp_{chave}")
    ui.tabela(_legivel(df), column_config={
        "": st.column_config.TextColumn("", width="small"),
        "Ating. tendência": st.column_config.ProgressColumn("Ating. tendência", format="%.0f%%", min_value=0,
                                                             max_value=120)})
    st.caption("🟢 tendência ≥ 100% da meta · 🟡 90–99% · 🟠 75–89% · 🔴 abaixo de 75%")
    ui.downloads(df.drop(columns=["cesta"]), f"acompanhamento_{ano}", key=f"dl_{chave}")

    if not com_graficos:
        return
    com_meta = df[(df["meta"] > 0) & (df["cesta"] != "TOTAL")].sort_values("ating_tend")
    g1, g2 = st.columns(2)
    with g1:
        if not com_meta.empty:
            cores = [tema.STATUS[tema.status_atingimento(p)][0] for p in com_meta["ating_tend"]]
            graficos.mostrar(graficos.barras_h(com_meta["indicador"], com_meta["ating_tend"].fillna(0), cores=cores,
                                               sufixo="%", titulo="Tendência de atingimento por cesta"),
                             key=f"g_{chave}_ating", detalhe=(det, "Indicador"), titulo="Cesta")
        else:
            st.info("Cadastre as metas em **🎯 Metas Mensais** para ver o atingimento.")
    with g2:
        if len(meses) == 1:
            mes_ano = f"{int(ano)}-{meses[0]:02d}"
            opcoes = df[df["cesta"] != "TOTAL"]["cesta"].tolist()
            if opcoes:
                cesta = st.selectbox("Evolução da cesta", opcoes, format_func=svc.nome_cesta, key=f"{chave}_cesta")
                evo = svc.evolucao_diaria(operacao_id, mes_ano, cesta)
                if not evo.empty:
                    graficos.mostrar(graficos.linhas(evo["data"], {"Real acumulado": evo["real_acum"],
                                                                   "Meta proporcional": evo["meta_acum"]},
                                                     titulo=f"{svc.nome_cesta(cesta)} — acumulado no mês", sufixo=" HL",
                                                     tracejadas=("Meta proporcional",)), key=f"g_{chave}_evo")


def render(usuario: dict, operacao_id: int) -> None:
    links_estaticos()
    acompanhamento(operacao_id)
