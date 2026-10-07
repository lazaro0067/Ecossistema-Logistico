"""Pedidos D0 / D+1 da Puxada — uma tela para cada área, os mesmos dados:

  • 🚛 Puxada › 📋 Pedidos D0 / D+1 ........ o gestor lança: placa, nº do pedido, tipo e paletes
  • 🏬 Armazém › 📋 Gestão de Pedidos ....... o armazém confere e clica em ✅ Finalizado
  • 🔄 Ressuprimento › 🚛 Placas & Pedidos ... vê placas disponíveis, sugestões e pedidos (somente leitura)
"""
import datetime as dt
import html

import pandas as pd
import streamlit as st

from config.settings import EMBALAGENS_RETORNAVEL, SUGESTAO_PEDIDO
from core import tema, tempo, ui
from repositories import operacoes_repo
from repositories import pedidos_puxada_repo as repo
from services import disponibilidade_service as disp
from services import pedidos_puxada_service as svc
from services.erros import RegraNegocioError

ICONE_TIPO = {"Retornável": "♻️", "Descartável": "🥫"}
_CSS = """
<style>
.pp-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap:.75rem; margin:.4rem 0 .6rem; }
.pp-card { background:#fff; border:1px solid #dfe5ee; border-left:5px solid var(--c); border-radius:14px;
    padding:.75rem .9rem; box-shadow:0 1px 2px rgba(11,31,58,.05); }
.pp-card.cancelado { opacity:.55; }
.pp-top { display:flex; justify-content:space-between; align-items:center; gap:.5rem; }
.pp-top b { font-size:1.05rem; color:#0B1F3A; }
.pp-st { font-size:.72rem; font-weight:800; padding:.12rem .5rem; border-radius:999px; background:var(--f); color:var(--c); }
.pp-star { font-size:.68rem; font-weight:800; padding:.1rem .45rem; border-radius:999px; background:#fff4d6; color:#8a5a00; border:1px solid #f0c75e; margin-left:.3rem; vertical-align:middle; }
.pp-ped { font-size:.86rem; color:#3d3c39; margin-top:.1rem; }
.pp-tipo { display:inline-block; font-size:.74rem; font-weight:700; padding:.1rem .5rem; border-radius:999px;
    background:#eef3fa; color:#2a5ca8; margin:.35rem 0 .25rem; }
.pp-emb { display:grid; grid-template-columns: repeat(3, 1fr); gap:.3rem; margin-top:.2rem; }
.pp-emb div { background:#f6f8fb; border-radius:8px; padding:.25rem .3rem; text-align:center; font-size:.7rem; color:#5f6b7a; }
.pp-emb div b { display:block; font-size:1rem; color:#0B1F3A; }
.pp-emb div.zero b { color:#c3c2bc; }
.pp-ag { display:flex; flex-direction:column; gap:.05rem; font-size:.78rem; color:#3d3c39; margin:.15rem 0 .3rem; }
.pp-edit { background:#fff6d6; border:1px solid #f0c94d; border-radius:9px; padding:.35rem .5rem; margin:.35rem 0;
    font-size:.76rem; color:#7a5300; } .pp-edit span { color:#5f4a12; }
.pp-rod { font-size:.74rem; color:#77766f; margin-top:.4rem; }
.pp-placas { display:flex; flex-wrap:wrap; gap:.4rem; margin:.3rem 0 .8rem; }
.pp-placa { border:1.5px solid var(--c); border-radius:10px; padding:.3rem .6rem; font-size:.8rem; background:#fff; }
.pp-placa b { color:#0B1F3A; } .pp-placa span { color:var(--c); font-weight:700; }
</style>
"""
_COR_ST = {"Aberto": ("#b7791f", "#fdf3e1"), "Finalizado": ("#146c43", "#e8f6ee"), "Cancelado": ("#77766f", "#f0efec"),
           "Reprogramado": ("#5b3fc4", "#ece8fb")}


def _e(v) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))


def _f(v) -> str:
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return "0"
    return ui.numero(f, 0 if f == int(f) else 1)


