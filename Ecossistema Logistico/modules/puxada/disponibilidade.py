"""Puxada › Frota própria › 🗓️ Disponibilidade de placas (hoje + 3 dias).

Clique no card do dia → aparecem todas as placas para o gestor da Puxada escolher o status
(Disponível · Indisponível Frota · Indisponível Viagem) e, se disponível, a sugestão de pedido
(Retornável ou Descartável). Isso aparece para o Ressuprimento.
"""
import html

import pandas as pd
import streamlit as st

from config.settings import STATUS_DISPONIBILIDADE, SUGESTAO_PEDIDO
from core import tema, ui
from services import disponibilidade_service as svc

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
ICONE = {"Disponível": "🟢", "Indisponível Frota": "🔧", "Indisponível Viagem": "🛣️"}
ICONE_SUG = {"Retornável": "♻️", "Descartável": "🥫"}


def _rot(d) -> str:
    return f"{DIAS_SEMANA[d.weekday()]} {d:%d/%m}"


def _perfil_txt(p) -> str:
    from config.settings import PERFIS_VEICULO

    if not isinstance(p, str) or not p or p == "Sem perfil":
        return "sem perfil"
    return f"{p} · {PERFIS_VEICULO.get(p, '?')} pal."


def _txt(v) -> str:
    return v if isinstance(v, str) else ""


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
            sug = _txt(r.get("sugestao"))
            sug_html = f'<div class="disp-sug">{ICONE_SUG.get(sug, "")} sugestão: <b>{html.escape(sug)}</b></div>' if sug else ""
            ped = _txt(r.get("pedidos"))
            ped_html = f'<div class="disp-ped">📋 {html.escape(ped)}</div>' if ped else ""
            cel.append(f'<td><span class="disp-chip" style="--c:{cor}">{ICONE.get(r["status"], "")} '
                       f'{html.escape(r["status"])}{marca}</span>{sug_html}{ped_html}'
                       f'<div class="disp-obs">{html.escape(_txt(r["observacao"]))}</div></td>')
        cap = f" · {ui.numero(info['capacidade_hl'])} HL" if info.get("capacidade_hl") else ""
        linhas.append(f'<tr><td><b>{html.escape(str(placa))}</b> <span class="disp-perfil">'
                      f'{html.escape(_perfil_txt(info.get("perfil")))}</span><div class="disp-obs">'
                      f'{html.escape(_txt(info.get("modelo")))}{cap}</div></td>{"".join(cel)}</tr>')
    st.markdown(f"""<style>
.disp-chip {{ display:inline-block; padding:.15rem .6rem; border-radius:999px; font-weight:700; font-size:.8rem;
  color: var(--c); background: color-mix(in srgb, var(--c) 12%, white); border:1px solid color-mix(in srgb, var(--c) 40%, white); }}
.disp-sug {{ font-size:.76rem; color:#0f5132; margin-top:.2rem; }}
.disp-ped {{ font-size:.74rem; color:#2a5ca8; margin-top:.15rem; }}
.disp-obs {{ font-size:.74rem; color:#6b6a65; margin-top:.15rem; }}
.disp-perfil {{ display:inline-block; font-size:.7rem; font-weight:800; padding:.05rem .45rem; border-radius:6px;
  background:#eef3fa; color:#2a5ca8; margin-left:.25rem; }}
</style><div class="eco-tab"><table><thead><tr><th>Placa</th>{cab}</tr></thead><tbody>{''.join(linhas)}</tbody>
</table></div>""", unsafe_allow_html=True)


