"""Puxada › TMV / TMA & Viagens — indicadores do App Carreteiro.

TMV: do "Iniciar viagem" ao "Finalizar viagem".
TMA: da "Chegada na revenda" até o próximo "Iniciar viagem" da mesma placa
     (com GPS: conta quantas paradas foram confirmadas dentro do raio da revenda).
"""
import pandas as pd
import streamlit as st

from core import graficos, tema, tempo, ui
from services import carreteiro_service as svc

F = svc.formatar_duracao
TRECHOS = [("ida_h", "Ida até a cervejaria"), ("espera_h", "Espera p/ carregar"), ("carregamento_h", "Carregamento"),
           ("liberacao_h", "Liberação (NF → saída)"), ("volta_h", "Retorno à revenda"), ("descarga_h", "Na revenda até finalizar")]


def _media(s: pd.Series) -> float | None:
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[s >= 0]
    return float(s.mean()) if not s.empty else None


def _pct_prazo(df: pd.DataFrame) -> float | None:
    s = pd.to_numeric(df["apresentou_no_prazo"], errors="coerce").dropna()
    return float(s.mean() * 100) if not s.empty else None


def _status_prazo(p: float | None) -> str:
    if p is None:
        return "neutro"
    return "bom" if p >= 90 else "atencao" if p >= 75 else "serio" if p >= 60 else "critico"


def _agrupado(df: pd.DataFrame, chave: str) -> pd.DataFrame:
    linhas = []
    for valor, g in df.groupby(chave):
        fin = g[g["status"] == "Finalizada"]
        linhas.append({
            chave: valor, "viagens": len(g), "finalizadas": len(fin),
            "tmv_h": _media(fin["tmv_h"]), "tma_h": _media(g["tma_h"]),
            "espera_h": _media(g["espera_h"]), "na_cervejaria_h": _media(g["na_cervejaria_h"]),
            "no_prazo_pct": _pct_prazo(g),
            "nfs": int(g["qtd_nfs"].sum()),
        })
    return pd.DataFrame(linhas).sort_values("viagens", ascending=False) if linhas else pd.DataFrame()


def _tabela_grupo(tab: pd.DataFrame, chave: str, rotulo: str, key: str) -> None:
    if tab.empty:
        return
    vis = tab.copy()
    for c in ("tmv_h", "tma_h", "espera_h", "na_cervejaria_h"):
        vis[c] = vis[c].map(F)
    vis["no_prazo_pct"] = vis["no_prazo_pct"].map(lambda p: "—" if p is None or pd.isna(p) else ui.pct(p, 0))
    ui.tabela(vis, column_config={
        chave: rotulo, "viagens": "Viagens", "finalizadas": "Finalizadas", "tmv_h": "TMV médio",
        "tma_h": "TMA médio", "espera_h": "Espera p/ carregar", "na_cervejaria_h": "Tempo na cervejaria",
        "no_prazo_pct": "Apresentação no prazo", "nfs": "NFs"})
    ui.downloads(tab, f"viagens_por_{chave}", key=key)


