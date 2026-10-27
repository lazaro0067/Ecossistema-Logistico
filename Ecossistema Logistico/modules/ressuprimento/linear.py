"""Ressuprimento › 📈 Linear Dinâmica — a linear (venda/dia) calculada pelo sistema, com crescimento e crítica."""
import pandas as pd
import streamlit as st

from core import tema, ui
from repositories import operacoes_repo
from services import linear_service as ls


def _n(v, c=1) -> str:
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else ui.numero(v, c)


def render(usuario: dict, operacao_id: int) -> None:
    st.markdown("##### 📦 Estoque › **📈 Linear Dinâmica**")
    if operacoes_repo.e_consolidada(operacao_id):
        st.info("Escolha uma filial no menu ao lado — a linear dinâmica é de cada revenda.")
        return
    op = operacao_id
    cfg = ls.config(op)
    with st.container(border=True):
        st.markdown("**⚙️ Usar a linear dinâmica nesta revenda**")
        c1, c2, c3 = st.columns([2.2, 1.2, 1])
        ativa = c1.toggle("Ligada — substitui a linear subida em todo o sistema (sugestão, DOI, estoque do dia…)",
                          value=cfg["ativa"], key=f"lin_ativa_{op}",
                          help="Desligue para voltar a usar a linear do relatório que foi subido.")
        cresc = c2.number_input("Crescer sobre a média (%)", min_value=-50.0, max_value=200.0, step=1.0,
                                value=float(cfg["crescimento"]), key=f"lin_cresc_{op}")
        c3.write("")
        if c3.button("💾 Salvar", key=f"lin_salvar_{op}", type="primary", **ui.LARGURA):
            ui.acao(ls.salvar_config, op, ativa, cresc, usuario.get("nome", ""),
                    sucesso="Linear dinâmica " + ("LIGADA" if ativa else "desligada — voltou a linear subida") + ".")
        st.caption(("🟢 Ligada" if cfg["ativa"] else "⚪ Desligada (vale a linear subida)")
                   + (f" · crescimento {cfg['crescimento']:+.0f}%".replace(".", ",") if cfg["crescimento"] else "")
                   + (f" · alterado por {cfg['por']} em {cfg['em']}" if cfg.get("por") else ""))
    with st.spinner("Calculando a linear…"):
        d = ls.calcular(op)
    if d.empty:
        st.info("Sem venda por produto (03.02.37 vendas) nem linear subida nesta revenda.")
        return
    ini, ate = d.attrs.get("periodo", (None, None))
    st.caption(f"Base: venda de {ini:%d/%m} a {ate:%d/%m} ({d.attrs.get('dias_base', 0)} dias de venda) · venda + "
               "bonificação em caixas ÷ dias de venda. Média inteligente: produto novo = desde a 1ª venda · sem venda "
               "nos 2 meses = média de 6 meses · sem histórico = linear subida." if ini else "")
    met = d["metodo"].value_counts()
    tot_sub = d["linear_subida"].fillna(0).sum()
    tot_fin = d["linear_final"].fillna(0).sum()
    tema.kpis([
        {"titulo": "Produtos", "valor": ui.numero(len(d)), "icone": "📦", "status": "info",
         "detalhe": f"{int((d['linear_final'] > 0).sum())} com venda/dia"},
        {"titulo": "Pela média de 2 meses", "valor": ui.numero(met.get("2 meses", 0)), "icone": "📈",
         "status": "info", "detalhe": "histórico completo"},
        {"titulo": "Média inteligente", "valor": ui.numero(met.get("desde a 1ª venda (novo)", 0)
                                                           + met.get("6 meses (sem venda recente)", 0)),
         "icone": "🧠", "status": "info",
         "detalhe": f"{met.get('desde a 1ª venda (novo)', 0)} novos · {met.get('6 meses (sem venda recente)', 0)} "
                    "pela média de 6 meses"},
        {"titulo": "Criticados (manual)", "valor": ui.numero(int(d["linear_manual"].notna().sum())), "icone": "✍️",
         "status": "info", "detalhe": "valem no lugar do calculado"},
        {"titulo": "Total cx/dia", "valor": _n(tot_fin, 0), "icone": "🧮",
         "status": "info", "detalhe": f"linear subida: {_n(tot_sub, 0)} cx/dia"
                                      + (f" ({(tot_fin / tot_sub - 1) * 100:+.0f}%)".replace(".", ",")
                                         if tot_sub else "")},
    ], key=f"kp_lin_{op}")

    tema.secao("✍️ Criticar produto a produto",
               "Digite o valor certo (cx/dia) na coluna ✍️ Crítica para o produto que precisa de ajuste — ele vale no "
               "lugar do calculado. Apague o valor para voltar ao calculado.")
    f1, f2 = st.columns([2.2, 1])
    busca = f1.text_input("🔎", key=f"lin_busca_{op}", label_visibility="collapsed",
                          placeholder="🔎 Pesquisar produto (código ou nome)…")
    so = f2.selectbox("Mostrar", ["Todos", "Só criticados", "Média inteligente", "Linear subida (sem histórico)",
                                  "Diferença > 30% da subida"], key=f"lin_filtro_{op}", label_visibility="collapsed")
    v = d.copy()
    if busca.strip():
        t = busca.strip().lower()
        v = v[v["cod"].astype(str).str.contains(t) | v["descricao"].astype(str).str.lower().str.contains(t, regex=False)]
    if so == "Só criticados":
        v = v[v["linear_manual"].notna()]
    elif so == "Média inteligente":
        v = v[v["metodo"].str.startswith(("desde", "6 meses"))]
    elif so.startswith("Linear subida"):
        v = v[v["metodo"].str.startswith("linear subida")]
    elif so.startswith("Diferença"):
        sub_ = v["linear_subida"].fillna(0)
        v = v[(sub_ > 0) & ((v["linear_dinamica"] / sub_ - 1).abs() > .3)]
    v = v.sort_values("linear_final", ascending=False).reset_index(drop=True)
    if v.empty:
        st.info("Nada com esse filtro.")
        return
    ed = pd.DataFrame({"cod": v["cod"], "Produto": v["cod"].astype(str) + " · " + v["descricao"].astype(str),
                       "Subida": v["linear_subida"], "Média": v["media"], "Como calculou": v["metodo"],
                       "Dinâmica": v["linear_dinamica"], "✍️ Crítica": v["linear_manual"],
                       "Obs": v["obs"].fillna(""), "Vale": v["linear_final"]})
    novo = st.data_editor(ed, hide_index=True, key=f"lin_ed_{op}_{busca}_{so}", **ui.LARGURA, height=480,
                          disabled=["cod", "Produto", "Subida", "Média", "Como calculou", "Dinâmica", "Vale"],
                          column_order=["Produto", "Subida", "Média", "Como calculou", "Dinâmica", "✍️ Crítica",
                                        "Obs", "Vale"],
                          column_config={
                              "Subida": st.column_config.NumberColumn("Linear subida", format="%.1f"),
                              "Média": st.column_config.NumberColumn("Média (cx/dia)", format="%.1f"),
                              "Dinâmica": st.column_config.NumberColumn("Dinâmica (+cresc.)", format="%.1f"),
                              "✍️ Crítica": st.column_config.NumberColumn("✍️ Crítica (cx/dia)", min_value=0.0,
                                                                         format="%.1f"),
                              "Obs": st.column_config.TextColumn("Obs (motivo)"),
                              "Vale": st.column_config.NumberColumn("✅ Vale", format="%.1f")})
    if st.button("💾 Salvar críticas", key=f"lin_salvar_crit_{op}", type="primary"):
        n = 0
        for (_, o), (_, r) in zip(ed.iterrows(), novo.iterrows()):
            mo, mn = o["✍️ Crítica"], r["✍️ Crítica"]
            mudou_v = not ((pd.isna(mo) and pd.isna(mn)) or (not pd.isna(mo) and not pd.isna(mn) and float(mo) == float(mn)))
            if mudou_v or str(o["Obs"] or "") != str(r["Obs"] or ""):
                ls.salvar_ajuste(op, int(o["cod"]), None if pd.isna(mn) else float(mn), str(r["Obs"] or ""),
                                 usuario.get("nome", ""))
                n += 1
        ui.avisar(f"{n} produto(s) criticado(s)." if n else "Nada mudou.")
        st.rerun()
    ui.downloads(v[["cod", "descricao", "linear_subida", "media", "metodo", "dias_venda", "linear_dinamica",
                    "linear_manual", "obs", "linear_final"]], f"linear_dinamica_{op}", key=f"dl_lin_{op}")