def _card(r: dict, com_filial: bool = False) -> str:
    cor, fundo = _COR_ST.get(r["status"], ("#52514e", "#f0efec"))
    if r["tipo"] == "Retornável":
        corpo = '<div class="pp-emb">' + "".join(
            f'<div class="{"zero" if not svc._v(r.get(k)) else ""}"><b>{_f(r.get(k))}</b>'
            f'{_e(rot if k != "p_outros" or not isinstance(r.get("outros_desc"), str) else "Outros: " + r["outros_desc"])}</div>'
            for k, rot in EMBALAGENS_RETORNAVEL.items()) + "</div>"
    else:
        corpo = ""
    fim = ""
    if r["status"] == "Finalizado" and isinstance(r.get("finalizado_em"), str):
        d = tempo.parse_dt(r["finalizado_em"])
        fim = f" · ✅ {_e(r.get('finalizado_por'))} {d:%d/%m %H:%M}" if d else ""
    filial = f"🏢 {_e(r.get('filial'))} · " if com_filial else ""
    _, prio, cor_prio = svc.prioridade(r)
    ag, pz = svc.agendamento_dt(r), svc.prazo_saida(r)
    mot = r.get("motorista") if isinstance(r.get("motorista"), str) else ""
    viagem = " · 📱 viagem iniciada" if isinstance(r.get("viagem_status"), str) and r.get("viagem_status") else ""
    agenda = (f'<div class="pp-ag"><span>👤 {_e(mot) or "sem motorista"}{viagem}</span>'
              f'<span>🕒 slot na fábrica {f"{ag:%d/%m} {svc.janela_txt(r)}" if ag else "—"}</span>'
              f'<span style="color:{cor_prio}"><b>🚦 sair até {f"{pz:%d/%m %H:%M}" if pz else "—"} · {_e(prio)}</b>'
              f'</span></div>')
    fab = f" · 🏭 {_e(r['fabrica'])}" if isinstance(r.get("fabrica"), str) and r.get("fabrica") else ""
    obs = f"<br>📝 {_e(r.get('observacao'))}" if isinstance(r.get("observacao"), str) and r.get("observacao") else ""
    editado = ""
    if isinstance(r.get("editado_em"), str) and r.get("editado_em"):
        quando = tempo.parse_dt(r["editado_em"])
        editado = (f'<div class="pp-edit">✏️ <b>Editado</b> por {_e(r.get("editado_por"))} em '
                   f'{quando:%d/%m às %H:%M}<br><span>{_e(r.get("editado_resumo"))}</span></div>' if quando else "")
    reprog = ""
    if r["status"] == "Reprogramado":
        reprog = (f'<div class="pp-edit">🔁 <b>Reprogramado</b> — substituído por novo agendamento'
                  f'{": " + _e(r.get("reprogramado_motivo")) if isinstance(r.get("reprogramado_motivo"), str) else ""}</div>')
    elif svc._v(r.get("substitui_id")):
        reprog = '<div class="pp-edit">🔁 <b>Reprogramação</b> — substitui um agendamento anterior deste pedido</div>'
    editado = reprog + editado
    estrela = (' <span class="pp-star">⭐ PRIORIDADE</span>' if svc.e_prioritario(r)
               and r["status"] not in ("Cancelado", "Reprogramado") else "")
    return (f'<div class="pp-card {"cancelado" if r["status"] in ("Cancelado", "Reprogramado") else ""}" style="--c:{cor};--f:{fundo}">'
            f'<div class="pp-top"><b>🚛 {_e(r["placa"])}{estrela}</b><span class="pp-st">{svc.STATUS_ICONE.get(r["status"], "")} '
            f'{_e(r["status"])}</span></div><div class="pp-ped">Pedido <b>{_e(r["numero_pedido"])}</b>{fab} · '
            f'{_e(svc.rotulo_dia(dt.date.fromisoformat(str(r["data"])[:10])))}</div>'
            f'<span class="pp-tipo">{ICONE_TIPO.get(r["tipo"], "")} {_e(r["tipo"])} · {_f(r.get("paletes"))} palete(s)</span>'
            f'{editado}{agenda}{corpo}<div class="pp-rod">{filial}lançado por {_e(r.get("criado_por"))}{fim}{obs}</div></div>')


