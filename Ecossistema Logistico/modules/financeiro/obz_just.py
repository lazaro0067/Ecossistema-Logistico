"""Financeiro › 🎯 Gestão OBZ › 📝 Justificar Dispersão — cada dono justifica as suas contas com dispersão (≥ 5%,
para mais ou para menos); o financeiro aprova e as aprovadas vão para a reunião como insumo."""
import datetime as dt
import html as _h

import pandas as pd
import streamlit as st

from core import tema, tempo, ui
from repositories import operacoes_repo
from services import obz_just_service as js
from services import obz_service as obz
from services.erros import RegraNegocioError

_CSS = """<style>
.jd-card{background:#fff;border:1px solid #e3e6ec;border-left:7px solid var(--c);border-radius:14px;padding:.75rem .9rem;
 margin-bottom:.15rem;box-shadow:0 1px 3px #0b1f3a0d}
.jd-top{display:flex;justify-content:space-between;gap:.5rem;align-items:flex-start}
.jd-tit{font-weight:800;color:#0B1F3A;font-size:.98rem;line-height:1.25}
.jd-sub{font-size:.78rem;color:#52514e;margin-top:.1rem}
.jd-chip{font-size:.72rem;font-weight:800;border-radius:999px;padding:.15rem .55rem;white-space:nowrap;background:var(--bg);
 color:var(--fg)}
.jd-num{display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem;margin:.55rem 0 .2rem;background:#f6f8fb;border-radius:10px;
 padding:.45rem .55rem;font-size:.8rem}
.jd-num b{display:block;font-size:.95rem;color:#0B1F3A}
.jd-disp b{color:var(--c)}
.jd-txt{font-size:.82rem;color:#2d2c29;background:#f9fafc;border-radius:8px;padding:.4rem .55rem;margin-top:.35rem}
[class*="st-key-jdbtn_"] button{background:linear-gradient(120deg,#ff7a59,#e34fa0 45%,#7c5cff);color:#fff;border:0;
 font-weight:800;box-shadow:0 3px 10px #e34fa033}
[class*="st-key-jdbtn_"] button:hover{filter:brightness(1.08);color:#fff}
[class*="st-key-jdok_"] button{background:linear-gradient(120deg,#1baf7a,#2a78d6);color:#fff;border:0;font-weight:800}
</style>"""
_CHIP = {"pendente": ("#fff3d6", "#8a5a00"), "aguardando": ("#e6f0ff", "#1c5cab"), "aprovada": ("#e2f6ee", "#0f6b4a"),
         "reprovada": ("#fde8e8", "#a32626")}
_ABAS = {"justificar": "✏️ Justificar", "aprovar": "✔️ Aprovar (financeiro)", "quem": "👥 Quem já fez",
         "prazo": "⏰ Prazo & limite"}


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else ui.moeda(v)


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+.1f}%".replace(".", ",")


def _mes_padrao(meses: list[str]) -> int:
    atual = tempo.hoje().strftime("%Y-%m")
    fechados = [m for m in meses if m < atual]
    return meses.index(fechados[0]) if fechados else 0


