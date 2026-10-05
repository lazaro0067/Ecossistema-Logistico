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
    cols = st.columns(4)
    for col, (rot, (cor, ico, desc)) in zip(cols, STATUS.items()):
        n = int((df["status_comercial"] == rot).sum())
        with col:
            tema.kpis([{"titulo": f"{ico} {rot}", "valor": f"{n} SKUs", "status": cor,
                        "detalhe": f"{ui.pct(n / total * 100 if total else 0)} · {desc}"}])
            ativo = st.session_state[filtro_k] == rot
            if st.button("✓ Filtrando" if ativo else "Filtrar", key=f"{key}_btn_{rot}", type="primary" if ativo else "secondary",
                         **ui.LARGURA):
                st.session_state[filtro_k] = None if ativo else rot
                st.rerun()

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

    modo = st.radio("Visualização", ["📊 Tabela", "📱 Cards (D0, D1, D2)"], horizontal=True, key=f"{key}_modo")
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
