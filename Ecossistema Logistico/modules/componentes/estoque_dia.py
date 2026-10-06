"""Estoque do dia (Portal do RN): status Stock Out / Low / Ideal / Over, marcações D0-D1-D2,
cards coloridos ou tabela. Usado no Ressuprimento, em Vendas e no portal comercial público."""
import streamlit as st

from core import tema, ui
from services import armazem_service

STATUS = {  # rótulo: (status de cor, ícone, descrição)
    "Stock Out": ("critico", "🔴", "zerado"),
    "Stock Low": ("atencao", "🟡", f"cobertura < {armazem_service.DOI_BAIXO:.0f} dias"),
    "Stock Ideal": ("bom", "🟢", f"{armazem_service.DOI_BAIXO:.0f} a {armazem_service.DOI_ALTO:.0f} dias"),
    "Stock Over": ("info", "🔵", f"acima de {armazem_service.DOI_ALTO:.0f} dias"),
}


def render(operacao_id: int, key: str, mostrar_download: bool = True) -> None:
    df = armazem_service.estoque_comercial(operacao_id)
    if df.empty:
        st.info("ℹ️ Nenhum estoque disponível no momento. Peça a atualização da base 02.03.04 no Ressuprimento.")
        return
    ult = df["dt_atualizacao"].dropna().max() if "dt_atualizacao" in df else None
    if ult:
        st.caption(f"🕒 Última atualização do estoque: **{ult}**")

    total = len(df)
    filtro_k = f"{key}_filtro"
    st.session_state.setdefault(filtro_k, None)
    def _filtrar(rot):
        def acao():
            st.session_state[filtro_k] = None if st.session_state[filtro_k] == rot else rot
            st.rerun()
        return acao

    cards = []
    for rot, (cor, ico, desc) in STATUS.items():
        n = int((df["status_comercial"] == rot).sum())
        ativo = st.session_state[filtro_k] == rot
        cards.append({"titulo": f"{ico} {rot}", "valor": f"{n} SKUs", "status": cor,
                      "detalhe": f"{ui.pct(n / total * 100 if total else 0)} · {desc}",
                      "selo": "✓ filtrando" if ativo else None,
                      "ver": "limpar filtro" if ativo else "filtrar a lista", "ao_clicar": _filtrar(rot)})
    tema.kpis(cards, key=f"kp_{key}")

    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    busca = f1.text_input("🔍 Código ou nome do produto", key=f"{key}_busca")
    tipo = f2.selectbox("Tipo", ["Todos", "CERVEJA", "NAB", "MARKETPLACE", "OUTROS"], key=f"{key}_tipo")
    cat = f3.selectbox("Embalagem", ["Todas", "Retornável", "Descartável", "Outros"], key=f"{key}_cat")
    marcas = ["Todas"] + sorted(df["marca"].unique())
    marca = f4.selectbox("Marca", marcas, key=f"{key}_marca")

    vis = df
    if st.session_state[filtro_k]:
        vis = vis[vis["status_comercial"] == st.session_state[filtro_k]]
    if tipo != "Todos":
        vis = vis[vis["tipo"] == tipo]
    if cat != "Todas":
        vis = vis[vis["categoria_detalhada"] == cat]
    if marca != "Todas":
        vis = vis[vis["marca"] == marca]
    if busca:
        vis = vis[vis["cod"].astype(str).str.contains(busca) | vis["descricao"].str.contains(busca, case=False)]

    modo = st.radio("Visualização", ["📊 Tabela", "📲 Para enviar no grupo", "📱 Cards (D0, D1, D2)"],
                    horizontal=True, key=f"{key}_modo")
    if modo.startswith("📲"):
        _grupo(vis, operacao_id, key)
        return
    st.caption(f"{len(vis)} produto(s)")
    if modo.startswith("📱"):
        _cards(vis.head(120))
        if len(vis) > 120:
            st.caption("Mostrando os 120 primeiros — use os filtros para refinar.")
    else:
        tab = vis.assign(status=vis["status_comercial"].map(lambda s: f"{STATUS[s][1]} {s}"))
        ui.tabela(tab[["cod", "descricao", "marca", "tipo", "categoria_detalhada", "disponivel", "d0", "d1", "d2",
                       "projetado", "linear_cx_dia", "doi", "status"]], column_config={
            "cod": st.column_config.NumberColumn("Código", format="%d"), "descricao": "Produto", "marca": "Marca",
            "tipo": "Tipo", "categoria_detalhada": "Embalagem",
            "disponivel": st.column_config.NumberColumn("Estoque (cx)", format="%.0f"),
            "d0": st.column_config.NumberColumn("D0", format="%.0f"),
            "d1": st.column_config.NumberColumn("D1", format="%.0f"),
            "d2": st.column_config.NumberColumn("D2", format="%.0f"),
            "projetado": st.column_config.NumberColumn("Projetado", format="%.0f"),
            "linear_cx_dia": st.column_config.NumberColumn("Venda/dia", format="%.1f"),
            "doi": st.column_config.NumberColumn("Cobertura", format="%.1f d"), "status": "Status"})
    if mostrar_download:
        ui.downloads(vis.drop(columns=["situacao"], errors="ignore"), "estoque_comercial", key=f"dl_{key}")


