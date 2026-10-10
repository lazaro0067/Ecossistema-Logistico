"""Portal Comercial com cara de aplicativo (link público por revenda).

Topo com a foto da carreta e a revenda, chips de status (Stock Out / Low / Ideal / Over) para filtrar,
busca, e a lista de produtos em cartões: estoque, trânsito, puxadas D0/D1/D2 e barra de cobertura.
A tabela e o quadro para o grupo continuam disponíveis.
"""
import html

import streamlit as st

from core import ui
from modules.componentes import estoque_dia
from services import armazem_service

COR = {"Stock Out": "#e5484d", "Stock Low": "#f5a524", "Stock Ideal": "#22a06b", "Stock Over": "#2f6fe0"}
ROTULO = {"Stock Out": "Sem estoque", "Stock Low": "Estoque baixo", "Stock Ideal": "Ideal", "Stock Over": "Acima"}
ICONE = {"Stock Out": "🔴", "Stock Low": "🟡", "Stock Ideal": "🟢", "Stock Over": "🔵"}
POR_PAGINA = 60

_CSS = """
<style>
.stApp { background: #eef2f8 !important; }
.block-container { max-width: 1100px; padding-top: 1rem !important; }
header[data-testid="stHeader"] { background: transparent; }
.pa-hero { position: relative; border-radius: 26px; overflow: hidden; min-height: 190px; color: #fff;
    background: linear-gradient(160deg, #0b2563, #1d47a6); background-size: cover; background-position: center 60%;
    box-shadow: 0 18px 40px -26px rgba(11,37,99,.9); margin-bottom: 1rem; }
.pa-hero:before { content: ""; position: absolute; inset: 0;
    background: linear-gradient(180deg, rgba(5,17,48,.25) 0%, rgba(5,17,48,.85) 100%); }
.pa-hero .in { position: relative; padding: 1.3rem 1.4rem; display: flex; flex-direction: column; justify-content: flex-end;
    min-height: 190px; }
.pa-hero .tag { display: inline-block; font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
    opacity: .85; }
.pa-hero h1 { color: #fff !important; font-size: 1.9rem; font-weight: 800; margin: .1rem 0 .2rem; padding: 0; line-height: 1.1; }
.pa-hero .sub { font-size: .9rem; opacity: .9; }
.pa-hero .chips { margin-top: .6rem; display: flex; gap: .4rem; flex-wrap: wrap; }
.pa-hero .chips span { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.3); border-radius: 999px;
    padding: .2rem .65rem; font-size: .78rem; font-weight: 700; }
.pa-resumo { display: grid; grid-template-columns: repeat(4, 1fr); gap: .6rem; margin: .2rem 0 .8rem; }
@media (max-width: 640px) { .pa-resumo { grid-template-columns: repeat(2, 1fr); } }
.pa-res { background: #fff; border-radius: 18px; padding: .75rem .9rem; box-shadow: 0 8px 20px -18px rgba(11,37,99,.7);
    border-top: 5px solid var(--c); }
.pa-res b { display: block; font-size: 1.6rem; font-weight: 900; color: #0b2563; line-height: 1.1; }
.pa-res span { font-size: .78rem; color: #5b6576; font-weight: 700; }
.pa-res i { font-style: normal; font-size: .72rem; color: var(--c); font-weight: 800; }
.st-key-pa_status [data-testid="stButtonGroup"] button { border-radius: 999px !important; font-weight: 700;
    background: #fff; border: 1.5px solid #d6deeb; }
.st-key-pa_status [data-testid="stButtonGroup"] button[kind="pillsActive"] { background: #0b2563 !important;
    border-color: #0b2563 !important; }
.st-key-pa_status [data-testid="stButtonGroup"] button[kind="pillsActive"] p { color: #fff !important; }
.st-key-pa_busca input { border-radius: 14px !important; height: 3rem; font-size: 1rem; }
.pa-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: .7rem; margin: .4rem 0 1rem; }
.pa-card { background: #fff; border-radius: 20px; padding: .85rem 1rem .8rem; position: relative; overflow: hidden;
    box-shadow: 0 10px 22px -20px rgba(11,37,99,.8); border: 1px solid #e3e9f3; }
.pa-card:before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px; background: var(--c); }
.pa-top { display: flex; justify-content: space-between; align-items: center; gap: .5rem; }
.pa-cod { font-size: .72rem; color: #7a8496; font-weight: 700; letter-spacing: .02em; }
.pa-st { font-size: .7rem; font-weight: 800; color: var(--c); background: color-mix(in srgb, var(--c) 12%, white);
    border-radius: 999px; padding: .12rem .55rem; white-space: nowrap; }
.pa-nome { font-weight: 800; color: #142033; font-size: .98rem; line-height: 1.25; margin: .25rem 0 .55rem; }
.pa-meio { display: flex; align-items: flex-end; justify-content: space-between; gap: .6rem; }
.pa-est b { font-size: 1.75rem; font-weight: 900; color: #0b2563; line-height: 1; }
.pa-est span { font-size: .75rem; color: #6b7588; font-weight: 700; margin-left: .2rem; }
.pa-cob { text-align: right; font-size: .75rem; color: #6b7588; font-weight: 700; }
.pa-cob b { display: block; font-size: 1rem; color: var(--c); }
.pa-barra { height: 7px; background: #edf1f7; border-radius: 99px; overflow: hidden; margin: .5rem 0 .55rem; }
.pa-barra i { display: block; height: 100%; background: var(--c); border-radius: 99px; }
.pa-pux { display: grid; grid-template-columns: repeat(4, 1fr); gap: .35rem; }
.pa-pux div { background: #f4f7fc; border-radius: 10px; padding: .3rem .2rem; text-align: center; }
.pa-pux div.on { background: #e8f0ff; }
.pa-pux small { display: block; font-size: .64rem; color: #6b7588; font-weight: 800; text-transform: uppercase; }
.pa-pux b { font-size: .88rem; color: #142033; }
.pa-pux div.z b { color: #b4bccb; }
.pa-vazio { background: #fff; border-radius: 18px; padding: 1.4rem; text-align: center; color: #5b6576; font-weight: 700; }
</style>
"""