def _cards(df: pd.DataFrame, com_filial: bool = False) -> None:
    if df.empty:
        return
    regs = sorted(df.to_dict("records"), key=lambda r: (*svc.ordem_armazem(r), str(r["placa"])))
    st.markdown(_CSS + '<div class="pp-grid">' + "".join(_card(r, com_filial) for r in regs)
                + "</div>", unsafe_allow_html=True)


def _kpis(df: pd.DataFrame, chave: str, extra: list[dict] | None = None) -> None:
    r = svc.resumo(df)
    vis = svc.tabela(df)
    ret_txt = " · ".join(f"{rot.replace(' ml', '')} {_f(r[k])}" for k, rot in EMBALAGENS_RETORNAVEL.items() if r[k])
    tema.kpis([
        {"titulo": "Pedidos", "valor": r["pedidos"], "icone": "📋", "status": "info",
         "detalhe": f"{r['abertos']} aberto(s)", "dados": vis},
        {"titulo": "♻️ Retornável", "valor": f"{_f(r['ret'])} pal.", "icone": "", "status": "info",
         "detalhe": ret_txt or "nenhum palete",
         "dados": vis[vis["Tipo"] == "Retornável"] if not vis.empty else vis},
        {"titulo": "🥫 Descartável", "valor": f"{_f(r['desc'])} pal.", "icone": "", "status": "info",
         "dados": vis[vis["Tipo"] == "Descartável"] if not vis.empty else vis},
        {"titulo": "Finalizados pelo armazém", "valor": f"{r['finalizados']} de {r['pedidos']}", "icone": "✅",
         "status": "bom" if r["pedidos"] and r["finalizados"] == r["pedidos"] else "atencao" if r["pedidos"] else "neutro",
         "dados": vis[vis["Status"].str.contains("Finalizado")] if not vis.empty else vis},
        *(extra or []),
    ], key=chave)


def _placas_do_dia(operacao_id: int, d: dt.date) -> pd.DataFrame:
    g = disp.grade(operacao_id)
    return g[g["data"] == d] if not g.empty else g


def _chips_placas(dia: pd.DataFrame) -> None:
    if dia.empty:
        return
    itens = []
    for r in dia.sort_values(["status", "placa"]).to_dict("records"):
        cor = disp.CORES.get(r["status"], "#898781")
        sug = r.get("sugestao") if isinstance(r.get("sugestao"), str) else ""
        ped = r.get("pedidos") if isinstance(r.get("pedidos"), str) and r.get("pedidos") else ""
        extra = f" · {ICONE_TIPO.get(sug, '')} {sug}" if sug else ""
        itens.append(f'<div class="pp-placa" style="--c:{cor}"><b>{_e(r["placa"])}</b> <span>{_e(r["status"])}'
                     f'{_e(extra)}</span>{" · 📋" if ped else ""}</div>')
    st.markdown(_CSS + f'<div class="pp-placas">{"".join(itens)}</div>', unsafe_allow_html=True)