def render(usuario: dict, operacao_id: int) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    op = ui.visao_acompanhamento(usuario, operacao_id, "obz_just")
    meses = obz.meses(op)
    if not meses:
        st.info("Suba a Base OBZ ou o 16.03.01 para ver as dispersões.")
        return
    c1, c2 = st.columns([1, 3])
    mes = c1.selectbox("Mês", meses, index=_mes_padrao(meses), key="jd_mes", format_func=ui.nome_mes)
    cfg = js.config(op, mes)
    with st.spinner("Buscando as dispersões..."):
        df = js.lista(op, mes)
    tudo = js.ve_tudo(usuario)
    meu = js.minhas(df, usuario)
    base = df if tudo else meu
    _prazo_banner(cfg, base, c2)
    if df.empty:
        st.success(f"Nenhuma conta com dispersão ≥ {cfg['limite']:.0f}% em {ui.nome_mes(mes)}. 👏")
        return
    feitas = base["j_status"].isin(["aguardando", "aprovada"]).sum()
    tema.kpis([
        {"titulo": "Contas com dispersão", "valor": ui.numero(len(base)), "icone": "📋", "status": "info",
         "detalhe": f"≥ {cfg['limite']:.0f}% · {'todas' if tudo else 'as suas'}"},
        {"titulo": "Acima do plan", "valor": _m(base.loc[base["tipo"] == "acima", "disp"].sum()), "icone": "🔴",
         "status": "critico", "detalhe": f"{int((base['tipo'] == 'acima').sum())} conta(s)"},
        {"titulo": "Abaixo do plan", "valor": _m(base.loc[base["tipo"] == "abaixo", "disp"].sum()), "icone": "🟢",
         "status": "bom", "detalhe": f"{int((base['tipo'] == 'abaixo').sum())} conta(s)"},
        {"titulo": "Justificadas", "valor": f"{feitas}/{len(base)}", "icone": "✏️",
         "status": "bom" if feitas == len(base) else "atencao",
         "detalhe": f"{feitas / len(base) * 100:.0f}% feito" if len(base) else ""},
        {"titulo": "Aguardando aprovação", "valor": ui.numero((base["j_status"] == "aguardando").sum()), "icone": "🕒",
         "status": "info"},
        {"titulo": "Aprovadas (vão p/ reunião)", "valor": ui.numero((base["j_status"] == "aprovada").sum()),
         "icone": "✔️", "status": "bom"},
    ], key="kp_jd")
    st.progress(float(feitas / len(base)) if len(base) else 1.0, text=f"Progresso das justificativas: {feitas} de "
                f"{len(base)}")
    abas = ["justificar"] + (["aprovar", "quem"] if tudo else []) + (["prazo"] if js.pode_configurar(usuario) else [])
    aba = ui._escolha("jd_aba", abas, "justificar", pills=True, formatar=_ABAS.get) if len(abas) > 1 else "justificar"
    if aba == "justificar":
        _justificar(usuario, op, mes, df if tudo else meu, tudo)
    elif aba == "aprovar":
        _aprovar(usuario, df)
    elif aba == "quem":
        _quem(df)
    else:
        _prazo(usuario, op, mes, cfg)


def _prazo_banner(cfg: dict, base: pd.DataFrame, cont) -> None:
    if not cfg["prazo"]:
        cont.caption("⏰ Prazo das justificativas ainda não definido (o dono do financeiro define em ⏰ Prazo & limite).")
        return
    pz = dt.date.fromisoformat(str(cfg["prazo"])[:10])
    falta = (pz - tempo.hoje()).days
    pend = int(base["j_status"].isin(["pendente", "reprovada"]).sum()) if not base.empty else 0
    if falta < 0 and pend:
        cont.error(f"⏰ Prazo vencido em {pz:%d/%m/%Y} — {pend} justificativa(s) atrasada(s).")
    elif falta <= 2 and pend:
        cont.warning(f"⏰ Prazo: {pz:%d/%m/%Y} ({'hoje' if falta == 0 else f'{falta} dia(s)'}) — {pend} pendente(s).")
    else:
        cont.info(f"⏰ Prazo das justificativas: **{pz:%d/%m/%Y}**" + (f" · faltam {falta} dia(s)" if falta >= 0 else ""))


# --- ✏️ Justificar ----------------------------------------------------------------------------------------------------
def _justificar(usuario: dict, op: int, mes: str, df: pd.DataFrame, tudo: bool) -> None:
    if df.empty:
        st.success("Você não tem contas com dispersão neste mês. 👏" if not tudo else "Nenhuma conta.")
        return
    f1, f2, f3 = st.columns([1.3, 1.3, 1])
    st_sel = f1.multiselect("Status", list(js.STATUS), default=["pendente", "reprovada", "aguardando"],
                            format_func=js.STATUS.get, key="jd_f_st")
    areas = sorted(df["area"].dropna().unique())
    ar = f2.multiselect("Departamento", areas, key="jd_f_area", placeholder="Todos")
    tipo = f3.segmented_control("Dispersão", ["acima", "abaixo"], selection_mode="multi", default=["acima", "abaixo"],
                                format_func={"acima": "🔴 Acima", "abaixo": "🟢 Abaixo"}.get, key="jd_f_tipo") \
        if hasattr(st, "segmented_control") else ["acima", "abaixo"]
    v = df[df["j_status"].isin(st_sel)] if st_sel else df
    if ar:
        v = v[v["area"].isin(ar)]
    if tipo:
        v = v[v["tipo"].isin(tipo)]
    st.caption(f"{len(v)} conta(s) — clique no ✏️ para justificar.")
    cols = st.columns(2)
    for i, r in enumerate(v.head(80).to_dict("records")):
        with cols[i % 2]:
            _card(usuario, op, mes, r)
    if len(v) > 80:
        st.caption("Mostrando as 80 maiores — use os filtros.")