def _resumo(g: pd.DataFrame, ds) -> None:
    """Resumo do dia aberto por perfil (9 eixos / LS) + flag para listar as placas disponíveis."""
    tema.secao("📊 Resumo da disponibilidade por perfil", "Aberto pelo perfil cadastrado em ⚙️ Cadastros › 🚛 Carretas.")
    rot = {d.isoformat(): ("Hoje · " if i == 0 else "") + _rot(d) for i, d in enumerate(ds)}
    esc = ui._escolha("disp_res_dia", list(rot), ds[0].isoformat(), formatar=rot.get, pills=True)
    d = next(x for x in ds if x.isoformat() == esc)
    res = svc.resumo_por_perfil(g, d)
    if res.empty:
        return
    linhas = []
    for r in res.to_dict("records"):
        cap = f" · {r['paletes']} paletes" if r.get("paletes") else ""
        linhas.append(
            f"<tr><td><b>{html.escape(r['perfil'])}</b><span class='disp-obs'>{cap}</span></td>"
            f"<td><b style='color:#0ca30c'>{r['disponivel']}</b> de {r['total']}</td>"
            f"<td>♻️ {r['retornavel']}</td><td>🥫 {r['descartavel']}</td><td>{r['sem_sugestao'] or '—'}</td>"
            f"<td>🔧 {r['ind_frota']}</td><td>🛣️ {r['ind_viagem']}</td></tr>")
    tot = res[["total", "disponivel", "retornavel", "descartavel", "sem_sugestao", "ind_frota", "ind_viagem"]].sum()
    linhas.append(f"<tr style='background:#eef3fa'><td><b>Total</b></td><td><b>{tot['disponivel']}</b> de {tot['total']}"
                  f"</td><td><b>♻️ {tot['retornavel']}</b></td><td><b>🥫 {tot['descartavel']}</b></td>"
                  f"<td>{tot['sem_sugestao'] or '—'}</td><td>🔧 {tot['ind_frota']}</td><td>🛣️ {tot['ind_viagem']}</td></tr>")
    st.markdown('<div class="eco-tab"><table><thead><tr><th>Perfil</th><th>Disponíveis</th><th>Sugestão retornável</th>'
                '<th>Sugestão descartável</th><th>Sem sugestão</th><th>Indisp. frota</th><th>Indisp. viagem</th>'
                f'</tr></thead><tbody>{"".join(linhas)}</tbody></table></div>', unsafe_allow_html=True)
    if st.toggle(f"🚛 Mostrar as placas disponíveis em {_rot(d)}", key=f"disp_flag_{esc}"):
        dia = g[(g["data"] == d) & (g["status"] == "Disponível")].sort_values(["perfil", "placa"])
        if dia.empty:
            st.info("Nenhuma placa disponível neste dia.")
        else:
            itens = []
            for r in dia.to_dict("records"):
                sug = r.get("sugestao") if isinstance(r.get("sugestao"), str) else ""
                itens.append(f'<span class="disp-chip" style="--c:#0ca30c">🚛 {html.escape(str(r["placa"]))} · '
                             f'{html.escape(_perfil_txt(r.get("perfil")))}'
                             f'{" · " + ICONE_SUG.get(sug, "") + " " + sug if sug else ""}</span>')
            st.markdown('<div style="display:flex;flex-wrap:wrap;gap:.4rem;margin:.3rem 0 .8rem">'
                        + "".join(itens) + "</div>", unsafe_allow_html=True)