# --- Formulário (novo / alterar) ------------------------------------------------------------
def _form(usuario: dict, operacao_id: int, d: dt.date, atual: dict | None, chave: str) -> None:
    if not atual:  # data do agendamento: D0 a D+3
        ds = svc.dias_pedido()
        d = st.selectbox("📅 Data do agendamento *", ds, index=ds.index(d) if d in ds else 0,
                         format_func=svc.rotulo_dia, key=f"{chave}_data")
    dia = _placas_do_dia(operacao_id, d)
    info = {r["placa"]: r for r in dia.to_dict("records")} if not dia.empty else {}
    ordem = sorted(info, key=lambda p: (info[p]["status"] != "Disponível", p))
    if atual and atual["placa"] not in ordem:
        ordem.insert(0, atual["placa"])
    if not ordem:
        st.info("Cadastre as placas em **⚙️ Cadastros › 🚛 Carretas**.")
        return

    def rot_placa(p):
        r = info.get(p)
        if not r:
            return p
        sug = r.get("sugestao") if isinstance(r.get("sugestao"), str) else ""
        cap = svc.capacidade_paletes(operacao_id, p)
        return f"{p}{f' ({cap} pal.)' if cap else ''} · {r['status']}" + (f" · sugestão {sug}" if sug else "")

    from repositories import logistica_repo

    fabs = logistica_repo.fabricas_df()
    if fabs.empty:
        st.warning("Cadastre as fábricas em **⚙️ Cadastros › 🏭 Fábricas** para lançar pedidos.")
        return
    nomes_fab = {int(r["id"]): r["nome"] for r in fabs.to_dict("records")}
    c1, c2, c3 = st.columns([1.5, 1.3, 1])
    placa = c1.selectbox("🚛 Placa *", ordem, key=f"{chave}_placa", format_func=rot_placa,
                         index=ordem.index(atual["placa"]) if atual else 0)
    st_placa = info.get(placa, {}).get("status")
    if st_placa and st_placa != "Disponível":
        c1.caption(f"⚠️ Esta placa está **{st_placa}** em {d:%d/%m}.")
    numero = c3.text_input("Nº do(s) pedido(s) *", value=(atual or {}).get("numero_pedido") or "", key=f"{chave}_num",
                           placeholder="4501, 4502", help="Mais de um pedido no mesmo agendamento: separe por vírgula.")
    fab_atual = (atual or {}).get("fabrica_id")
    fab_atual = int(fab_atual) if fab_atual and int(fab_atual) in nomes_fab else None
    ids_fab = list(nomes_fab)
    fabrica_id = c2.selectbox("🏭 Fábrica *", ids_fab, format_func=nomes_fab.get, key=f"{chave}_fab",
                              index=ids_fab.index(fab_atual) if fab_atual else (0 if len(ids_fab) == 1 else None),
                              placeholder="Selecione a fábrica...")
    mots = logistica_repo.motoristas_df(operacao_id)
    nomes_mot = {int(r["id"]): r["nome"] for r in mots.to_dict("records")} if not mots.empty else {}
    if not nomes_mot:
        st.warning("Cadastre os motoristas em **⚙️ Cadastros › 👤 Motoristas** para lançar pedidos.")
        return
    m1, m2, m3 = st.columns([1.5, 1.3, 1])
    mot_atual = (atual or {}).get("motorista_id")
    mot_atual = int(mot_atual) if mot_atual and int(mot_atual) in nomes_mot else None
    from services import disp_motoristas_service as dms

    gm = dms.grade(operacao_id)
    sit = {int(r["id"]): r for r in gm[gm["data"] == d].to_dict("records")} if not gm.empty else {}
    ids_mot = sorted(nomes_mot, key=lambda i: (sit.get(i, {}).get("status", "Disponível") != "Disponível", nomes_mot[i]))

    def rot_mot(i):
        s_ = sit.get(i)
        if not s_:
            return nomes_mot[i]
        extra = f" · {s_['detalhe']}" if s_["status"] != "Disponível" or "a partir" in str(s_["detalhe"]) else ""
        return f"{dms.ICONES.get(s_['status'], '')} {nomes_mot[i]} · {s_['status']}{extra}"

    motorista_id = m1.selectbox("👤 Motorista *", ids_mot, format_func=rot_mot, key=f"{chave}_mot",
                                index=ids_mot.index(mot_atual) if mot_atual else None,
                                placeholder="Selecione o motorista...")
    def _t(v):
        return dt.datetime.strptime(v, "%H:%M").time() if isinstance(v, str) and v else None

    hora_ag = m2.time_input(f"🕒 Slot na fábrica ({d:%d/%m}) — início *", value=_t((atual or {}).get("hora_agendamento")),
                            step=dt.timedelta(minutes=15), key=f"{chave}_hora")
    hora_fim = m3.time_input("até (fim do slot)", value=_t((atual or {}).get("hora_agendamento_fim")),
                             step=dt.timedelta(minutes=15), key=f"{chave}_hora_fim")
    if hora_ag and fabrica_id:
        desl = logistica_repo.deslocamento_h(operacao_id, fabrica_id)
        pz = svc.prazo_saida({"data": d.isoformat(), "hora_agendamento": hora_ag.strftime("%H:%M"),
                              "deslocamento_h": desl})
        st.markdown(f"🚦 **Sair da revenda até {pz:%d/%m %H:%M}** (início do slot − {ui.numero(desl, 1)} h de "
                    "deslocamento)" if desl else "🚦 Prazo de saída: sem deslocamento cadastrado para esta fábrica.")
        if motorista_id and pz:
            s_mot = dms.no_momento(operacao_id, int(motorista_id), pz)
            if s_mot["status"] != "Disponível":
                st.warning(f"⚠️ {nomes_mot[int(motorista_id)]} estará **{s_mot['status']}** na saída "
                           f"({pz:%d/%m %H:%M}): {s_mot['detalhe']}.")
        if not desl:
            st.caption("Informe em ⚙️ Cadastros › 🏭 Fábricas.")
    sug = info.get(placa, {}).get("sugestao")
    padrao = (atual or {}).get("tipo") or (sug if sug in SUGESTAO_PEDIDO else None)
    tipo = st.radio("Tipo *", SUGESTAO_PEDIDO, horizontal=True, key=f"{chave}_tipo_{placa}",
                    index=SUGESTAO_PEDIDO.index(padrao) if padrao in SUGESTAO_PEDIDO else None,
                    format_func=lambda t: f"{ICONE_TIPO.get(t, '')} {t}")
    qtds, paletes, outros_desc = {}, 0.0, None
    if tipo == "Retornável":
        st.markdown("**♻️ Paletes por embalagem**")
        cols = st.columns(len(EMBALAGENS_RETORNAVEL))
        for col, (k, rot) in zip(cols, EMBALAGENS_RETORNAVEL.items()):
            qtds[k] = col.number_input(rot, min_value=0.0, step=1.0, format="%.0f", key=f"{chave}_{k}",
                                       value=svc._v((atual or {}).get(k)))
        if qtds.get("p_outros"):
            outros_desc = st.text_input("Qual vasilhame em “Outros”? *", key=f"{chave}_outros",
                                        value=(atual or {}).get("outros_desc") or "",
                                        placeholder="ex.: 1 L Original, garrafeira vazia...")
        st.caption(f"Total: **{_f(sum(qtds.values()))} palete(s)**")
    elif tipo == "Descartável":
        paletes = st.number_input("🥫 Quantidade de paletes *", min_value=0.0, step=1.0, format="%.0f",
                                  key=f"{chave}_pal", value=float((atual or {}).get("paletes") or 0))
    total_pal = sum(qtds.values()) if tipo == "Retornável" else paletes
    cap = svc.capacidade_paletes(operacao_id, placa)
    if cap and total_pal > cap:
        st.warning(f"⚠️ {_f(total_pal)} paletes passam da capacidade da {placa} ({cap} paletes).")
    obs = st.text_input("Observação", value=(atual or {}).get("observacao") or "", key=f"{chave}_obs",
                        placeholder="opcional")
    prio = st.checkbox("⭐ Prioridade para o armazém", value=svc.e_prioritario(atual or {}), key=f"{chave}_prio",
                       help="O pedido aparece no topo da Gestão de Pedidos e do Pátio/Descarga do armazém.")
    if st.button("💾 Salvar pedido" if not atual else "💾 Salvar alteração", type="primary", key=f"{chave}_ok"):
        try:
            svc.salvar_pedido(operacao_id, atual["id"] if atual else None, d, placa, numero, tipo, qtds, paletes, obs,
                              usuario.get("nome") or usuario.get("login") or "", fabrica_id=fabrica_id,
                              motorista_id=motorista_id, hora_agendamento=hora_ag, hora_agendamento_fim=hora_fim,
                              outros_desc=outros_desc, prioridade=prio)
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            st.session_state[f"pp_form_v_{operacao_id}"] = st.session_state.get(f"pp_form_v_{operacao_id}", 0) + 1
            ui.avisar(f"Pedido {numero} {'editado — a edição aparece sinalizada' if atual else 'salvo — já aparece'} "
                      "para o Ressuprimento e o Armazém.")
            st.rerun()