def render(usuario: dict, operacao_id: int) -> None:
    c1, c2, c3, c4 = st.columns([1, 1, 1.5, 1.5])
    de = c1.date_input("De", value=tempo.hoje().replace(day=1), format="DD/MM/YYYY", key="tmv_de")
    ate = c2.date_input("Até", value=tempo.hoje(), format="DD/MM/YYYY", key="tmv_ate")
    df = svc.indicadores(operacao_id, de.isoformat() if de else None, ate.isoformat() if ate else None)
    if df.empty:
        st.info("Nenhuma viagem do App Carreteiro no período. Os motoristas lançam as viagens pelo celular "
                "(crie os acessos em **🚛 App Carreteiro › 🔑 Acessos dos motoristas**).")
        return
    mots = c3.multiselect("Motoristas", sorted(df["motorista"].unique()), key="tmv_mot")
    pls = c4.multiselect("Placas", sorted(df["placa"].unique()), key="tmv_placa")
    if mots:
        df = df[df["motorista"].isin(mots)]
    if pls:
        df = df[df["placa"].isin(pls)]
    if df.empty:
        st.info("Nenhuma viagem com esses filtros.")
        return

    fin = df[df["status"] == "Finalizada"]
    tma_validos = df["tma_h"].dropna()
    tma_gps = int(df["tma_confirmado_gps"].sum())
    prazo = _pct_prazo(df)
    tema.kpis([
        {"titulo": "Viagens", "valor": len(df), "icone": "🚛", "status": "info",
         "detalhe": f"{len(fin)} finalizadas · {int((df['status'] == 'Em viagem').sum())} em andamento"},
        {"titulo": "TMV — tempo médio de viagem", "valor": F(_media(fin["tmv_h"])), "icone": "⏱️", "status": "info",
         "detalhe": f"início → fim · {len(fin)} viagens"},
        {"titulo": "TMA — parada na revenda", "valor": F(_media(df["tma_h"])), "icone": "🅿️", "status": "info",
         "detalhe": f"chegada → próxima saída · {len(tma_validos)} paradas"
                    + (f" · {tma_gps} confirmadas por GPS" if tma_gps else "")},
        {"titulo": "Apresentação no prazo", "valor": ui.pct(prazo, 0) if prazo is not None else "—", "icone": "🙋",
         "status": _status_prazo(prazo), "detalhe": "dentro do horário agendado"},
        {"titulo": "Espera p/ carregar", "valor": F(_media(df["espera_h"])), "icone": "🏭", "status": "info",
         "detalhe": "apresentado → chamado"},
        {"titulo": "Tempo na cervejaria", "valor": F(_media(df["na_cervejaria_h"])), "icone": "📦", "status": "info",
         "detalhe": "apresentado → saída"},
    ])

    abas = st.tabs(["📊 Visão geral", "👤 Por motorista", "🚛 Por placa", "📋 Viagens"])
    with abas[0]:
        tema.secao("Onde o tempo da viagem vai", "Média de cada trecho, em horas.")
        medias = [(_media(df[c]) or 0) for c, _ in TRECHOS]
        graficos.mostrar(graficos.barras_h([r for _, r in TRECHOS], medias, casas=1, sufixo=" h",
                                           textos=[F(m) for m in medias]), key="tmv_trechos")
        dia = df.groupby("data").agg(viagens=("id", "count"), tmv=("tmv_h", "mean")).reset_index()
        g1, g2 = st.columns(2)
        with g1:
            graficos.mostrar(graficos.barras([d.strftime("%d/%m") for d in dia["data"]], {"Viagens": dia["viagens"]},
                                             titulo="Viagens por dia"), key="tmv_dia")
        with g2:
            tma_placa = df.dropna(subset=["tma_h"]).groupby("placa")["tma_h"].mean().sort_values(ascending=False)
            if not tma_placa.empty:
                graficos.mostrar(graficos.barras_h(tma_placa.index, tma_placa.values, titulo="TMA médio por placa",
                                                   textos=[F(v) for v in tma_placa.values], casas=1),
                                 key="tmv_tma_placa")
            else:
                st.info("TMA aparece quando a mesma placa chega na revenda e inicia a viagem seguinte.")
        if df["chegada_gps"].ne("Sem GPS").any():
            tema.secao("Conferência por GPS (chegada na revenda)")
            cont = df.dropna(subset=["ts_chegada_revenda"])["chegada_gps"].value_counts()
            cores = {"Dentro do raio": tema.STATUS["bom"][0], "Fora do raio": tema.STATUS["serio"][0],
                     "Sem GPS": tema.STATUS["neutro"][0]}
            graficos.mostrar(graficos.barras_h(cont.index, cont.values, cores=[cores[i] for i in cont.index]),
                             key="tmv_gps")

    with abas[1]:
        tab = _agrupado(df, "motorista")
        g1, g2 = st.columns(2)
        with g1:
            graficos.mostrar(graficos.barras_h(tab["motorista"], tab["viagens"], titulo="Viagens por motorista"),
                             key="tmv_mot_v")
        with g2:
            t = tab.dropna(subset=["tmv_h"]).sort_values("tmv_h", ascending=False)
            if not t.empty:
                graficos.mostrar(graficos.barras_h(t["motorista"], t["tmv_h"], titulo="TMV médio por motorista",
                                                   textos=[F(v) for v in t["tmv_h"]], casas=1), key="tmv_mot_tmv")
        _tabela_grupo(tab, "motorista", "Motorista", "dl_tmv_mot")

    with abas[2]:
        tab = _agrupado(df, "placa")
        g1, g2 = st.columns(2)
        with g1:
            graficos.mostrar(graficos.barras_h(tab["placa"], tab["viagens"], titulo="Viagens por placa"),
                             key="tmv_pl_v")
        with g2:
            t = tab.dropna(subset=["tmv_h"]).sort_values("tmv_h", ascending=False)
            if not t.empty:
                graficos.mostrar(graficos.barras_h(t["placa"], t["tmv_h"], titulo="TMV médio por placa",
                                                   textos=[F(v) for v in t["tmv_h"]], casas=1), key="tmv_pl_tmv")
        _tabela_grupo(tab, "placa", "Placa", "dl_tmv_pl")

    with abas[3]:
        vis = df[["id", "status", "motorista", "placa", "numero_pedido", "destino", "ts_inicio", "ts_fim", "tmv_h",
                  "espera_h", "na_cervejaria_h", "tma_h", "chegada_gps", "apresentou_no_prazo", "atraso_min",
                  "qtd_nfs"]].copy()
        for c in ("ts_inicio", "ts_fim"):
            vis[c] = vis[c].dt.strftime("%d/%m/%Y %H:%M").fillna("")
        for c in ("tmv_h", "espera_h", "na_cervejaria_h", "tma_h"):
            vis[c] = vis[c].map(F)
        vis["apresentou_no_prazo"] = vis["apresentou_no_prazo"].map(
            lambda x: "" if pd.isna(x) else ("✅ No prazo" if int(x) else "⚠️ Fora"))
        vis["atraso_min"] = vis["atraso_min"].map(lambda x: "" if pd.isna(x) else F(x / 60) if x > 0 else "—")
        ui.tabela(vis, column_config={
            "id": "Nº", "status": "Status", "motorista": "Motorista", "placa": "Placa", "numero_pedido": "Pedido",
            "destino": "Destino", "ts_inicio": "Início", "ts_fim": "Fim", "tmv_h": "TMV",
            "espera_h": "Espera", "na_cervejaria_h": "Na cervejaria", "tma_h": "TMA (parada seguinte)",
            "chegada_gps": "GPS chegada", "apresentou_no_prazo": "Apresentação", "atraso_min": "Atraso",
            "qtd_nfs": "NFs"})
        exp = df.drop(columns=["operacao_id", "motorista_id"], errors="ignore")
        ui.downloads(exp, "tmv_tma_viagens", key="dl_tmv_viagens")
