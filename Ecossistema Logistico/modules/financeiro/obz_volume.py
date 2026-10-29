"""Financeiro › 🧮 Planejamento & orçamento › 🍺 Volume planejado — o diretor preenche o HL de cada mês do próximo
ano, por revenda. Esse volume pondera o orçamento do OBZ: cada conta × departamento recebe, em cada mês, a parte
proporcional ao HL planejado (mês que entrega mais, custa mais), e os custos variáveis acompanham o HL do mês."""
import html as _h

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import graficos, tema, tempo, ui
from modules.financeiro.obz_painel import AZUL, VERDE, _mk, _p
from repositories import operacoes_repo
from services import obz_sim_service as sim

_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _revendas(usuario: dict) -> list[dict]:
    from core.auth import operacoes_permitidas

    return [o for o in operacoes_permitidas(usuario) if not operacoes_repo.e_consolidada(o["id"])]


def render(usuario: dict, operacao_id: int) -> None:
    from modules.financeiro.obz_sim import _passo

    revs = _revendas(usuario)
    if not revs:
        st.info("Nenhuma revenda liberada para você.")
        return
    pode = sim.pode_volume(usuario)
    prox = tempo.hoje().year + 1
    c1, c2 = st.columns([0.8, 3])
    ano = c1.selectbox("Ano do orçamento", [str(prox), str(prox - 1), str(prox + 1)], key="vol_ano")
    nomes = {o["id"]: o["nome"] for o in revs}
    ids = list(nomes)
    padrao = operacao_id if operacao_id in nomes else ids[0]
    if st.session_state.get("vol_op") not in ids:
        st.session_state["vol_op"] = padrao
    with c2:
        op = st.pills("Revenda", ids, key="vol_op", format_func=lambda i: f"🏢 {nomes[i]}", selection_mode="single")
    op = op if op in nomes else padrao
    a1, a2 = str(int(ano) - 1), str(int(ano) - 2)
    v = sim.volume_diretor(op, ano)
    preench = int(v["hl"].notna().sum())
    tot, ref = float(v["hl"].sum()), float(v["ref"].sum())
    quem = v.dropna(subset=["por"]).sort_values("em").tail(1)
    _passo("🍺", f"Volume planejado de {ano} — {nomes[op]}",
           "O diretor preenche o HL que vamos entregar em cada mês. O orçamento do OBZ é ponderado por esse volume: "
           "cada departamento e conta recebe, mês a mês, a parte do ano proporcional ao HL do mês.",
           [("✏️ você pode preencher" if pode else "🔒 só o diretor preenche", "ok" if pode else "lk"),
            (f"{preench}/12 meses preenchidos", "ok" if preench == 12 else "at"),
            (f"HL {ano}: {ui.numero(tot)}", ""), (f"{_p((tot / ref - 1) * 100 if ref and tot else None)} vs referência", ""),
            *([(f"por {quem['por'].iloc[0]} em {pd.to_datetime(quem['em'].iloc[0]).strftime('%d/%m %H:%M')}", "")]
              if not quem.empty else [])])

    # gráfico: 2 anos atrás, ano anterior, planejado e o peso de cada mês no orçamento
    x = _MESES
    plan_ou_ref = [h if pd.notna(h) else None for h in v["hl"]]
    tot_p = sum(h for h in plan_ou_ref if h) or 0
    fig = go.Figure()
    fig.add_bar(x=x, y=v["hl_ant2"], name=f"HL {a2}", marker_color="#e3e8f0")
    fig.add_bar(x=x, y=v["hl_ant"], name=f"HL {a1} (real)", marker_color="#9aa3b2")
    fig.add_bar(x=x, y=v["hl"], name=f"HL {ano} planejado", marker_color=AZUL)
    if tot_p:
        fig.add_scatter(x=x, y=[(h or 0) / tot_p * 100 for h in plan_ou_ref], name="Peso no orçamento (%)",
                        yaxis="y2", mode="lines+markers", line=dict(color=VERDE))
    fig.update_layout(barmode="group", yaxis2=dict(overlaying="y", side="right", showgrid=False, ticksuffix="%"))
    graficos.mostrar(graficos._layout(fig, f"HL mês a mês — {nomes[op]}", 340), key="vol_g")

    sem_ref = [m for m, r in zip(_MESES, v["ref"]) if pd.isna(r)]
    sem_plan = [m for m, h in zip(_MESES, v["hl"]) if pd.isna(h)]
    if sem_plan:
        st.warning(f"✏️ Faltam {len(sem_plan)} mês(es) de {ano}: {', '.join(sem_plan)}. Preencha à mão — não usamos "
                   "média, cada mês vende diferente (fim de ano vende mais)."
                   + (f" {', '.join(sem_ref)} de {a1} ainda não têm venda: use o HL de {a2} da tabela como guia."
                      if sem_ref else ""))
    if pode:
        with st.container(border=True):
            st.markdown(f"**⚡ Preencher rápido** — crescimento sobre o vendido de {a1} (mantém a sazonalidade). Meses "
                        f"sem venda em {a1} ficam em branco para preencher à mão.")
            k1, k2, _ = st.columns([1, 1.2, 2])
            cr = k1.number_input("Crescimento (%)", value=0.0, step=0.5, key=f"vol_cr_{op}_{ano}")
            if k2.button("Aplicar nos 12 meses", key=f"vol_cr_ap_{op}_{ano}", **ui.LARGURA):
                st.session_state[f"vol_sug_{op}_{ano}"] = [round(r * (1 + cr / 100), 0) if pd.notna(r) else
                                                          (h if pd.notna(h) else None)
                                                          for r, h in zip(v["ref"], v["hl"])]
                st.session_state.pop(f"vol_ed_{op}_{ano}", None)
                st.rerun()
    sug = st.session_state.get(f"vol_sug_{op}_{ano}")
    tab = pd.DataFrame({
        "Mês": [f"{m}/{ano}" for m in _MESES], "hl_ant2": v["hl_ant2"], "hl_ant": v["hl_ant"],
        "ref": v["ref"], "hl": sug if sug else v["hl"]})
    din = st.column_config.NumberColumn
    with st.container(border=True):
        st.markdown(f"**🍺 HL planejado de {ano} — mês a mês**" + (" · *sugestão aplicada, confira e salve*"
                                                                     if sug else ""))
        novo = st.data_editor(tab, hide_index=True, key=f"vol_ed_{op}_{ano}", **ui.LARGURA, height=13 * 35 + 3,
                              disabled=[c for c in tab.columns if c != "hl"] if pode else list(tab.columns),
                              column_config={"hl_ant2": din(f"HL {a2}", format="%.0f"),
                                             "hl_ant": din(f"HL {a1} (real)", format="%.0f"),
                                             "ref": din("Referência", format="%.0f",
                                                        help=f"Vendido em {a1}; mês sem venda fica em branco"),
                                             "hl": din(f"HL {ano} planejado ✏️", format="%.0f", min_value=0)})
        tn, tr = float(pd.to_numeric(novo["hl"], errors="coerce").sum()), float(v["ref"].sum())
        tot_n = pd.to_numeric(novo["hl"], errors="coerce")
        st.markdown(" · ".join([f"**Total {ano}: {ui.numero(tn)} HL**", f"referência {ui.numero(tr)}",
                                f"{_p((tn / tr - 1) * 100 if tr and tn else None)}",
                                f"média/mês {ui.numero(tn / max(int(tot_n.notna().sum()), 1))}"]))
        if pode:
            b1, b2 = st.columns([1, 3])
            if b1.button("💾 Salvar volume", type="primary", key=f"vol_s_{op}_{ano}", **ui.LARGURA):
                vals = {f"{ano}-{i + 1:02d}": h for i, h in enumerate(pd.to_numeric(novo["hl"], errors="coerce"))}
                try:
                    r = sim.salvar_volume_diretor(op, ano, vals, usuario)
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))
                else:
                    st.session_state.pop(f"vol_sug_{op}_{ano}", None)
                    msg = "Volume salvo."
                    if r["aplicado"]:
                        msg += " Orçamento recalculado: " + ", ".join(r["aplicado"]) + "."
                    if r["pendente"]:
                        msg += (" Simulador em outra etapa (vale quando voltar para a montagem): "
                                + ", ".join(r["pendente"]) + ".")
                    ui.avisar(msg)
                    st.rerun()
            b2.caption("Ao salvar, os simuladores desta revenda/ano em montagem são recalculados com este volume.")

    _impacto(op, ano, nomes[op])
    _todas(ano, revs)