def _reprogramar(usuario: dict, operacao_id: int, atual: dict, chave: str) -> None:
    """Novo dia/slot (e, se quiser, outra placa/motorista) — o pedido atual vira 🔁 Reprogramado."""
    with st.popover("🔁 Reprogramar (substitui o agendamento)"):
        st.caption(f"Pedido **{atual['numero_pedido']}** · {atual['placa']} · hoje no slot "
                   f"{svc.janela_txt(atual)} de {dt.date.fromisoformat(str(atual['data'])[:10]):%d/%m}.")
        ds = svc.dias_pedido()
        nova = st.selectbox("Nova data *", ds, format_func=svc.rotulo_dia, key=f"{chave}_d")
        a, b = st.columns(2)
        ini = a.time_input("Slot início *", value=None, step=dt.timedelta(minutes=15), key=f"{chave}_i")
        fim = b.time_input("Slot fim", value=None, step=dt.timedelta(minutes=15), key=f"{chave}_f")
        placas = logistica_repo_placas(operacao_id)
        placa = st.selectbox("Placa", placas, index=placas.index(atual["placa"]) if atual["placa"] in placas else 0,
                             key=f"{chave}_p")
        motivo = st.text_input("Motivo *", key=f"{chave}_m", placeholder="ex.: fábrica remarcou o horário")
        if st.button("🔁 Confirmar reprogramação", type="primary", key=f"{chave}_ok"):
            ui.acao(svc.reprogramar, operacao_id, int(atual["id"]), nova, motivo, usuario.get("nome") or "",
                    hora_agendamento=ini, hora_agendamento_fim=fim, placa=placa,
                    sucesso="Pedido reprogramado — o agendamento antigo ficou como 🔁 Reprogramado.")


