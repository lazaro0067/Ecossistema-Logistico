"""Armazém › ✅ Check de Grade — 02.05.02 do dia (depósito 1) × grade (02.03.04). Diferença acima do limite vira
alerta para os gestores do controle e aparece no painel de itens errados."""
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core import arquivos, graficos, tema, tempo, ui
from repositories import operacoes_repo
from services import grade_service as gs
from services.erros import RegraNegocioError

_ABAS = {"painel": "📊 Painel (itens errados)", "novo": "➕ Novo check", "historico": "🕒 Histórico",
         "controle": "⚙️ Controle & alertas"}
VERDE, VERMELHO, AMARELO, AZUL = "#1baf7a", "#e34948", "#eda100", "#2a78d6"


def _n(v, c=0) -> str:
    return "—" if v is None or pd.isna(v) else ui.numero(v, c)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+.1f}%".replace(".", ",")


def render(usuario: dict, operacao_id: int) -> None:
    aba = ui._escolha("gr_aba", list(_ABAS), "painel", pills=True, formatar=_ABAS.get)
    {"painel": _painel, "novo": _novo, "historico": _historico, "controle": _controle}[aba](usuario, operacao_id)


# --- 📊 Painel ---------------------------------------------------------------------------------------------------------
def _painel(usuario: dict, op: int) -> None:
    ck = gs.checks(op)
    if ck.empty:
        st.info("Nenhum check de grade ainda. Use ➕ Novo check: suba o 02.05.02 do dia — o depósito 1 é conferido "
                "com a grade do relatório 02.03.04.")
        return
    ult = ck.iloc[0]
    it = gs.itens(int(ult["id"]))
    div = it[it["divergente"]]
    acur = (1 - len(div) / len(it)) * 100 if len(it) else None
    falta = div.loc[div["dif"] < 0, "dif"].sum()
    sobra = div.loc[div["dif"] > 0, "dif"].sum()
    tema.kpis([
        {"titulo": "Último check", "valor": pd.to_datetime(ult["data"]).strftime("%d/%m/%Y"), "icone": "✅",
         "status": "info", "detalhe": f"{int(ult['itens'])} itens · por {ult['criado_por'] or '—'}"},
        {"titulo": "Itens com diferença", "valor": _n(len(div)), "icone": "⚠️",
         "status": "critico" if len(div) else "bom", "detalhe": f"acima de {float(ult['limite_pct'] or 5):.0f}%",
         "dados": _tab(div) if len(div) else None},
        {"titulo": "Acurácia da grade", "valor": f"{acur:.1f}%".replace(".", ",") if acur is not None else "—",
         "icone": "🎯", "status": "bom" if (acur or 0) >= 98 else "atencao" if (acur or 0) >= 95 else "critico",
         "detalhe": "itens sem diferença"},
        {"titulo": "Falta na grade", "valor": f"{_n(falta)} cx", "icone": "🔻", "status": "critico" if falta else "bom",
         "detalhe": "grade menor que o depósito 1"},
        {"titulo": "Sobra na grade", "valor": f"{_n(sobra)} cx", "icone": "🔺", "status": "atencao" if sobra else "bom",
         "detalhe": "grade maior que o depósito 1"},
    ], key="kp_grade")
    if not div.empty:
        top = div.head(15).iloc[::-1]
        fig = go.Figure(go.Bar(y=top["cod"] + " · " + top["descricao"].str[:28], x=top["dif"], orientation="h",
                               marker_color=[VERMELHO if d < 0 else AMARELO for d in top["dif"]],
                               text=[f"{d:+.0f} cx ({p:+.0f}%)" for d, p in zip(top["dif"], top["dif_pct"])],
                               textposition="outside"))
        graficos.mostrar(graficos._layout(fig, "Maiores diferenças (grade − depósito 1, em caixas)",
                                          max(300, 32 * len(top) + 90), legenda=False), key="gr_g_top")
        tema.secao(f"❌ Itens errados no check de {pd.to_datetime(ult['data']).strftime('%d/%m/%Y')}")
        ui.tabela(_tab(div), baixar=f"grade_errados_{ult['data']}")
    else:
        st.success("Grade 100% batendo com o sistema no último check. 👏")
    if len(ck) > 1:
        h = ck.head(20).iloc[::-1]
        ac = [(1 - d / i) * 100 if i else None for d, i in zip(h["divergentes"], h["itens"])]
        fig = go.Figure()
        fig.add_bar(x=pd.to_datetime(h["data"]).dt.strftime("%d/%m"), y=h["divergentes"], name="Itens com diferença",
                    marker_color=VERMELHO)
        fig.add_scatter(x=pd.to_datetime(h["data"]).dt.strftime("%d/%m"), y=ac, name="Acurácia %", yaxis="y2",
                        mode="lines+markers", line=dict(color=VERDE))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 100], showgrid=False))
        graficos.mostrar(graficos._layout(fig, "Evolução dos checks", 320), key="gr_g_evo")
    rec = gs.recorrentes(op)
    if not rec.empty:
        tema.secao("🔁 Itens que erram sempre", "Diferença em mais de um dos últimos checks — vale investigar a causa.")
        ui.tabela(pd.DataFrame({"Código": rec["cod"], "Produto": rec["descricao"],
                                "Vezes com diferença": [f"{v} de {d}" for v, d in zip(rec["vezes"], rec["de"])],
                                "Diferença média (cx)": rec["dif_media"].map(lambda v: f"{v:+.0f}")}),
                  baixar="grade_recorrentes")