def _cards(df) -> None:
    partes = []
    for r in df.itertuples():
        cor = tema.STATUS[STATUS[r.status_comercial][0]][0]
        doi = "—" if r.doi != r.doi else f"{ui.numero(r.doi, 1)} dias"
        partes.append(f"""
<div class="eco-kpi" style="--cor:{cor};margin-bottom:.6rem">
  <div class="rot" style="justify-content:space-between"><span>CÓD {r.cod} · {tema._e(r.tipo)} · {tema._e(r.categoria_detalhada)}</span>
  {tema.selo(STATUS[r.status_comercial][0], r.status_comercial)}</div>
  <div style="font-weight:700;font-size:1rem;margin:.3rem 0">{tema._e(r.descricao)}</div>
  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:.4rem;font-size:.82rem;background:#f6f8fb;border-radius:10px;padding:.5rem .6rem">
    <div><div style="color:#52514e">Estoque</div><b>{ui.numero(r.disponivel)} cx</b></div>
    <div><div style="color:#52514e">D0</div><b>{ui.numero(r.d0)}</b></div>
    <div><div style="color:#52514e">D1</div><b>{ui.numero(r.d1)}</b></div>
    <div><div style="color:#52514e">D2</div><b>{ui.numero(r.d2)}</b></div>
    <div><div style="color:#52514e">Cobertura</div><b>{doi}</b></div>
  </div>
  <div class="det" style="margin-top:.35rem">Projetado (estoque + puxadas): <b>{ui.numero(r.projetado)} cx</b></div>
</div>""")
    c1, c2 = st.columns(2)
    metade = (len(partes) + 1) // 2
    c1.markdown("".join(partes[:metade]), unsafe_allow_html=True)
    c2.markdown("".join(partes[metade:]), unsafe_allow_html=True)


# --- Modo "para enviar no grupo": cabe na tela (print) e gera o texto do WhatsApp ----------------
_CSS_GRUPO = """
<style>
.eg-box { background:#fff; border:1px solid #dfe5ee; border-radius:14px; padding:.8rem .9rem; max-width:760px; }
.eg-tit { display:flex; justify-content:space-between; align-items:baseline; gap:.5rem; margin-bottom:.45rem; }
.eg-tit b { font-size:1.05rem; color:#0B1F3A; } .eg-tit span { font-size:.78rem; color:#6b6a65; }
.eg-tab { width:100%; border-collapse:collapse; font-size:.8rem; }
.eg-tab th { background:#eef3fa; color:#0B1F3A; font-weight:800; padding:.35rem .3rem; text-align:right; }
.eg-tab th:first-child, .eg-tab td:first-child { text-align:left; white-space:normal; line-height:1.2; }
.eg-tab td { padding:.3rem .3rem; border-bottom:1px solid #eceae4; text-align:right; white-space:nowrap; }
.eg-tab tr.out td { background:#fdecec; } .eg-tab tr.low td { background:#fff8e1; }
.eg-tab td.z { color:#c3c2bc; }
.eg-leg { font-size:.72rem; color:#6b6a65; margin-top:.4rem; }
</style>
"""
_CLASSE = {"Stock Out": "out", "Stock Low": "low"}


