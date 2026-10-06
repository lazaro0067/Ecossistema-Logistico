"""Puxada › Frota própria › 👤 Disponibilidade de motoristas.

Interjornada de 11 h contada da última etapa "Finalizar viagem" do App Carreteiro, viagem em
andamento e férias cadastradas aqui mesmo.
"""
import html

import pandas as pd
import streamlit as st

from config.settings import INTERJORNADA_H
from core import tema, tempo, ui
from modules.componentes.cadastro import Campo, tela
from repositories import logistica_repo
from repositories import motoristas_repo as repo
from services import disp_motoristas_service as svc

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_CSS = """
<style>
.dm-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap:.7rem; margin:.4rem 0 1rem; }
.dm-card { background:#fff; border:1px solid #dfe5ee; border-left:5px solid var(--c); border-radius:14px;
    padding:.7rem .85rem; box-shadow:0 1px 2px rgba(11,31,58,.05); }
.dm-top { display:flex; justify-content:space-between; gap:.4rem; align-items:center; }
.dm-top b { color:#0B1F3A; font-size:.98rem; }
.dm-st { font-size:.74rem; font-weight:800; padding:.12rem .5rem; border-radius:999px; white-space:nowrap;
    color:var(--c); background: color-mix(in srgb, var(--c) 12%, white); }
.dm-det { font-size:.8rem; color:#3d3c39; margin-top:.3rem; }
.dm-bar { height:6px; background:#eef0f3; border-radius:99px; overflow:hidden; margin-top:.45rem; }
.dm-bar i { display:block; height:100%; background:var(--c); }
.dm-falta { font-size:.76rem; color:var(--c); font-weight:700; margin-top:.25rem; }
.dm-chip { display:inline-block; padding:.12rem .55rem; border-radius:999px; font-weight:700; font-size:.78rem;
    color: var(--c); background: color-mix(in srgb, var(--c) 12%, white); border:1px solid color-mix(in srgb, var(--c) 40%, white); }
.dm-obs { font-size:.73rem; color:#6b6a65; margin-top:.15rem; }
</style>
"""


def _rot(d) -> str:
    return f"{DIAS_SEMANA[d.weekday()]} {d:%d/%m}"


def _e(v) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))


def _falta(livre) -> str:
    if livre is None or (isinstance(livre, float) and pd.isna(livre)):
        return ""
    seg = (pd.Timestamp(livre).to_pydatetime() - tempo.agora()).total_seconds()
    if seg <= 0:
        return ""
    h, m = int(seg // 3600), int(seg % 3600 // 60)
    return f"faltam {h}h{m:02d}" if h < 48 else f"faltam {h // 24} dias"


def _cards(df: pd.DataFrame) -> None:
    ordem = {"Disponível": 0, "Interjornada": 1, "Em viagem": 2, "Férias": 3}
    itens = []
    for r in sorted(df.to_dict("records"), key=lambda r: (ordem.get(r["status"], 9), r["nome"])):
        cor = svc.CORES.get(r["status"], "#898781")
        barra = ""
        if r["status"] == "Interjornada" and r.get("livre_em") is not None and not pd.isna(r["livre_em"]):
            livre = pd.Timestamp(r["livre_em"]).to_pydatetime()
            pct = max(0.0, min(100.0, 100 - (livre - tempo.agora()).total_seconds() / (INTERJORNADA_H * 36)))
            barra = (f'<div class="dm-bar"><i style="width:{pct:.0f}%"></i></div>'
                     f'<div class="dm-falta">⏳ {_e(_falta(r["livre_em"]))}</div>')
        itens.append(f'<div class="dm-card" style="--c:{cor}"><div class="dm-top"><b>👤 {_e(r["nome"])}</b>'
                     f'<span class="dm-st">{svc.ICONES.get(r["status"], "")} {_e(r["status"])}</span></div>'
                     f'<div class="dm-det">{_e(r["detalhe"]) or "&nbsp;"}</div>{barra}</div>')
    st.markdown(_CSS + f'<div class="dm-grid">{"".join(itens)}</div>', unsafe_allow_html=True)


def _grade_html(g: pd.DataFrame) -> None:
    ds = svc.dias()
    cab = "".join(f"<th>{_e(_rot(d))}{' · hoje' if i == 0 else ''}</th>" for i, d in enumerate(ds))
    linhas = []
    for nome, grupo in g.groupby("nome", sort=True):
        cel = []
        for d in ds:
            r = grupo[grupo["data"] == d].iloc[0]
            cor = svc.CORES.get(r["status"], "#898781")
            cel.append(f'<td><span class="dm-chip" style="--c:{cor}">{svc.ICONES.get(r["status"], "")} '
                       f'{_e(r["status"])}</span><div class="dm-obs">{_e(r["detalhe"])}</div></td>')
        linhas.append(f"<tr><td><b>{_e(nome)}</b></td>{''.join(cel)}</tr>")
    st.markdown(_CSS + f'<div class="eco-tab"><table><thead><tr><th>Motorista</th>{cab}</tr></thead>'
                f'<tbody>{"".join(linhas)}</tbody></table></div>', unsafe_allow_html=True)


def _vis(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Motorista": df["nome"],
                         "Situação": [f"{svc.ICONES.get(s, '')} {s}" for s in df["status"]],
                         "Detalhe": df["detalhe"]})