def logistica_repo_placas(operacao_id: int) -> list[str]:
    from repositories import logistica_repo

    c = logistica_repo.carretas_df(operacao_id)
    return c["placa"].tolist() if not c.empty else []


def _escolher_dia(chave: str) -> dt.date:
    ds = svc.dias_pedido()
    rot = {d.isoformat(): svc.rotulo_dia(d) for d in ds}
    esc = ui._escolha(chave, list(rot), ds[0].isoformat(), formatar=rot.get, pills=True)
    return dt.date.fromisoformat(esc)


# --- Puxada ---------------------------------------------------------------------------------
def render(usuario: dict, operacao_id: int) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        tela_ressuprimento(usuario, operacao_id)
        return
    d = _escolher_dia("pp_dia")
    df = repo.pedidos_df(operacao_id, d.isoformat(), d.isoformat())
    dia = _placas_do_dia(operacao_id, d)
    disponiveis = dia[dia["status"] == "Disponível"] if not dia.empty else dia
    com_pedido = set(df[~df["status"].isin(["Cancelado", "Reprogramado"])]["placa"].str.upper()) if not df.empty else set()
    livres = disponiveis[~disponiveis["placa"].str.upper().isin(com_pedido)] if not disponiveis.empty else disponiveis
    _kpis(df, f"kp_pp_{d}", [{"titulo": "Placas disponíveis sem pedido", "valor": len(livres), "icone": "🚛",
                              "status": "atencao" if len(livres) else "bom",
                              "dados": livres[["placa", "sugestao", "observacao"]] if not livres.empty else None,
                              "colunas": {"placa": "Placa", "sugestao": "Sugestão", "observacao": "Observação"}}])
    tema.secao(f"🚛 Placas em {d:%d/%m}", "Status e sugestão definidos em 🗓️ Disponibilidade de Placas.")
    _chips_placas(dia)

    v = st.session_state.get(f"pp_form_v_{operacao_id}", 0)
    with st.expander(f"➕ Novo pedido para {d:%d/%m}", expanded=df.empty):
        _form(usuario, operacao_id, d, None, f"pp_n_{d}_{v}")

    tema.secao(f"📋 Pedidos de {svc.rotulo_dia(d)}", "🟡 Aberto = aguardando o armazém · ✅ Finalizado pelo armazém.")
    if df.empty:
        st.info("Nenhum pedido lançado para este dia.")
        return
    _cards(df)
    abertos = df[~df["status"].isin(["Cancelado", "Reprogramado"])]
    if not abertos.empty:
        with st.container(key="cad_alt_pp"):
            st.markdown('<div class="eco-alt-titulo">✏️ Editar ou cancelar pedido</div>', unsafe_allow_html=True)
            st.caption("A edição fica sinalizada para o Armazém e o Ressuprimento (quem editou, quando e o que mudou). "
                       "Pedido já finalizado volta para Aberto para o armazém conferir de novo.")
            nomes = {int(r["id"]): f"{'✅ ' if r['status'] == 'Finalizado' else ''}{r['placa']} · pedido "
                                   f"{r['numero_pedido']} · {r['tipo']}"
                     + (f" · {r['fabrica']}" if isinstance(r.get("fabrica"), str) else "")
                     for r in abertos.to_dict("records")}
            pid = st.selectbox("Pedido", [None, *nomes], key=f"pp_alt_{d}",
                               format_func=lambda i: "Selecione..." if i is None else nomes[i])
            if pid:
                _form(usuario, operacao_id, d, repo.pedido(pid), f"pp_a_{pid}_{v}")
                if repo.pedido(pid)["status"] == "Aberto":
                    _reprogramar(usuario, operacao_id, repo.pedido(pid), f"pp_r_{pid}_{v}")
                    with st.popover("⛔ Cancelar este pedido"):
                        if st.button("Confirmar cancelamento", key=f"pp_cancel_{pid}", type="primary"):
                            ui.acao(svc.cancelar, pid, usuario.get("nome") or "", sucesso="Pedido cancelado.")
    ui.downloads(svc.tabela(df), f"pedidos_puxada_{d}", key=f"dl_pp_{d}")


