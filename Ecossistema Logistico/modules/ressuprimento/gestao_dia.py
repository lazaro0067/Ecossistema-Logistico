"""Ressuprimento › 📅 Gestão do dia & metas semanais.

Quanto precisa puxar por dia (o que falta ÷ dias de puxada que restam), metas semanais com ajuste
do gestor (percentual a mais) e os dias sem puxada, que recalculam metas e tendência.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from config.settings import CESTAS_TOTAL, PERFIL_MASTER
from core import tema, tempo, ui
from repositories import ressuprimento_repo
from services import gestao_metas_service as svc
from services.erros import RegraNegocioError

_CSS = """
<style>
.gd-sem { display:grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap:.6rem; margin:.4rem 0 .8rem; }
.gd-card { background:#fff; border:1px solid #dfe5ee; border-top:5px solid var(--c); border-radius:14px; padding:.65rem .8rem; }
.gd-card.atual { box-shadow:0 0 0 2px #2a78d6; }
.gd-card .t { display:flex; justify-content:space-between; font-size:.8rem; color:#52514e; font-weight:700; }
.gd-card .v { font-size:1.25rem; font-weight:900; color:#0B1F3A; margin:.15rem 0; }
.gd-card .s { font-size:.76rem; color:#52514e; }
.gd-card .aj { display:inline-block; margin-top:.25rem; font-size:.7rem; font-weight:800; padding:.05rem .45rem;
    border-radius:999px; background:#fff4d6; color:#8a5a00; border:1px solid #f0c75e; }
.gd-bar { height:7px; background:#eef0f3; border-radius:99px; overflow:hidden; margin-top:.35rem; }
.gd-bar i { display:block; height:100%; background:var(--c); }
.gd-hoje { background:linear-gradient(135deg,#0B1F3A,#1f4a8a); color:#fff; border-radius:18px; padding:1rem 1.2rem;
    margin:.3rem 0 .9rem; display:flex; flex-wrap:wrap; gap:1.4rem; align-items:center; }
.gd-hoje .big { font-size:2.1rem; font-weight:900; line-height:1; }
.gd-hoje .lb { font-size:.8rem; opacity:.85; }
.gd-hoje .bl { min-width:150px; }
</style>
"""


def _gestor(usuario: dict) -> bool:
    return usuario.get("perfil") in (PERFIL_MASTER, "Gestor")


def _cor(p) -> str:
    if p is None or p != p:
        return "#898781"
    return "#146c43" if p >= 100 else "#b7791f" if p >= 90 else "#c2571a" if p >= 75 else "#a32025"


def _rot_dia(d: dt.date) -> str:
    return f"{svc.DIAS_SEMANA[d.weekday()]} {d:%d/%m}"


def _total(df: pd.DataFrame, colunas: list[str]) -> dict:
    t = df[df["cesta"].isin(CESTAS_TOTAL)]
    return {c: float(t[c].sum()) for c in colunas}


def render(usuario: dict, operacao_id: int) -> None:
    hoje = tempo.hoje()
    meses = sorted(set(ressuprimento_repo.meses_disponiveis(operacao_id)) | {hoje.strftime("%Y-%m")}, reverse=True)
    c1, c2 = st.columns([1, 3])
    mes = ui.seletor_mes("Mês", meses, key="gd_mes", container=c1)
    p = svc.plano(operacao_id, mes)
    res, sem = p["resumo"], p["semanas"]
    if res.empty:
        st.info("Sem metas nem carregamentos neste mês. Cadastre as metas em 🎯 Metas Mensais e atualize o ressuprimento.")
        _dias_sem_puxada(usuario, operacao_id, mes, p)
        return
    c2.caption(f"📅 {len(p['dias_puxada'])} dias de puxada no mês · {len(p['feitos'])} realizados · "
               f"{len(p['restantes'])} restantes"
               + (f" · último dado: {p['ref']:%d/%m}" if p["ref"] else "")
               + (f" · {len(p['sem_puxada'])} dia(s) sem puxada" if p["sem_puxada"] else ""))

    # --- Hoje: quanto puxar -------------------------------------------------------------------
    t = _total(res, ["meta", "real", "falta", "tendencia", "por_dia", "media_realizada"])
    sem_atual = sem[sem["atual"]] if not sem.empty else sem
    ts = _total(sem_atual, ["por_dia", "meta_ajustada", "real"]) if not sem_atual.empty else None
    ating = t["tendencia"] / t["meta"] * 100 if t["meta"] else None
    proximo = p["restantes"][0] if p["restantes"] else None
    st.markdown(_CSS + f'<div class="gd-hoje">'
                f'<div class="bl"><div class="lb">🎯 Precisa puxar por dia (Cerveja + Nab)</div>'
                f'<div class="big">{ui.numero(t["por_dia"])} HL</div>'
                f'<div class="lb">{"a partir de " + _rot_dia(proximo) if proximo else "mês encerrado"} · '
                f'{len(p["restantes"])} dia(s) de puxada</div></div>'
                f'<div class="bl"><div class="lb">📆 Pela meta da semana</div>'
                f'<div class="big">{ui.numero(ts["por_dia"]) + " HL" if ts else "—"}</div>'
                f'<div class="lb">meta semana {ui.numero(ts["meta_ajustada"]) if ts else "—"} · real '
                f'{ui.numero(ts["real"]) if ts else "—"}</div></div>'
                f'<div class="bl"><div class="lb">✅ Já puxado no mês</div><div class="big">{ui.numero(t["real"])}</div>'
                f'<div class="lb">de {ui.numero(t["meta"])} HL · falta {ui.numero(t["falta"])}</div></div>'
                f'<div class="bl"><div class="lb">🔮 Tendência (dias de puxada)</div>'
                f'<div class="big">{ui.numero(t["tendencia"])}</div>'
                f'<div class="lb">{ui.pct(ating) + " da meta" if ating is not None else "sem meta"} · média '
                f'{ui.numero(t["media_realizada"])}/dia</div></div></div>', unsafe_allow_html=True)

    tema.secao("🎯 Gestão do dia por indicador",
               "Precisa/dia = (meta − real) ÷ dias de puxada que restam. Na semana, usa a meta semanal ajustada.")
    pd_sem = (sem_atual.set_index("cesta")["por_dia"] if not sem_atual.empty else pd.Series(dtype=float))
    vis = pd.DataFrame({
        "": [_bola(a) for a in res["ating_tend"]],
        "Indicador": res["indicador"],
        "Meta mês (HL)": res["meta"].map(lambda v: ui.numero(v) if v else "—"),
        "Real (HL)": res["real"].map(ui.numero),
        "Falta (HL)": [ui.numero(f) if m else "—" for f, m in zip(res["falta"], res["meta"])],
        "Precisa/dia — mês": [ui.numero(v) if m else "—" for v, m in zip(res["por_dia"], res["meta"])],
        "Precisa/dia — semana": [ui.numero(pd_sem.get(c)) if c in pd_sem and m else "—"
                                 for c, m in zip(res["cesta"], res["meta"])],
        "Média realizada/dia": res["media_realizada"].map(ui.numero),
        "Tendência (HL)": res["tendencia"].map(ui.numero),
        "Ating. tendência": [float(a) if a is not None and a == a else None for a in res["ating_tend"]],
    })
    ui.tabela(vis, column_config={"Ating. tendência": st.column_config.ProgressColumn(
        "Ating. tendência", format="%.0f%%", min_value=0, max_value=120)}, baixar=f"gestao_do_dia_{mes}")
    if p["restantes"]:
        with st.expander("📋 Plano dos próximos dias de puxada (quanto puxar em cada dia)"):
            _plano_dias(p, res, sem)

    _semanas(usuario, operacao_id, mes, p)
    _dias_sem_puxada(usuario, operacao_id, mes, p)


def _bola(a) -> str:
    if a is None or a != a:
        return "⚪"
    return "🟢" if a >= 100 else "🟡" if a >= 90 else "🟠" if a >= 75 else "🔴"


def _plano_dias(p: dict, res: pd.DataFrame, sem: pd.DataFrame) -> None:
    """Cada dia de puxada que resta: precisa/dia da semana em que ele cai (meta semanal ajustada)."""
    com_meta = res[res["meta"] > 0]
    linhas = []
    for d in p["restantes"]:
        s = sem[(sem["ini"] <= d) & (sem["fim"] >= d)]
        linha = {"Dia": _rot_dia(d), "Semana": f"S{int(s['semana'].iloc[0])}" if not s.empty else ""}
        for c, nome in zip(com_meta["cesta"], com_meta["indicador"]):
            v = s[s["cesta"] == c]["por_dia"]
            linha[nome] = ui.numero(v.iloc[0]) if not v.empty else "—"
        linhas.append(linha)
    ui.tabela(pd.DataFrame(linhas), baixar="plano_dias_puxada")
    st.caption("Valor em HL por dia, pela meta da semana. Ao lançar o carregamento do dia, o que faltar é "
               "redistribuído nos dias seguintes da semana.")


def _semanas(usuario: dict, operacao_id: int, mes: str, p: dict) -> None:
    sem = p["semanas"]
    tema.secao("🗓️ Metas semanais",
               "Meta do mês dividida pelas semanas, na proporção dos dias de puxada. O gestor pode criticar a "
               "semana com um percentual a mais.")
    if sem.empty:
        return
    cards = []
    for n, g in sem.groupby("semana", sort=True):
        tot = g[g["cesta"].isin(CESTAS_TOTAL)]
        meta_aj, real = float(tot["meta_ajustada"].sum()), float(tot["real"].sum())
        pct = real / meta_aj * 100 if meta_aj else None
        cor = _cor(pct) if (g["fim"].iloc[0] < tempo.hoje() or g["atual"].iloc[0]) else "#2a78d6"
        aj = float(g["ajuste_pct"].iloc[0])
        cards.append(
            f'<div class="gd-card{" atual" if g["atual"].iloc[0] else ""}" style="--c:{cor}">'
            f'<div class="t"><span>S{n} · {g["ini"].iloc[0]:%d/%m}–{g["fim"].iloc[0]:%d/%m}</span>'
            f'<span>{int(g["dias_puxada"].iloc[0])} dia(s)</span></div>'
            f'<div class="v">{ui.numero(real)} / {ui.numero(meta_aj)}</div>'
            f'<div class="s">Cerveja + Nab (HL) · {ui.pct(pct) if pct is not None else "—"}'
            f'{" · semana atual" if g["atual"].iloc[0] else ""}</div>'
            f'<div class="gd-bar"><i style="width:{min(pct or 0, 100):.0f}%"></i></div>'
            + (f'<span class="aj">✏️ {aj:+.0f}% gestor</span>' if aj else "")
            + "</div>")
    st.markdown(_CSS + f'<div class="gd-sem">{"".join(cards)}</div>', unsafe_allow_html=True)

    opcoes = sorted(sem["semana"].unique())
    atual = sem[sem["atual"]]["semana"]
    escolha = st.pills("Semana", opcoes, key="gd_semana", selection_mode="single",
                       default=int(atual.iloc[0]) if not atual.empty else opcoes[0],
                       format_func=lambda n: f"S{n}", label_visibility="collapsed") or (
        int(atual.iloc[0]) if not atual.empty else opcoes[0])
    g = sem[sem["semana"] == escolha]
    ui.tabela(pd.DataFrame({
        "Indicador": g["indicador"],
        "Meta base (HL)": g["meta_base"].map(ui.numero),
        "Ajuste": g["ajuste_pct"].map(lambda v: f"{v:+.0f}%" if v else "—"),
        "Meta ajustada (HL)": g["meta_ajustada"].map(ui.numero),
        "Real (HL)": g["real"].map(ui.numero),
        "Falta (HL)": g["falta"].map(ui.numero),
        "Dias restantes": g["dias_restantes"],
        "Precisa/dia (HL)": g["por_dia"].map(ui.numero),
        "Atingimento": [float(a) if a is not None and a == a else None for a in g["ating"]],
    }), column_config={"Atingimento": st.column_config.ProgressColumn("Atingimento", format="%.0f%%",
                                                                       min_value=0, max_value=120)},
        baixar=f"metas_semanais_{mes}_S{escolha}")
    obs = g["observacao"].iloc[0] if not g.empty else ""
    if obs:
        st.caption(f"📝 Crítica do gestor: {obs} — {g['ajustado_por'].iloc[0]}")

    if not _gestor(usuario):
        st.caption("🔒 O ajuste das metas semanais é feito pelos gestores.")
        return
    with st.expander("✏️ Criticar metas semanais (gestor) — percentual a mais por semana"):
        st.caption("Ex.: +10% na semana 2 aumenta a meta de todos os indicadores dessa semana em 10%. "
                   "Use valor negativo para reduzir.")
        semanas = sem.drop_duplicates("semana")
        with st.form(f"gd_aj_{mes}"):
            valores = {}
            for r in semanas.itertuples():
                a, b = st.columns([1, 3])
                valores[r.semana] = (r.ini, a.number_input(
                    f"S{r.semana} · {r.ini:%d/%m}–{r.fim:%d/%m} (%)", min_value=-50.0, max_value=100.0, step=1.0,
                    value=float(r.ajuste_pct), key=f"gd_pct_{mes}_{r.semana}"),
                    b.text_input("Motivo / crítica", value=r.observacao, key=f"gd_obs_{mes}_{r.semana}"))
            if st.form_submit_button("💾 Salvar metas semanais", type="primary"):
                try:
                    for ini, pct, ob in valores.values():
                        svc.salvar_ajuste(operacao_id, mes, ini, pct, ob, usuario.get("nome") or "")
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    ui.avisar("Metas semanais atualizadas — a gestão do dia já recalculou.")
                    st.rerun()


def _dias_sem_puxada(usuario: dict, operacao_id: int, mes: str, p: dict) -> None:
    dias = svc.dias_do_mes(mes)
    fora = p["sem_puxada"]
    with st.expander(f"🚫 Dias sem puxada · {len(fora)} marcado(s)"
                     + (": " + ", ".join(_rot_dia(d) for d in fora[:8]) + ("…" if len(fora) > 8 else "") if fora else "")):
        st.caption("Marque os dias em que não haverá puxada (feriado, domingo, parada...). As metas semanais, "
                   "o “precisa por dia” e a tendência são recalculados só com os dias de puxada.")
        if not _gestor(usuario):
            st.caption("🔒 Somente gestores alteram o calendário.")
            return
        k = f"gd_fora_{operacao_id}_{mes}"
        st.session_state.setdefault(k, list(fora))
        b1, b2, _ = st.columns([1, 1, 2])
        if b1.button("➕ Todos os domingos", key=f"{k}_dom"):
            st.session_state[k] = sorted(set(st.session_state[k]) | {d for d in dias if d.weekday() == 6})
        if b2.button("🧹 Limpar", key=f"{k}_limpar"):
            st.session_state[k] = []
        sel = st.multiselect("Dias sem puxada", dias, key=k, format_func=_rot_dia)
        if st.button("💾 Salvar dias sem puxada", type="primary", key=f"{k}_ok"):
            try:
                svc.salvar_dias_sem_puxada(operacao_id, mes, sel)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(f"Calendário salvo: {len(sel)} dia(s) sem puxada. Metas e tendência recalculadas.")
                st.rerun()