def _e(v) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and v != v) else str(v))


def _n(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "0"
    return ui.numero(f) if f == f else "0"


def _hero(revenda: str, atualizado) -> None:
    from modules.puxada.app_motorista import _foto_carreta

    foto = _foto_carreta()
    fundo = f' style="background-image:url({foto})"' if foto else ""
    st.markdown(_CSS + f'<div class="pa-hero"{fundo}><div class="in"><span class="tag">Portal Comercial · Grupo Lima</span>'
                f'<h1>{_e(revenda)}</h1><div class="sub">Estoque do dia com o que está chegando (trânsito e puxadas '
                f'D0, D1, D2)</div><div class="chips"><span>🕒 estoque de {_e(atualizado or "—")}</span>'
                f'<span>🔒 somente leitura</span></div></div></div>', unsafe_allow_html=True)


def _card(r) -> str:
    st_ = r.status_comercial
    cor = COR.get(st_, "#7a8496")
    doi = r.doi if r.doi == r.doi else None
    pct = 100 if doi is None and r.disponivel > 0 else min((doi or 0) / 15 * 100, 100)
    cob = "—" if doi is None else f"{ui.numero(doi, 1)} dias"
    pux = [("Trâns.", r.transito), ("D0", r.d0), ("D1", r.d1), ("D2", r.d2)]
    chips = "".join(f'<div class="{"on" if v else "z"}"><small>{k}</small><b>{_n(v)}</b></div>' for k, v in pux)
    return (f'<div class="pa-card" style="--c:{cor}"><div class="pa-top"><span class="pa-cod">CÓD {_e(r.cod)} · '
            f'{_e(r.categoria_detalhada)}</span><span class="pa-st">{ICONE.get(st_, "")} {ROTULO.get(st_, st_)}</span></div>'
            f'<div class="pa-nome">{_e(r.descricao)}</div><div class="pa-meio"><div class="pa-est"><b>{_n(r.disponivel)}</b>'
            f'<span>cx em estoque</span></div><div class="pa-cob">cobertura<b>{cob}</b></div></div>'
            f'<div class="pa-barra"><i style="width:{pct:.0f}%"></i></div><div class="pa-pux">{chips}</div></div>')


def render(operacao_id: int, revenda: str) -> None:
    df = armazem_service.estoque_comercial(operacao_id)
    ult = df["dt_atualizacao"].dropna().max() if not df.empty and "dt_atualizacao" in df else None
    _hero(revenda, ult)
    if df.empty:
        st.markdown('<div class="pa-vazio">Estoque ainda não atualizado. Volte mais tarde. 🙂</div>',
                    unsafe_allow_html=True)
        return
    total = len(df)
    cont = {s: int((df["status_comercial"] == s).sum()) for s in COR}
    st.markdown('<div class="pa-resumo">' + "".join(
        f'<div class="pa-res" style="--c:{COR[s]}"><span>{ICONE[s]} {ROTULO[s]}</span><b>{cont[s]}</b>'
        f'<i>{ui.pct(cont[s] / total * 100 if total else 0)} dos produtos</i></div>' for s in COR) + "</div>",
        unsafe_allow_html=True)

    opcoes = ["Todos", *COR]
    with st.container(key="pa_status"):
        sel = st.pills("Status", opcoes, key="pa_st", selection_mode="single", default="Todos",
                       format_func=lambda s: f"Todos · {total}" if s == "Todos" else f"{ICONE[s]} {ROTULO[s]} · {cont[s]}",
                       label_visibility="collapsed") or "Todos"
    with st.container(key="pa_busca"):
        busca = st.text_input("Buscar", key="pa_q", placeholder="🔍  Buscar produto ou código",
                              label_visibility="collapsed")
    c1, c2, c3 = st.columns(3)
    tipo = c1.selectbox("Tipo", ["Todos", "CERVEJA", "NAB", "MARKETPLACE", "OUTROS"], key="pa_tipo")
    emb = c2.selectbox("Embalagem", ["Todas", "Retornável", "Descartável", "Chopp", "Outros"], key="pa_emb")
    modo = c3.selectbox("Ver como", ["📱 Cartões", "📊 Tabela", "📲 Para o grupo"], key="pa_modo")

    vis = df
    if sel != "Todos":
        vis = vis[vis["status_comercial"] == sel]
    if tipo != "Todos":
        vis = vis[vis["tipo"] == tipo]
    if emb != "Todas":
        vis = vis[vis["categoria_detalhada"] == emb]
    if busca:
        vis = vis[vis["cod"].astype(str).str.contains(busca) | vis["descricao"].str.contains(busca, case=False, regex=False)]
    ordem = {"Stock Out": 0, "Stock Low": 1, "Stock Ideal": 2, "Stock Over": 3}
    vis = vis.assign(_o=vis["status_comercial"].map(ordem)).sort_values(["_o", "doi", "descricao"], na_position="last")

    if modo.startswith("📲"):
        estoque_dia._grupo(vis, operacao_id, "pa")
        return
    st.caption(f"{len(vis)} produto(s)")
    if vis.empty:
        st.markdown('<div class="pa-vazio">Nenhum produto com esses filtros.</div>', unsafe_allow_html=True)
        return
    if modo.startswith("📊"):
        ui.tabela(vis.assign(status=vis["status_comercial"].map(lambda s: f"{ICONE.get(s, '')} {ROTULO.get(s, s)}"))[
            ["cod", "descricao", "categoria_detalhada", "disponivel", "transito", "d0", "d1", "d2", "doi", "status"]],
            column_config={"cod": st.column_config.NumberColumn("Código", format="%d"), "descricao": "Produto",
                           "categoria_detalhada": "Embalagem",
                           "disponivel": st.column_config.NumberColumn("Estoque (cx)", format="%.0f"),
                           "transito": st.column_config.NumberColumn("🚚 Trânsito", format="%.0f"),
                           "d0": st.column_config.NumberColumn("D0", format="%.0f"),
                           "d1": st.column_config.NumberColumn("D1", format="%.0f"),
                           "d2": st.column_config.NumberColumn("D2", format="%.0f"),
                           "doi": st.column_config.NumberColumn("Cobertura", format="%.1f d"), "status": "Status"},
            baixar="portal_comercial")
        return
    lim_k = "pa_limite"
    lim = st.session_state.get(lim_k, POR_PAGINA)
    st.markdown('<div class="pa-grid">' + "".join(_card(r) for r in vis.head(lim).itertuples()) + "</div>",
                unsafe_allow_html=True)
    if len(vis) > lim:
        if st.button(f"⬇️ Mostrar mais ({len(vis) - lim} restantes)", key="pa_mais", **ui.LARGURA):
            st.session_state[lim_k] = lim + POR_PAGINA
            st.rerun()
