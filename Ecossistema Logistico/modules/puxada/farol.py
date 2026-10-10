"""Puxada › Frota própria › 🚦 Farol de produtividade.

Mostra, para cada atividade da viagem, quantas ocorrências ficaram dentro do tempo e lista as que
ficaram fora (motorista, placa, pedido, real × meta e excesso).
"""
import datetime as dt
import html

import pandas as pd
import streamlit as st

from config.settings import FAROL_FAIXAS
from core import tema, tempo, ui
from services import farol_service as svc

_CSS = """
<style>
.fr-geral { display:flex; align-items:center; gap:1rem; background:#fff; border:1px solid #dfe5ee;
    border-left:6px solid var(--c); border-radius:14px; padding:.8rem 1rem; margin:.3rem 0 .9rem; }
.fr-geral .big { font-size:2.1rem; font-weight:900; color:var(--c); line-height:1; }
.fr-geral .tx b { color:#0B1F3A; font-size:1.02rem; } .fr-geral .tx div { color:#52514e; font-size:.84rem; }
.fr-leg { font-size:.78rem; color:#6b6a65; margin:-.4rem 0 .6rem; }
</style>
"""
_COR = {"bom": "#146c43", "atencao": "#b7791f", "critico": "#a32025", "neutro": "#77766f"}


def _periodo() -> tuple[dt.date, dt.date]:
    hoje = tempo.hoje()
    opcoes = {"7": "Últimos 7 dias", "30": "Últimos 30 dias", "mes": "Mês atual", "per": "📅 Escolher período"}
    esc = ui._escolha("fr_periodo", list(opcoes), "7", formatar=opcoes.get, pills=True)
    if esc == "7":
        return hoje - dt.timedelta(days=6), hoje
    if esc == "30":
        return hoje - dt.timedelta(days=29), hoje
    if esc == "mes":
        return hoje.replace(day=1), hoje
    c1, c2, _ = st.columns([1, 1, 2])
    de = c1.date_input("De", value=hoje - dt.timedelta(days=13), format="DD/MM/YYYY", key="fr_de")
    ate = c2.date_input("Até", value=hoje, format="DD/MM/YYYY", key="fr_ate")
    return (de, ate) if de <= ate else (ate, de)


def render(usuario: dict, operacao_id: int) -> None:
    operacao_id = ui.visao_acompanhamento(usuario, operacao_id, "farol")
    de, ate = _periodo()
    ativs = svc.atividades(operacao_id, de, ate)
    g = svc.geral(ativs)
    icone, status = svc.farol(g["pct"])
    cor = _COR[status]
    pct_txt = f"{g['pct']:.0f}%" if g["pct"] is not None else "—"
    st.markdown(_CSS + f'<div class="fr-geral" style="--c:{cor}"><div class="big">{icone} {pct_txt}</div>'
                f'<div class="tx"><b>Produtividade geral · {de:%d/%m} a {ate:%d/%m/%Y}</b>'
                f'<div>{g["ok"]} de {g["total"]} atividades no tempo · <b>{g["fora"]}</b> fora do tempo</div></div></div>'
                f'<div class="fr-leg">🟢 ≥ {FAROL_FAIXAS[0]}% no tempo · 🟡 ≥ {FAROL_FAIXAS[1]}% · 🔴 abaixo · '
                f'⚪ sem registros no período. Clique no card para ver o que ficou fora do tempo.</div>',
                unsafe_allow_html=True)
    cards = []
    for a in ativs:
        ic, stt = svc.farol(a["pct"])
        fora = a["itens"]
        fora = fora[~fora["_ok"].astype(bool)][svc.COLUNAS[:-1]] if not fora.empty else None
        cards.append({"titulo": f"{a['icone']} {a['nome']}",
                      "valor": f"{ic} {a['pct']:.0f}%" if a["pct"] is not None else "⚪ —",
                      "detalhe": (f"{a['ok']} de {a['total']} no tempo · {a['fora']} fora" if a["total"]
                                  else "sem registros") ,
                      "status": stt, "dados": fora if fora is not None and not fora.empty else None})
    tema.kpis(cards, key="kp_farol")

    tema.secao("❌ Fora do tempo", "Todas as ocorrências que passaram da meta, da mais recente para a mais antiga.")
    ff = svc.fora_do_tempo(ativs)
    if ff.empty:
        st.success("Nenhuma atividade fora do tempo no período. 👏")
    else:
        nomes = ["Todas"] + sorted(ff["Atividade"].unique().tolist())
        filtro = st.selectbox("Atividade", nomes, key="fr_filtro")
        ui.tabela(ff if filtro == "Todas" else ff[ff["Atividade"] == filtro], baixar="farol_fora_do_tempo")

    tema.secao("👤 Por motorista", "Percentual no tempo de cada motorista em cada atividade (pior primeiro).")
    pm = svc.por_motorista(ativs)
    if pm.empty:
        st.info("Sem viagens no período.")
    else:
        ui.tabela(pm, baixar="farol_por_motorista")

    with st.expander("📏 Metas usadas"):
        st.markdown("\n".join(f"- **{a['icone']} {html.escape(a['nome'])}** — {html.escape(a['regra'])}"
                              for a in ativs))
        todas = pd.concat([a["itens"].assign(Atividade=f"{a['icone']} {a['nome']}") for a in ativs
                           if not a["itens"].empty], ignore_index=True) if any(a["total"] for a in ativs) else None
        if todas is not None:
            ui.downloads(todas[["Atividade", *svc.COLUNAS]], "farol_todas_atividades", key="dl_farol_todas")