def _impacto(op: int, ano: str, nome: str) -> None:
    """Como fica o orçamento mês a mês por departamento com este volume (simulador da revenda/ano)."""
    sims = sim.listar(op)
    sims = sims[sims["ano"].astype(str) == str(ano)] if not sims.empty else sims
    tema.secao(f"🏢 Orçamento {ano} por departamento, mês a mês — {nome}",
               "Ponderado pelo volume planejado. Abra o 🧮 Simulador OBZ para ver as contas.")
    if sims.empty:
        st.info(f"Ainda não há simulador de {ano} para {nome}. Quando o financeiro criar, ele já nasce com este volume.")
        return
    s = sim.buscar(int(sims["id"].iloc[0]))
    v = sim.mensal_area(s["id"])
    if v.empty:
        st.info("Simulador sem contas.")
        return
    ms = [f"{ano}-{m:02d}" for m in range(1, 13)]
    pv = v.pivot_table(index="area", columns="mes", values="liq", aggfunc="sum").reindex(columns=ms).fillna(0.0)
    pv = pv.loc[pv.sum(axis=1).sort_values(ascending=False).index]
    out = pd.DataFrame({"Departamento": list(pv.index)})
    for m in ms:
        out[_MESES[int(m[5:]) - 1]] = [_mk(x) for x in pv[m]]
    out["Ano"] = [_mk(x) for x in pv.sum(axis=1)]
    out.loc[len(out)] = ["TOTAL", *[_mk(pv[m].sum()) for m in ms], _mk(pv.values.sum())]
    st.caption(f"Simulador: **{_h.escape(s['nome'])}** · {sim.ETAPAS.get(s['status'], s['status'])}")
    ui.tabela(out, baixar=f"orcamento_{ano}_{nome}_mensal")


def _todas(ano: str, revs: list[dict]) -> None:
    if len(revs) < 2:
        return
    d = sim.volume_revendas(ano, [o["id"] for o in revs])
    tema.secao(f"🌐 Todas as revendas — HL planejado {ano}")
    ms = [f"{ano}-{m:02d}" for m in range(1, 13)]
    nomes = [o["nome"] for o in revs]
    pv = (d.pivot_table(index="revenda", columns="mes", values="hl", aggfunc="sum") if not d.empty
          else pd.DataFrame()).reindex(index=nomes, columns=ms)
    out = pd.DataFrame({"Revenda": nomes})
    for m in ms:
        out[_MESES[int(m[5:]) - 1]] = [ui.numero(x) if pd.notna(x) else "—" for x in pv[m]]
    out["Total"] = [ui.numero(x) for x in pv.sum(axis=1)]
    out["Meses"] = [f"{int(n)}/12" for n in pv.notna().sum(axis=1)]
    out.loc[len(out)] = ["TOTAL", *[ui.numero(pv[m].sum()) for m in ms], ui.numero(pv.values[~pd.isna(pv.values)].sum()),
                         ""]
    ui.tabela(out, baixar=f"volume_planejado_{ano}")