def _curto(nome: str, n: int = 34) -> str:
    nome = " ".join(str(nome or "").split())
    return nome if len(nome) <= n else nome[: n - 1].rstrip() + "…"


def _grupo(vis, operacao_id: int, key: str) -> None:
    import html as _h

    from core import tempo
    from repositories import operacoes_repo

    c1, c2, c3 = st.columns([2, 1, 1])
    status_sel = c1.multiselect("Mostrar status", list(STATUS), default=["Stock Out", "Stock Low"],
                                format_func=lambda s: f"{STATUS[s][1]} {s}", key=f"{key}_g_status")
    so_marc = c2.toggle("Só com puxada D0–D2", value=False, key=f"{key}_g_marc")
    ordem = c3.selectbox("Ordenar por", ["Cobertura", "Produto", "Estoque"], key=f"{key}_g_ord")
    g = vis[vis["status_comercial"].isin(status_sel)] if status_sel else vis
    if so_marc:
        g = g[(g["d0"] + g["d1"] + g["d2"]) > 0]
    g = g.sort_values({"Cobertura": "doi", "Produto": "descricao", "Estoque": "disponivel"}[ordem],
                      na_position="last")
    if g.empty:
        st.info("Nenhum produto com esses filtros.")
        return
    filial = (operacoes_repo.buscar(operacao_id) or {}).get("nome", "")
    agora = tempo.agora()

    def n(v):
        return "–" if not v or v != v else ui.numero(v)

    linhas = []
    for r in g.itertuples():
        doi = "–" if r.doi != r.doi else f"{ui.numero(r.doi, 1)}d"
        linhas.append(
            f'<tr class="{_CLASSE.get(r.status_comercial, "")}"><td>{STATUS[r.status_comercial][1]} '
            f'{_h.escape(_curto(r.descricao, 48))}</td><td><b>{ui.numero(r.disponivel)}</b></td>'
            + "".join(f'<td class="{"z" if not v else ""}">{n(v)}</td>' for v in (r.d0, r.d1, r.d2))
            + f"<td>{doi}</td></tr>")
    st.markdown(
        _CSS_GRUPO + f'<div class="eg-box"><div class="eg-tit"><b>📦 Estoque · {_h.escape(filial)}</b>'
        f'<span>{agora:%d/%m %H:%M} · {len(g)} produto(s)</span></div>'
        '<table class="eg-tab"><thead><tr><th>Produto</th><th>Estoque</th><th>D0</th><th>D1</th><th>D2</th>'
        f'<th>Cob.</th></tr></thead><tbody>{"".join(linhas)}</tbody></table>'
        '<div class="eg-leg">Estoque em caixas · D0/D1/D2 = puxadas marcadas · Cob. = dias de cobertura · '
        '🔴 Stock Out · 🟡 Stock Low · 🟢 Ideal · 🔵 Over</div></div>', unsafe_allow_html=True)
    st.caption("📸 Tire o print do quadro acima ou copie o texto abaixo para colar no grupo.")
    texto = [f"*📦 Estoque {filial} — {agora:%d/%m %H:%M}*", ""]
    for rot in STATUS:
        sub = g[g["status_comercial"] == rot]
        if sub.empty:
            continue
        texto.append(f"{STATUS[rot][1]} *{rot}* ({len(sub)})")
        for r in sub.itertuples():
            puxada = " + ".join(f"{d} {ui.numero(v)}" for d, v in (("D0", r.d0), ("D1", r.d1), ("D2", r.d2)) if v)
            doi = "" if r.doi != r.doi else f" · {ui.numero(r.doi, 1)}d"
            texto.append(f"• {_curto(r.descricao, 40)} — {ui.numero(r.disponivel)} cx{doi}"
                         + (f" · puxada {puxada}" if puxada else ""))
        texto.append("")
    with st.expander("📋 Texto para WhatsApp (copiar)"):
        st.code("\n".join(texto).strip(), language=None)
    ui.downloads(g.drop(columns=["situacao"], errors="ignore"), "estoque_grupo", key=f"dl_{key}_g")
