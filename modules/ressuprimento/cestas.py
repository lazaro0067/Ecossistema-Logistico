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


def acompanhamento(operacao_id: int, chave: str = "ces", com_graficos: bool = True) -> None:
    hoje = tempo.hoje()
    c1, c2 = st.columns([1, 3])
    ano = c1.number_input("Ano", min_value=2024, max_value=2035, value=hoje.year, key=f"{chave}_ano")
    meses = c2.multiselect("Meses (vazio = ano inteiro)", list(range(1, 13)), default=[hoje.month],
                           format_func=lambda m: MESES[m - 1], key=f"{chave}_meses")
    df = svc.acompanhamento(operacao_id, int(ano), meses)
    tot = df[df["cesta"] == "TOTAL"].iloc[0]
    preench, periodo = df.attrs.get("dias_preenchidos", 0), df.attrs.get("dias_periodo", 0)
    tema.kpis([
        {"titulo": "Total Cerveja + Nab — real", "valor": f"{ui.compacto(tot['real'])} HL", "icone": "🍺",
         "status": "info", "detalhe": f"{preench} de {periodo} dia(s) com dado"},
        {"titulo": "Meta do período", "valor": f"{ui.compacto(tot['meta'])} HL" if tot["meta"] else "Sem meta",
         "icone": "🎯", "status": "info" if tot["meta"] else "neutro"},
        {"titulo": "Tendência de fechamento", "valor": f"{ui.compacto(tot['tendencia'])} HL", "icone": "🔮",
         "detalhe": f"{ui.pct(tot['ating_tend'])} da meta" if tot["meta"] else "defina as metas",
         "status": tema.status_atingimento(tot["ating_tend"] if tot["meta"] else None)},
        {"titulo": "Pendência (real − meta)", "valor": f"{ui.compacto(tot['pendencia'])} HL", "icone": "⚖️",
         "status": ("bom" if tot["pendencia"] >= 0 else "critico") if tot["meta"] else "neutro"},
    ])
    tab = df.assign(
        status=df["ating_tend"].map(lambda p: _COR[tema.status_atingimento(p if pd.notna(p) else None)]),
    )[["status", "indicador", "meta", "real", "tendencia", "ating_real", "ating_tend", "pendencia"]]
    ui.tabela(tab, column_config={
        "status": st.column_config.TextColumn("", width="small"), "indicador": "Indicador",
        "meta": st.column_config.NumberColumn("Meta (HL)", format="%.0f"),
        "real": st.column_config.NumberColumn("Real (HL)", format="%.0f"),
        "tendencia": st.column_config.NumberColumn("Tendência (HL)", format="%.0f"),
        "ating_real": st.column_config.NumberColumn("Ating. real", format="%.1f%%"),
        "ating_tend": st.column_config.ProgressColumn("Ating. tendência", format="%.0f%%", min_value=0, max_value=120),
        "pendencia": st.column_config.NumberColumn("Pendência (HL)", format="%.0f"),
    })
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
                             key=f"g_{chave}_ating")
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