def _card(usuario: dict, op: int, mes: str, r: dict) -> None:
    e = _h.escape
    cor = "#e34948" if r["tipo"] == "acima" else "#1baf7a"
    bg, fg = _CHIP[r["j_status"]]
    txt = ""
    if r.get("j_texto"):
        txt = (f'<div class="jd-txt">💬 {e(str(r["j_texto"]))}'
               + (f'<br>🎯 <b>Ação:</b> {e(str(r["j_acao"]))}' if r.get("j_acao") else "")
               + f'<br><span style="color:#6b6a65;font-size:.72rem">por {e(str(r.get("j_por") or ""))}</span>'
               + (f'<br><span style="color:#a32626">↩️ {e(str(r["j_comentario"]))}</span>'
                  if r["j_status"] == "reprovada" and r.get("j_comentario") else "") + "</div>")
    st.markdown(
        f'<div class="jd-card" style="--c:{cor}"><div class="jd-top"><div><div class="jd-tit">{e(str(r["conta"]))} · '
        f'{e(str(r.get("nome_conta") or ""))}</div><div class="jd-sub">{e(str(r["area"]))} · {e(str(r["nome_depto"]))} · '
        f'👤 {e(str(r.get("responsavel") or "Sem dono"))}</div></div>'
        f'<span class="jd-chip" style="--bg:{bg};--fg:{fg}">{js.STATUS[r["j_status"]]}</span></div>'
        f'<div class="jd-num"><div>Plan<b>{e(_m(r["plan"]))}</b></div><div>Real<b>{e(_m(r["fechamento"]))}</b></div>'
        f'<div class="jd-disp">Dispersão<b>{e(_m(r["disp"]))} ({e(_p(r["disp_pct"]))})</b></div></div>{txt}</div>',
        unsafe_allow_html=True)
    if r["j_status"] in ("pendente", "reprovada", "aguardando") and js.pode_justificar(r, usuario):
        rot = "✏️ Justificar" if r["j_status"] != "aguardando" else "✏️ Editar justificativa"
        with st.container(key=f"jdbtn_{r['conta']}_{r['depto']}"):
            if st.button(rot, key=f"jd_b_{r['conta']}_{r['depto']}", **ui.LARGURA):
                _dialogo(usuario, op, mes, r)


def _dialogo(usuario: dict, op: int, mes: str, r: dict) -> None:
    def corpo():
        st.markdown(f"**{r['conta']} · {r.get('nome_conta') or ''}**  \n{r['area']} · {r['nome_depto']}")
        st.markdown(f"Plan **{_m(r['plan'])}** → real **{_m(r['fechamento'])}** · dispersão **{_m(r['disp'])} "
                    f"({_p(r['disp_pct'])})** — {'🔴 acima do plan' if r['tipo'] == 'acima' else '🟢 abaixo do plan'}")
        with st.form(f"jd_form_{r['conta']}_{r['depto']}"):
            texto = st.text_area("O que aconteceu? (justificativa)", value=r.get("j_texto") or "", height=110)
            acao = st.text_input("Ação para corrigir / manter (opcional)", value=r.get("j_acao") or "")
            if st.form_submit_button("💾 Enviar para aprovação", type="primary"):
                try:
                    js.justificar(op, mes, r, texto, acao, usuario)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    ui.avisar("Justificativa enviada para o financeiro aprovar. ✅")
                    st.rerun()
    if hasattr(st, "dialog"):
        st.dialog("✏️ Justificar dispersão", width="large")(corpo)()
    else:
        corpo()


