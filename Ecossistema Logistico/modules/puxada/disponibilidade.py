"""Puxada › Frota própria › 🗓️ Disponibilidade de placas (hoje + 3 dias)."""
import html

import pandas as pd
import streamlit as st

from config.settings import STATUS_DISPONIBILIDADE
from core import tema, ui
from modules.componentes.autosave import editor_autosave
from services import disponibilidade_service as svc

AUTO = "↺ Automático"
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _rot(d) -> str:
    return f"{DIAS_SEMANA[d.weekday()]} {d:%d/%m}"


def _grade_html(g: pd.DataFrame, ds) -> None:
    cab = "".join(f"<th>{html.escape(_rot(d))}{' · hoje' if i == 0 else ''}</th>" for i, d in enumerate(ds))
    linhas = []
    for placa, grupo in g.groupby("placa", sort=True):
        info = grupo.iloc[0]
        cel = []
        for d in ds:
            r = grupo[grupo["data"] == d].iloc[0]
            cor = svc.CORES.get(r["status"], "#898781")
            marca = " ✋" if r["manual"] else ""
            cel.append(f'<td><span class="disp-chip" style="--c:{cor}">{html.escape(r["status"])}{marca}</span>'
                       f'<div class="disp-obs">{html.escape(r["observacao"] or "")}</div></td>')
        cap = f" · {ui.numero(info['capacidade_hl'])} HL" if info.get("capacidade_hl") else ""
        linhas.append(f'<tr><td><b>{html.escape(str(placa))}</b><div class="disp-obs">'
                      f'{html.escape(str(info.get("modelo") or ""))}{cap}</div></td>{"".join(cel)}</tr>')
    st.markdown(f"""<style>
.disp-chip {{ display:inline-block; padding:.15rem .6rem; border-radius:999px; font-weight:700; font-size:.82rem;
  color: var(--c); background: color-mix(in srgb, var(--c) 13%, white); border:1px solid color-mix(in srgb, var(--c) 40%, white); }}
.disp-obs {{ font-size:.75rem; color:#6b6a65; margin-top:.15rem; }}
</style><div class="eco-tab"><table><thead><tr><th>Placa</th>{cab}</tr></thead><tbody>{''.join(linhas)}</tbody>
</table></div>""", unsafe_allow_html=True)


def render(usuario: dict, operacao_id: int) -> None:
    ds = svc.dias()
    g = svc.grade(operacao_id)
    if g.empty:
        st.info("Cadastre as placas da frota própria em **⚙️ Cadastros › 🚛 Carretas**.")
        return
    total = g["placa"].nunique()
    cards = []
    for i, d in enumerate(ds):
        dia = g[g["data"] == d]
        disp = dia[dia["status"] == "Disponível"]
        pct = len(disp) / total * 100 if total else 0
        cards.append({"titulo": ("Hoje · " if i == 0 else "") + _rot(d), "valor": f"{len(disp)} de {total}",
                      "icone": "🚛", "detalhe": "placas disponíveis",
                      "status": "bom" if pct >= 50 else "atencao" if pct > 0 else "critico",
                      "dados": dia[["placa", "status", "observacao"]].sort_values("status"),
                      "colunas": {"placa": "Placa", "status": "Status", "observacao": "Observação"}})
    tema.kpis(cards, key="kp_disp")
    tema.secao("Grade de disponibilidade",
               "Automática pelo App Carreteiro (em viagem até o dia da chegada agendada) e pelo status da carreta. "
               "✋ = planejado à mão.")
    _grade_html(g, ds)

    tema.secao("✏️ Planejar", "Escolha o status de cada placa por dia — salva sozinho. "
               f"“{AUTO}” volta para o cálculo automático.")
    tab = g.pivot(index="placa", columns="data", values="status").reset_index()
    manual = g.pivot(index="placa", columns="data", values="manual").reset_index()
    for d in ds:
        tab[d] = [st_ if m else AUTO for st_, m in zip(tab[d], manual[d])]
    tab.columns = ["placa"] + [_rot(d) for d in ds]
    por_rotulo = {_rot(d): d for d in ds}

    def alterar(linha, alt):
        for col, valor in alt.items():
            if col in por_rotulo:
                svc.planejar(operacao_id, linha["placa"], por_rotulo[col], None if valor in (AUTO, None) else valor,
                             "", usuario.get("nome") or "")

    editor_autosave(tab, f"ed_disp_{operacao_id}_{ds[0]}", list(por_rotulo), alterar, column_config={
        "placa": st.column_config.TextColumn("Placa", disabled=True),
        **{r: st.column_config.SelectboxColumn(r + " ✏️", options=[AUTO, *STATUS_DISPONIBILIDADE]) for r in por_rotulo}})
    with st.expander("📝 Planejar com observação (ex.: pedido programado, motorista escalado)"):
        with st.form("f_disp_obs", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            placa = c1.selectbox("Placa", sorted(g["placa"].unique()))
            dia = c2.selectbox("Dia", ds, format_func=_rot)
            status = c3.selectbox("Status", STATUS_DISPONIBILIDADE, index=STATUS_DISPONIBILIDADE.index("Programada"))
            obs = st.text_input("Observação")
            if st.form_submit_button("💾 Salvar", type="primary"):
                ui.acao(svc.planejar, operacao_id, placa, dia, status, obs, usuario.get("nome") or "",
                        sucesso="Planejamento salvo.")
    ui.downloads(g.assign(data=g["data"].map(lambda d: d.strftime("%d/%m/%Y"))), "disponibilidade_placas",
                 key="dl_disp")