def _tab(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "": ["🔻" if d < 0 else "🔺" for d in df["dif"]], "Código": df["cod"], "Produto": df["descricao"],
        "Depósito 1 (cx)": df["sistema"].map(_n), "Grade 02.03.04 (cx)": df["grade"].map(_n),
        "Diferença (cx)": df["dif"].map(lambda v: f"{v:+.0f}"), "Diferença %": df["dif_pct"].map(_p)}).reset_index(
        drop=True)


# --- ➕ Novo check -----------------------------------------------------------------------------------------------------
def _novo(usuario: dict, op: int) -> None:
    if operacoes_repo.e_consolidada(op):
        st.info("Escolha uma filial no menu para conferir a grade.")
        return
    grade, dt_grade = gs.grade_020304(op)
    lim = gs.limite(op)
    c1, c2, c3 = st.columns([1, 1.6, 1])
    data = c1.date_input("Data do check", value=tempo.hoje(), format="DD/MM/YYYY", key="gr_data")
    if grade.empty:
        c2.warning("A grade vem do relatório **02.03.04** — suba ele em 📥 Atualizar relatórios.")
        return
    quando = pd.to_datetime(dt_grade, errors="coerce") if dt_grade else None
    c2.markdown(f"**Grade (02.03.04):** {len(grade)} produto(s) · {_n(grade['grade'].sum())} cx  \n"
                f"carregado em {quando.strftime('%d/%m/%Y %H:%M') if quando is not None and pd.notna(quando) else '—'}")
    if quando is not None and pd.notna(quando) and quando.date() != data:
        c2.caption("⚠️ O 02.03.04 não é da data do check — atualize se quiser conferir com a grade do dia.")
    c3.metric("Limite de diferença", f"{lim:.0f}%")
    arq = st.file_uploader("📤 02.05.02 do dia (" + arquivos.FORMATOS_TXT + ") — o sistema confere o depósito 1",
                           type=arquivos.FORMATOS, key="gr_arq")
    if arq is None:
        st.caption("Suba o 02.05.02 do dia: todos os produtos com saldo no depósito 1 são comparados, em caixas, com o "
                   "disponível da grade (02.03.04).")
        return
    try:
        a2 = arquivos.preparar(arq)
        sist = gs.sistema_020502(a2.getvalue(), a2.name)
    except RegraNegocioError as e:
        st.error(str(e))
        return
    comp = gs.comparar(sist, grade, lim)
    div = comp[comp["divergente"]]
    tema.kpis([
        {"titulo": "Depósito 1 (02.05.02)", "valor": f"{_n(sist['sistema'].sum())} cx", "icone": "🏬",
         "status": "info", "detalhe": f"{len(sist)} produto(s)"},
        {"titulo": "Itens conferidos", "valor": _n(len(comp)), "icone": "📋", "status": "info"},
        {"titulo": "Com diferença", "valor": _n(len(div)), "icone": "⚠️", "status": "critico" if len(div) else "bom",
         "detalhe": f"acima de {lim:.0f}%"},
        {"titulo": "Batendo", "valor": _n(len(comp) - len(div)), "icone": "✅", "status": "bom"},
    ], key="kp_gr_novo")
    if not div.empty:
        ui.tabela(_tab(div), baixar="grade_previa")
    else:
        st.success("Tudo batendo: depósito 1 igual à grade. 👏")
    obs = st.text_input("Observação (opcional)", key="gr_obs")
    if st.button("💾 Salvar check e alertar o controle", type="primary", key="gr_salvar"):
        try:
            gs.salvar_check(op, data.isoformat(), gs.FONTE, comp, usuario, obs)
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar(f"Check salvo: {len(div)} item(ns) com diferença" +
                      (" — alerta enviado ao controle." if len(div) and gs.controle(op) else "."))
            st.session_state["gr_aba"] = st.session_state["gr_aba__ultima"] = "painel"
            st.rerun()