# --- ✔️ Aprovar ----------------------------------------------------------------------------------------------------
def _aprovar(usuario: dict, df: pd.DataFrame) -> None:
    pend = df[df["j_status"] == "aguardando"]
    if pend.empty:
        st.success("Nenhuma justificativa aguardando aprovação. 👏")
        return
    st.caption(f"{len(pend)} justificativa(s) para aprovar. Aprovadas vão para a 🗓️ Reunião & Ações como insumo; "
               "reprovadas voltam para o dono refazer.")
    for r in pend.to_dict("records"):
        with st.container(border=True):
            a, b = st.columns([2.2, 1])
            a.markdown(f"**{r['conta']} · {r.get('nome_conta') or ''}** — {r['area']} · {r['nome_depto']}  \n"
                       f"Plan {_m(r['plan'])} → real {_m(r['fechamento'])} · **{_m(r['disp'])} ({_p(r['disp_pct'])})**")
            a.markdown(f"💬 {r['j_texto']}" + (f"  \n🎯 **Ação:** {r['j_acao']}" if r.get("j_acao") else "")
                       + f"  \n_por {r.get('j_por')} em {r.get('j_em')}_")
            com = b.text_input("Comentário (obrigatório para reprovar)", key=f"jd_com_{r['j_id']}")
            x, y = b.columns(2)
            with x.container(key=f"jdok_{r['j_id']}"):
                if st.button("✔️ Aprovar", key=f"jd_ok_{r['j_id']}", **ui.LARGURA):
                    ui.acao(js.aprovar, int(r["j_id"]), usuario, True, com, sucesso="Justificativa aprovada.")
            if y.button("❌ Reprovar", key=f"jd_no_{r['j_id']}", **ui.LARGURA):
                ui.acao(js.aprovar, int(r["j_id"]), usuario, False, com, sucesso="Reprovada — voltou para o dono.")


# --- 👥 Quem já fez ---------------------------------------------------------------------------------------------------
def _quem(df: pd.DataFrame) -> None:
    pg = js.progresso(df)
    if pg.empty:
        st.info("Sem dados.")
        return
    st.dataframe(pd.DataFrame({"Responsável": pg["responsavel"], "Contas": pg["contas"],
                               "Justificadas": pg["justificadas"], "Aprovadas": pg["aprovadas"],
                               "Pendentes": pg["pendentes"], "Progresso": pg["pct"]}), hide_index=True, **ui.LARGURA,
                 column_config={"Progresso": st.column_config.ProgressColumn("Progresso", format="%.0f%%",
                                                                            min_value=0, max_value=100)})
    pend = df[df["j_status"].isin(["pendente", "reprovada"])]
    if not pend.empty:
        tema.secao("⏳ O que falta, por responsável")
        ui.tabela(pd.DataFrame({"Responsável": pend["responsavel"], "Conta": pend["conta"] + " · " +
                                pend["nome_conta"].fillna(""), "Departamento": pend["area"],
                                "Dispersão": pend["disp"].map(_m), "Disp. %": pend["disp_pct"].map(_p),
                                "Status": pend["j_status"].map(js.STATUS)}).sort_values("Responsável"),
                  baixar="justificativas_pendentes")


# --- ⏰ Prazo & limite -------------------------------------------------------------------------------------------------
def _prazo(usuario: dict, op: int, mes: str, cfg: dict) -> None:
    if operacoes_repo.e_consolidada(op):
        st.info("Escolha a revenda para definir o prazo.")
        return
    padrao = dt.date.fromisoformat(str(cfg["prazo"])[:10]) if cfg["prazo"] else tempo.hoje() + dt.timedelta(days=5)
    with st.form("jd_prazo", border=True):
        c1, c2 = st.columns(2)
        pz = c1.date_input("Prazo para os donos justificarem", value=padrao, format="DD/MM/YYYY")
        lim = c2.number_input("Dispersão mínima para justificar (%)", value=float(cfg["limite"]), min_value=0.0,
                              step=1.0)
        st.caption("Ao salvar, cada dono recebe um aviso com quantas contas tem para justificar e o prazo.")
        if st.form_submit_button("💾 Salvar e avisar os donos", type="primary"):
            ui.acao(js.salvar_config, op, mes, pz, lim, usuario, sucesso="Prazo salvo e donos avisados.")
    if cfg.get("definido_por"):
        st.caption(f"Definido por {cfg['definido_por']}.")