# --- Armazém --------------------------------------------------------------------------------
def tela_armazem(usuario: dict, operacao_id: int) -> None:
    hoje = tempo.hoje()
    consolidada = operacoes_repo.e_consolidada(operacao_id)
    ds = svc.dias_pedido()
    df = repo.pedidos_df(operacao_id, ds[0].isoformat(), ds[-1].isoformat())
    atrasados = repo.pedidos_df(operacao_id, None, (hoje - dt.timedelta(days=1)).isoformat(), apenas_abertos=True)
    abertos = pd.concat([atrasados, df[df["status"] == "Aberto"] if not df.empty else df]).drop_duplicates("id") \
        if not (atrasados.empty and df.empty) else df
    prios = [svc.prioridade(r)[0] for r in abertos.to_dict("records")] if not abertos.empty else []
    urgentes = abertos[[p <= 2 for p in prios]] if prios else abertos
    estrelas = abertos[[svc.e_prioritario(r) for r in abertos.to_dict("records")]] if not abertos.empty else abertos
    _kpis(df, "kp_pp_arm", [
        {"titulo": "🚦 Saem em até 6h / atrasados", "valor": len(urgentes), "icone": "",
         "status": "critico" if any(p <= 1 for p in prios) else "atencao" if len(urgentes) else "bom",
         "dados": svc.tabela(urgentes, consolidada) if not urgentes.empty else None},
        {"titulo": "⭐ Prioridades da Puxada", "valor": len(estrelas), "icone": "",
         "status": "critico" if len(estrelas) else "bom",
         "dados": svc.tabela(estrelas, consolidada) if not estrelas.empty else None},
        {"titulo": "Abertos de dias anteriores", "valor": len(atrasados), "icone": "⏰",
         "status": "critico" if len(atrasados) else "bom", "dados": svc.tabela(atrasados, consolidada)}])
    opcoes = {"PRIO": f"🚦 Prioridades ({len(abertos)} aberto(s))",
              **{f"D{i}": svc.rotulo_dia(d) for i, d in enumerate(ds)}}
    if len(atrasados):
        opcoes["ATR"] = f"⏰ Pendentes anteriores ({len(atrasados)})"
    esc = ui._escolha("pp_arm_dia", list(opcoes), "PRIO", formatar=opcoes.get, pills=True)
    if esc == "PRIO":
        lista = abertos
        st.caption("Ordem: ⭐ prioridades marcadas pela Puxada primeiro; depois o prazo máximo para a carreta **sair da revenda** = agendamento na fábrica − "
                   "tempo de deslocamento até a fábrica.")
    elif esc == "ATR":
        lista = atrasados
    else:
        d = ds[int(esc[1:])]
        lista = df[df["data"] == d.isoformat()] if not df.empty else df
    st.caption("Confira a carga e clique em **✅ Finalizado** — o status muda na Puxada e no Ressuprimento na hora.")
    if lista.empty:
        st.info("Nenhum pedido para este dia.")
        return
    regs = sorted(lista.to_dict("records"), key=lambda r: (*svc.ordem_armazem(r), str(r["placa"])))
    for ini in range(0, len(regs), 3):
        for col, r in zip(st.columns(3), regs[ini:ini + 3]):
            with col:
                st.markdown(_CSS + _card(r, consolidada), unsafe_allow_html=True)
                if r["status"] == "Aberto":
                    if st.button("✅ Finalizado", key=f"pp_fin_{r['id']}", type="primary", **ui.LARGURA):
                        ui.acao(svc.finalizar, int(r["id"]), usuario.get("nome") or "",
                                sucesso=f"Pedido {r['numero_pedido']} finalizado.")
                elif r["status"] == "Finalizado":
                    if st.button("↩️ Reabrir", key=f"pp_reab_{r['id']}", **ui.LARGURA):
                        ui.acao(svc.reabrir, int(r["id"]), sucesso="Pedido reaberto.")
    ui.downloads(svc.tabela(lista, consolidada), "gestao_pedidos_armazem", key="dl_pp_arm")