# --- 🕒 Histórico -------------------------------------------------------------------------------------------------------
def _historico(usuario: dict, op: int) -> None:
    ck = gs.checks(op)
    if ck.empty:
        st.info("Nenhum check ainda.")
        return
    vis = pd.DataFrame({"Data": pd.to_datetime(ck["data"]).dt.strftime("%d/%m/%Y"),
                        "Itens": ck["itens"],
                        "Com diferença": ck["divergentes"],
                        "Acurácia": [f"{(1 - d / i) * 100:.1f}%".replace(".", ",") if i else "—"
                                     for d, i in zip(ck["divergentes"], ck["itens"])],
                        "Por": ck["criado_por"].fillna(""), "Obs.": ck["obs"].fillna("")})
    ui.tabela(vis, baixar="grade_historico")
    cid = st.selectbox("🔎 Abrir check", ck["id"].tolist(), key="gr_hist_sel",
                       format_func=lambda i: f"{pd.to_datetime(ck.set_index('id').at[i, 'data']).strftime('%d/%m/%Y')} · "
                                             f"{ck.set_index('id').at[i, 'divergentes']} com diferença")
    it = gs.itens(cid)
    so = st.toggle("Só os itens com diferença", value=True, key="gr_hist_so")
    ui.tabela(_tab(it[it["divergente"]] if so else it), baixar=f"grade_check_{cid}")
    from core.auth import e_master

    if e_master(usuario) and st.button("🗑️ Excluir este check", key=f"gr_del_{cid}"):
        ui.acao(gs.excluir_check, cid, sucesso="Check excluído.")


# --- ⚙️ Controle -------------------------------------------------------------------------------------------------------
def _controle(usuario: dict, op: int) -> None:
    from repositories import usuarios_repo

    if operacoes_repo.e_consolidada(op):
        st.info("Escolha uma filial no menu para cadastrar o controle.")
        return
    st.caption("Quem recebe o alerta quando o check de grade dá diferença acima do limite.")
    us = {u["id"]: f"{u['nome']} ({u.get('cargo') or u.get('perfil') or ''})" for u in usuarios_repo.listar()
          if u.get("ativo", 1)}
    with st.form("gr_ctrl", border=True):
        sel = st.multiselect("Gestores do controle (recebem o alerta)", list(us),
                             default=[i for i in gs.controle(op) if i in us], format_func=us.get)
        lim = st.number_input("Limite de diferença para alerta (%)", value=gs.limite(op), min_value=0.0, step=1.0)
        if st.form_submit_button("💾 Salvar", type="primary"):
            try:
                gs.salvar_controle(op, sel)
                gs.salvar_limite(op, lim)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar("Controle salvo.")
                st.rerun()