@st.dialog("🗓️ Placas do dia", width="large")
def _dialogo_dia(operacao_id: int, d, usuario: dict) -> None:
    g = svc.grade(operacao_id)
    dia = g[g["data"] == d].sort_values("placa")
    st.markdown(f"#### {_rot(d)} — {len(dia)} placa(s)")
    st.caption("Escolha o status de cada placa. Se estiver **Disponível**, marque a sugestão de pedido — "
               "ela aparece para o Ressuprimento. ✋ = já definido pela Puxada; sem ✋ = cálculo automático.")
    linhas = []
    k = f"dd_{operacao_id}_{d}"
    for r in dia.to_dict("records"):
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.2, 1.5, 1.6])
            c1.markdown(f"**🚛 {html.escape(str(r['placa']))}**{' ✋' if r['manual'] else ''} "
                        f"<span class='disp-perfil'>{html.escape(_perfil_txt(r.get('perfil')))}</span>  \n"
                        f"<span style='font-size:.78rem;color:#6b6a65'>{html.escape(_txt(r['observacao']))}"
                        f"{(' · 📋 ' + html.escape(_txt(r.get('pedidos')))) if _txt(r.get('pedidos')) else ''}</span>",
                        unsafe_allow_html=True)
            status = c2.selectbox("Status", STATUS_DISPONIBILIDADE, key=f"{k}_s_{r['placa']}",
                                  index=STATUS_DISPONIBILIDADE.index(r["status"]) if r["status"] in STATUS_DISPONIBILIDADE
                                  else 0, format_func=lambda s: f"{ICONE.get(s, '')} {s}")
            sug = None
            if status == "Disponível":
                atual = _txt(r.get("sugestao"))
                sug = c3.radio("Sugestão de pedido", SUGESTAO_PEDIDO, horizontal=True, key=f"{k}_g_{r['placa']}",
                               index=SUGESTAO_PEDIDO.index(atual) if atual in SUGESTAO_PEDIDO else None,
                               format_func=lambda s: f"{ICONE_SUG.get(s, '')} {s}")
            else:
                c3.caption("Sem sugestão — placa indisponível.")
            obs_padrao = _txt(r["observacao"]) if r["manual"] else ""
            obs = st.text_input("Observação", value=obs_padrao, key=f"{k}_o_{r['placa']}",
                                placeholder="opcional (ex.: motorista escalado, manutenção até 14h)",
                                label_visibility="collapsed")
            linhas.append({"placa": r["placa"], "status": status, "sugestao": sug, "observacao": obs})
    perfis = {r["placa"]: r.get("perfil") or "Sem perfil" for r in dia.to_dict("records")}
    cont: dict = {}
    for l in linhas:
        c = cont.setdefault(perfis.get(l["placa"], "Sem perfil"), {"disp": 0, "tot": 0, "ret": 0, "desc": 0})
        c["tot"] += 1
        if l["status"] == "Disponível":
            c["disp"] += 1
            c["ret"] += l["sugestao"] == "Retornável"
            c["desc"] += l["sugestao"] == "Descartável"
    st.markdown("**📊 Resumo do dia:** " + " · ".join(
        f"**{p}**: {c['disp']} de {c['tot']} disponível(is) (♻️ {c['ret']} · 🥫 {c['desc']})" for p, c in cont.items()))
    sem_sug = [l["placa"] for l in linhas if l["status"] == "Disponível" and not l["sugestao"]]
    if sem_sug:
        st.caption("ℹ️ Disponíveis sem sugestão: " + ", ".join(sem_sug))
    if st.button(f"💾 Salvar {_rot(d)}", type="primary", key=f"{k}_salvar", **ui.LARGURA):
        n = svc.salvar_dia(operacao_id, d, linhas, usuario.get("nome") or "")
        ui.avisar(f"Disponibilidade de {_rot(d)} salva ({n} placa(s) alterada(s)).")
        st.rerun()


def render(usuario: dict, operacao_id: int) -> None:
    ds = svc.dias()
    g = svc.grade(operacao_id)
    if g.empty:
        st.info("Cadastre as placas da frota própria em **⚙️ Cadastros › 🚛 Carretas**.")
        return
    total = g["placa"].nunique()
    editar = not ui.somente_leitura(operacao_id)
    cards = []
    for i, d in enumerate(ds):
        dia = g[g["data"] == d]
        disp = dia[dia["status"] == "Disponível"]
        ret = int((disp["sugestao"] == "Retornável").sum())
        desc = int((disp["sugestao"] == "Descartável").sum())
        pct = len(disp) / total * 100 if total else 0
        det = (f"♻️ {ret} retornável · 🥫 {desc} descartável" if ret or desc else "placas disponíveis")
        cards.append({"titulo": ("Hoje · " if i == 0 else "") + _rot(d), "valor": f"{len(disp)} de {total}",
                      "icone": "🚛", "detalhe": det, "selo": "clique para editar" if editar else None,
                      "status": "bom" if pct >= 50 else "atencao" if pct > 0 else "critico",
                      **({"ao_clicar": (lambda d=d: _dialogo_dia(operacao_id, d, usuario))} if editar else
                         {"dados": dia[["placa", "status", "sugestao", "observacao"]].sort_values("status"),
                          "colunas": {"placa": "Placa", "status": "Status", "sugestao": "Sugestão",
                                      "observacao": "Observação"}})})
    tema.kpis(cards, key="kp_disp")
    _resumo(g, ds)
    tema.secao("Grade de disponibilidade",
               "Clique no card do dia para escolher o status das placas e a sugestão de pedido. "
               "Sem escolha, vale o automático: App Carreteiro (em viagem até a chegada agendada) e cadastro "
               "da carreta. ✋ = definido pela Puxada · 📋 = pedido lançado.")
    _grade_html(g, ds)
    ui.downloads(g.assign(data=g["data"].map(lambda d: d.strftime("%d/%m/%Y"))).drop(columns=["manual"]),
                 "disponibilidade_placas", key="dl_disp")