def _ferias(usuario: dict, operacao_id: int) -> None:
    mots = logistica_repo.motoristas_df(operacao_id)
    nomes = {int(r["id"]): r["nome"] for r in mots.to_dict("records")} if not mots.empty else {}
    if not nomes:
        st.info("Cadastre os motoristas em **⚙️ Cadastros › 👤 Motoristas**.")
        return
    df = repo.ferias_df(operacao_id)
    if not df.empty:
        df["situacao"] = [svc.situacao_ferias(a, b) for a, b in zip(df["inicio"], df["fim"])]
        df["dias"] = [(pd.to_datetime(b) - pd.to_datetime(a)).days + 1 for a, b in zip(df["inicio"], df["fim"])]
    tela(chave=f"fer_{operacao_id}", titulo="Férias dos motoristas", icone="🏖️", df=df, por_linha=4,
         descricao="No período cadastrado o motorista aparece de férias na disponibilidade e no lançamento de pedidos.",
         campos=[Campo("motorista_id", "Motorista", "opcoes", True, nomes),
                 Campo("inicio", "Início", "data", True), Campo("fim", "Fim (último dia)", "data", True),
                 Campo("observacao", "Observação")],
         colunas_extras=[("dias", "Dias"), ("situacao", "Situação")],
         rotulo_registro=lambda r: f"{nomes.get(int(r['motorista_id']), '?')} · "
                                   f"{pd.to_datetime(r['inicio']):%d/%m/%Y} a {pd.to_datetime(r['fim']):%d/%m/%Y}",
         salvar=lambda fid, d: svc.salvar_ferias(operacao_id, fid, d.get("motorista_id"), d.get("inicio"),
                                                 d.get("fim"), d.get("observacao") or "", usuario.get("nome") or ""),
         excluir=repo.excluir_ferias, aviso_vazio="Nenhum período de férias cadastrado.")


def render(usuario: dict, operacao_id: int) -> None:
    if ui.somente_leitura(operacao_id):
        st.info("A disponibilidade de motoristas é por filial. Escolha uma filial no menu.")
        return
    partes = {"agora": "👤 Agora", "dias": "🗓️ Próximos dias", "ferias": "🏖️ Férias"}
    parte = ui._escolha("dm_parte", list(partes), "agora", formatar=partes.get, pills=True)
    if parte == "ferias":
        _ferias(usuario, operacao_id)
        return
    g = svc.grade(operacao_id)
    if g.empty:
        st.info("Cadastre os motoristas em **⚙️ Cadastros › 👤 Motoristas**.")
        return
    total = g["id"].nunique()
    cards = []
    for i, d in enumerate(svc.dias()):
        dia = g[g["data"] == d]
        disp = dia[dia["status"] == "Disponível"]
        pct = len(disp) / total * 100 if total else 0
        resumo = " · ".join(f"{svc.ICONES[s]} {int((dia['status'] == s).sum())}"
                            for s in ("Interjornada", "Em viagem", "Férias") if (dia["status"] == s).any())
        cards.append({"titulo": ("Agora · " if i == 0 else "") + _rot(d), "valor": f"{len(disp)} de {total}",
                      "icone": "👤", "detalhe": resumo or "motoristas disponíveis",
                      "status": "bom" if pct >= 50 else "atencao" if pct > 0 else "critico", "dados": _vis(dia)})
    tema.kpis(cards, key="kp_dm")
    if parte == "agora":
        tema.secao(f"Motoristas agora · {tempo.agora():%d/%m %H:%M}",
                   f"Interjornada de {INTERJORNADA_H} h contada da etapa “Finalizar viagem” do App Carreteiro.")
        _cards(svc.agora(operacao_id))
    else:
        tema.secao("Disponibilidade nos próximos dias",
                   "Hoje = agora; nos outros dias, a situação no começo do dia (com a hora em que a interjornada acaba).")
        _grade_html(g)
    ui.downloads(g.assign(data=g["data"].map(lambda d: d.strftime("%d/%m/%Y")))
                 [["nome", "data", "status", "detalhe"]], "disponibilidade_motoristas", key="dl_dm")