# --- Ressuprimento ------------------------------------------------------------------------
def tela_ressuprimento(usuario: dict, operacao_id: int) -> None:
    d = _escolher_dia("pp_res_dia")
    filiais = operacoes_repo.ids_efetivos(operacao_id)
    consolidada = len(filiais) > 1
    df = repo.pedidos_df(operacao_id, d.isoformat(), d.isoformat())
    placas = pd.concat([_placas_do_dia(f, d).assign(filial=operacoes_repo.buscar(f)["nome"]) for f in filiais]) \
        if filiais else pd.DataFrame()
    disp_ = placas[placas["status"] == "Disponível"] if not placas.empty else placas
    ret = int((disp_["sugestao"] == "Retornável").sum()) if not disp_.empty else 0
    desc = int((disp_["sugestao"] == "Descartável").sum()) if not disp_.empty else 0
    _kpis(df, f"kp_pp_res_{d}", [{"titulo": "Placas disponíveis", "valor": len(disp_), "icone": "🚛", "status": "info",
                                  "detalhe": f"sugestão: ♻️ {ret} retornável · 🥫 {desc} descartável",
                                  "dados": disp_[["filial", "placa", "sugestao", "observacao"]] if not disp_.empty else None,
                                  "colunas": {"filial": "Filial", "placa": "Placa", "sugestao": "Sugestão",
                                              "observacao": "Observação"}}])
    tema.secao(f"🚛 Placas em {d:%d/%m}", "Definidas pela Puxada. A sugestão orienta o pedido de cada placa.")
    for f in filiais:
        sub = placas[placas["filial"] == operacoes_repo.buscar(f)["nome"]] if not placas.empty else placas
        if consolidada:
            st.markdown(f"**🏢 {operacoes_repo.buscar(f)['nome']}**")
        if sub.empty:
            st.caption("Sem placas cadastradas.")
        _chips_placas(sub)
    tema.secao(f"📋 Pedidos de {svc.rotulo_dia(d)}", "Lançados pela Puxada · ✅ = finalizado pelo armazém.")
    if df.empty:
        st.info("A Puxada ainda não lançou pedidos para este dia.")
        return
    _cards(df, consolidada)
    ui.downloads(svc.tabela(df, consolidada), f"pedidos_puxada_{d}", key=f"dl_pp_res_{d}")
