"""Pátio de descarga — agenda por janela (slots), próximos dias e cadastro das janelas da revenda.

Usada em 🚛 Puxada › Descarga (Pátio) e em 🏬 Armazém › Pátio (é a mesma tela).
As carretas do App Carreteiro entram sozinhas: "Agendado" quando o motorista agenda (dia, janela e
produto), "A caminho" na saída da cervejaria, "Chegou" na chegada à revenda e "Descarregado" no fim.
"""
import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import tema, tempo, ui
from modules.componentes.autosave import editor_autosave
from modules.componentes.cadastro import Campo, tela
from repositories import logistica_repo
from services import janelas_service as jsvc
from services import patio_service
from services.erros import RegraNegocioError

STATUS = ["Agendado", "A caminho", "Chegou", "Descarregando", "Descarregado", "Cancelado", "No-show"]
ICONE_STATUS = {"Agendado": "🗓️", "A caminho": "🛣️", "Chegou": "🅿️", "Descarregando": "⏳",
                "Descarregado": "✅", "Cancelado": "⛔", "No-show": "⚠️"}
TIPOS = ["Descartável", "Retornável", "Misto"]
HORAS = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
ORIGEM_APP = "App Carreteiro"

_CSS = """
<style>
.pt-quadro { display:grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap:.8rem; margin:.4rem 0 1rem; }
.pt-jan { background:#fff; border:1px solid #dfe5ee; border-radius:14px; padding:.7rem .75rem .6rem;
    box-shadow:0 1px 2px rgba(11,31,58,.05); }
.pt-jan .hd { display:flex; justify-content:space-between; align-items:baseline; gap:.4rem; }
.pt-jan .hd b { font-size:1.05rem; color:#0B1F3A; }
.pt-jan .hd span { font-size:.8rem; font-weight:700; padding:.1rem .5rem; border-radius:999px; }
.pt-jan .hd span.ok { background:#e8f6ee; color:#146c43; } .pt-jan .hd span.cheia { background:#fdecec; color:#a32025; }
.pt-jan .hd span.livre { background:#eef3fa; color:#2a5ca8; }
.pt-jan .sub { color:#77766f; font-size:.75rem; margin:.1rem 0 .35rem; }
.pt-bar { height:6px; background:#eef0f3; border-radius:99px; overflow:hidden; margin-bottom:.5rem; }
.pt-bar i { display:block; height:100%; background:#2a78d6; border-radius:99px; }
.pt-bar i.cheia { background:#e5484d; }
.pt-card { border:1px solid #e6e8ec; border-left:4px solid var(--c); border-radius:10px; padding:.45rem .6rem;
    margin:.35rem 0; background:#fbfcfd; }
.pt-card .l1 { display:flex; justify-content:space-between; gap:.4rem; align-items:center; }
.pt-card .l1 b { font-size:.98rem; letter-spacing:.02em; }
.pt-card .st { font-size:.72rem; font-weight:800; padding:.08rem .45rem; border-radius:999px; background:var(--f);
    color:var(--c); white-space:nowrap; }
.pt-card .l2 { font-size:.82rem; color:#3d3c39; margin-top:.15rem; }
.pt-card .l3 { font-size:.75rem; color:#77766f; margin-top:.1rem; }
.pt-card .nx { font-size:.78rem; margin-top:.3rem; padding:.3rem .45rem; border-radius:8px; background:#eef6ff;
    color:#173a6b; border:1px solid #cfe0f6; }
.pt-card .mn { font-size:.78rem; margin-top:.3rem; padding:.3rem .45rem; border-radius:8px; background:#fff1e6;
    color:#7a3a07; border:1px solid #f3cfae; }
.pt-card .cg { font-size:.78rem; margin-top:.3rem; padding:.3rem .45rem; border-radius:8px; background:#f1ebfb;
    color:#4a2a8a; border:1px solid #dccbf5; }
.pt-card.prio { box-shadow:0 0 0 2px #f0c75e; }
.pt-star { font-size:.66rem; font-weight:800; padding:.05rem .4rem; border-radius:999px; background:#fff4d6;
    color:#8a5a00; border:1px solid #f0c75e; margin-left:.3rem; }
.pt-vazio { color:#9a9993; font-size:.8rem; font-style:italic; padding:.3rem 0; }
.pt-livres { font-size:.76rem; color:#3d3c39; margin-top:.45rem; line-height:1.9; }
.pt-hl { display:inline-block; background:#e8f6ee; color:#146c43; border-radius:6px; padding:0 .35rem; font-weight:700;
    margin-right:.15rem; }
.pt-slot { border:1.5px dashed #cfd8e6; border-radius:10px; padding:.35rem .6rem; margin:.35rem 0; color:#8a96a8;
    font-size:.78rem; }
.pt-dias { overflow:auto; border:1px solid #dfe5ee; border-radius:12px; background:#fff; margin:.3rem 0 .8rem; }
.pt-dias table { width:100%; border-collapse:collapse; font-size:.88rem; }
.pt-dias th { background:#eef3fa; color:#0B1F3A; font-weight:800; text-align:center; padding:.5rem .6rem;
    border-bottom:2px solid #c9d6ea; white-space:nowrap; }
.pt-dias th:first-child, .pt-dias td:first-child { text-align:left; }
.pt-dias td { padding:.45rem .6rem; border-bottom:1px solid #eceae4; text-align:center; white-space:nowrap; }
.pt-dias td.ok { color:#146c43; font-weight:700; } .pt-dias td.cheia { background:#fdecec; color:#a32025; font-weight:800; }
.pt-dias td.na { color:#c3c2bc; }
</style>
"""
_CORES = {"Agendado": ("#2a5ca8", "#eaf1fb"), "A caminho": ("#7a4fc9", "#f1ebfb"), "Chegou": ("#b7791f", "#fdf3e1"),
          "Descarregando": ("#b7791f", "#fdf3e1"), "Descarregado": ("#146c43", "#e8f6ee"),
          "Cancelado": ("#77766f", "#f0efec"), "No-show": ("#a32025", "#fdecec")}


def _e(v) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))


def _txt(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) or str(v) in ("None", "nan", "NaT") else str(v)


# --- Regras do agendamento manual ---------------------------------------------------
def agendar(operacao_id: int, data: dt.date, hora: str | None, placa: str, slot: str, tipo: str, obs: str,
            usuario: str, janela_id: int | None = None):
    placa, slot = (placa or "").strip().upper(), (slot or "").strip()
    if not placa:
        raise RegraNegocioError("Informe a placa.")
    if jsvc.tem_janelas(operacao_id):
        x = jsvc.validar_reserva(operacao_id, data, hora, tipo)
        hora, janela_id = x["hora"], x["periodo"]["id"]
    elif not hora:
        raise RegraNegocioError("Informe a hora.")
    if slot and logistica_repo.slot_ocupado(operacao_id, data.isoformat(), hora, slot):
        raise RegraNegocioError(f"A {slot} já está reservada em {data:%d/%m} às {hora}. Escolha outra doca.")
    aid = logistica_repo.inserir_agendamento(operacao_id, data.isoformat(), hora, placa, slot or "A definir", tipo,
                                             (obs or "").strip(), usuario)
    if janela_id:
        logistica_repo.atualizar_agendamento(aid, janela_id=janela_id)


# --- Visual ----------------------------------------------------------------------------
def _andamento(r: dict) -> str:
    """Da observação do app fica só o que interessa ao pátio (NFs, saída, chegada)."""
    obs = _txt(r.get("observacao"))
    if r.get("criado_por") != ORIGEM_APP:
        return obs
    partes = [p for p in obs.split(" · ") if p and not p.startswith("📱 Pedido") and p != _txt(r.get("motorista"))]
    return " · ".join(partes)


def _janela_txt(js_todas: list[dict], r: dict) -> str:
    return jsvc.janela_de_agendamento(js_todas, r.get("data"), r.get("hora"), r.get("janela_id"),
                                      _txt(r.get("tipo_carga")) or None) or "Fora dos períodos"


def tabela_legivel(df: pd.DataFrame, js_todas: list[dict], com_data: bool = False) -> pd.DataFrame:
    """Agendamentos no formato de leitura (para os detalhes e downloads)."""
    if df is None or df.empty:
        return pd.DataFrame()
    linhas = []
    for r in df.to_dict("records"):
        d = {}
        if com_data:
            d["Dia"] = pd.to_datetime(r["data"]).strftime("%d/%m/%Y") if _txt(r.get("data")) else ""
        d.update({
            "Ocupa a doca": _janela_txt(js_todas, r) if js_todas else "",
            "Hora": _txt(r.get("hora")) or "—",
            "Placa": _txt(r.get("placa")),
            "Status": f"{ICONE_STATUS.get(r.get('status'), '')} {_txt(r.get('status'))}".strip(),
            "Motorista": _txt(r.get("motorista")) or "—",
            "Pedido": _txt(r.get("pedido_app")) or "—",
            "Produto": _txt(r.get("tipo_carga")) or "—",
            "Doca": _txt(r.get("slot")) or "A definir",
            "Origem": "📱 App" if r.get("criado_por") == ORIGEM_APP else f"✍️ {_txt(r.get('criado_por'))}",
            "Andamento / obs.": _andamento(r) or "—",
        })
        if not js_todas:
            d.pop("Ocupa a doca")
        linhas.append(d)
    return pd.DataFrame(linhas)


def _card(r: dict) -> str:
    cor, fundo = _CORES.get(r.get("status"), ("#52514e", "#f0efec"))
    app = "📱 " if r.get("criado_por") == ORIGEM_APP else ""
    ped, hora, doca = _txt(r.get("pedido_app")), _txt(r.get("hora")), _txt(r.get("slot"))
    l2 = " · ".join(x for x in [_txt(r.get("motorista")), f"Ped. {ped}" if ped else "", _txt(r.get("tipo_carga"))] if x)
    faixa = _txt(r.get("_faixa"))
    l3 = " · ".join(x for x in [f"⏰ {faixa or hora}" if (faixa or hora) else "", f"Doca: {doca}" if doca and doca != "A definir" else "",
                                _andamento(r)] if x)
    inativo = r.get("status") in ("Cancelado", "No-show")
    apagado = ";opacity:.55" if inativo else ""
    extra = ""
    if not inativo and r.get("status") != "Descarregado" and patio_service.carga_txt(r.get("_itens")):
        extra += f'<div class="cg">📦 <b>Carga:</b> {_e(patio_service.carga_txt(r.get("_itens")))}</div>'
    if not inativo:
        if r.get("_depois"):
            extra += f'<div class="nx">📦 <b>Depois carrega:</b> {_e(patio_service.depois_txt(r["_depois"]))}</div>'
        if r.get("_manut"):
            extra += f'<div class="mn">🔧 <b>Depois vai para MANUTENÇÃO:</b> {_e(patio_service.manut_txt(r["_manut"]))}</div>'
    prio = bool(r.get("_prio")) and not inativo
    estrela = '<span class="pt-star">⭐ PRIORIDADE</span>' if prio else ""
    return (f'<div class="pt-card{" prio" if prio else ""}" style="--c:{cor};--f:{fundo}{apagado}"><div class="l1">'
            f'<b>{app}{_e(r.get("placa"))}{estrela}</b>'
            f'<span class="st">{ICONE_STATUS.get(r.get("status"), "")} {_e(r.get("status"))}</span></div>'
            f'{f"<div class=l2>{_e(l2)}</div>" if l2 else ""}{f"<div class=l3>{_e(l3)}</div>" if l3 else ""}{extra}</div>')


def _chips_livres(hs: list[dict]) -> str:
    livres = [h for h in hs if h["livre"] and not h["passou"]]
    if not livres:
        return '<span class="pt-vazio">nenhum horário livre</span>'
    return " ".join(f'<span class="pt-hl">{h["hora"]}</span>' for h in livres)


def _depois_descarga(regs: list[dict]) -> None:
    """Resumo no topo: carretas com ⭐ prioridade, próximo carregamento ou manutenção depois da descarga."""
    ativos = [r for r in regs if r.get("status") not in ("Cancelado", "No-show")
              and (r.get("_depois") or r.get("_manut"))]
    if not ativos:
        return
    ativos.sort(key=lambda r: (not r.get("_prio"), r.get("status") == "Descarregado", _txt(r.get("hora"))))
    n_p = sum(1 for r in ativos if r.get("_prio"))
    n_m = sum(1 for r in ativos if r.get("_manut"))
    tema.secao(f"🧭 Depois da descarga · {len(ativos)} carreta(s)",
               f"{'⭐ ' + str(n_p) + ' prioridade(s) · ' if n_p else ''}"
               f"{'🔧 ' + str(n_m) + ' vão para manutenção · ' if n_m else ''}"
               "o que cada carreta faz quando terminar de descarregar (pedido já lançado pela Puxada).")
    st.markdown(_CSS + '<div class="pt-quadro">' + "".join(_card(r) for r in ativos) + "</div>",
                unsafe_allow_html=True)
    with st.expander("📋 Ver em tabela / baixar"):
        ui.tabela(patio_service.tabela_depois(ativos), baixar="depois_da_descarga")


def _itens_cargas(regs: list[dict]) -> None:
    """O que cada carreta do dia traz: itens da Puxada Marcada do pedido que o motorista ligou à viagem."""
    ativos = [r for r in regs if r.get("status") not in ("Cancelado", "No-show")]
    tab = patio_service.tabela_itens(ativos)
    sem = [r for r in ativos if _txt(r.get("pedido_app")) and (r.get("_itens") is None or len(r["_itens"]) == 0)]
    if tab.empty and not sem:
        return
    with st.expander(f"📦 O que cada carreta traz · {tab['Placa'].nunique() if not tab.empty else 0} carga(s) · "
                     f"{ui.numero(tab['Paletes'].sum()) if not tab.empty else 0} paletes"):
        st.caption("Itens da Puxada Marcada (coluna Q = pedido, R = código, S = produto, T = paletes). "
                   "Caixas = paletes × caixas por palete da 01.11.")
        if not tab.empty:
            ui.tabela(tab, column_config={
                "Código": st.column_config.NumberColumn("Código", format="%d"),
                "Paletes": st.column_config.NumberColumn("Paletes", format="%.1f"),
                "Caixas (unid. venda)": st.column_config.NumberColumn("Caixas (unid. venda)", format="%.0f")},
                baixar="itens_das_cargas")
        if sem:
            st.caption("⚠️ Pedido sem itens na Puxada Marcada: "
                       + ", ".join(f"{_txt(r.get('placa'))} (ped. {_txt(r.get('pedido_app'))})" for r in sem)
                       + " — atualize o relatório da Puxada Marcada.")


def _manutencoes(operacao_id: int, dia: dt.date) -> None:
    from repositories import manutencao_repo

    if ui.somente_leitura(operacao_id):
        return
    m = manutencao_repo.lista_df(operacao_id, dia.isoformat(), (dia + dt.timedelta(days=3)).isoformat(),
                                 ["Programada", "Em andamento"])
    with st.expander(f"🔧 Manutenções programadas pela Puxada (até {dia + dt.timedelta(days=3):%d/%m}) · {len(m)}"):
        if m.empty:
            st.caption("Nenhuma manutenção programada.")
            return
        m = m.sort_values(["prioridade", "data", "hora"], ascending=[False, True, True], na_position="last")
        ui.tabela(pd.DataFrame({
            "Prioridade": ["⭐" if patio_service.ped_svc._v(x) else "" for x in m["prioridade"]],
            "Dia": [pd.to_datetime(x).strftime("%d/%m") for x in m["data"]],
            "Hora": [_txt(x) or "—" for x in m["hora"]], "Placa": m["placa"], "Tipo": m["tipo"],
            "Descrição": [_txt(x) for x in m["descricao"]], "Oficina": [_txt(x) for x in m["oficina"]],
            "Status": m["status"]}), baixar="manutencoes_programadas")


def quadro_dia(operacao_id: int, dia: dt.date, df: pd.DataFrame) -> None:
    """Agenda do dia por período (linha do tempo da doca) + horários ainda livres de cada produto."""
    ps = jsvc.periodos(operacao_id)
    js_todas = logistica_repo.janelas(operacao_id, apenas_ativas=False)
    regs = patio_service.enriquecer(operacao_id, df.to_dict("records") if not df.empty else [])
    for r in regs:
        r["_faixa"] = jsvc.janela_de_agendamento(js_todas, r.get("data"), r.get("hora"), r.get("janela_id"),
                                                 _txt(r.get("tipo_carga")) or None)
    _depois_descarga(regs)
    _itens_cargas(regs)
    tema.secao(f"🗓️ Agenda de {dia:%d/%m/%Y} ({jsvc.DIAS[dia.weekday()]})",
               "Cada coluna é um período da doca. 📱 = agendado pelo motorista no App Carreteiro.")
    if not ps:
        if not regs:
            st.info(f"Nenhuma descarga em {dia:%d/%m}. Cadastre os períodos em 🕒 Slots de descarga.")
            return
        st.markdown(_CSS + '<div class="pt-quadro"><div class="pt-jan"><div class="hd"><b>📋 Descargas do dia</b>'
                    '</div>' + "".join(_card(r) for r in sorted(regs, key=lambda x: _txt(x.get("hora")))) +
                    "</div></div>", unsafe_allow_html=True)
        return
    grupos: dict = {p["id"]: [] for p in ps}
    fora = []
    for r in regs:
        try:
            ini = dt.datetime.combine(dia, dt.datetime.strptime(_txt(r.get("hora"))[:5], "%H:%M").time())
            p = jsvc.periodo_em(ps, ini)
        except ValueError:
            p = None
        (grupos[p["id"]] if p else fora).append(r)
    hs_desc = jsvc.horarios(operacao_id, dia, "Descartável")
    hs_ret = jsvc.horarios(operacao_id, dia, "Retornável")
    blocos = []
    for p in sorted(ps, key=lambda x: (x["hora_inicio"] < "12:00", x["hora_inicio"])):
        lista = sorted(grupos[p["id"]], key=lambda x: (x.get("status") in ("Cancelado", "No-show"),
                                                       (_txt(x.get("hora")) < "12:00") != (p["hora_inicio"] >= p["hora_fim"]),
                                                       _txt(x.get("hora"))))
        noite = p["hora_inicio"] > p["hora_fim"]
        dd = [h for h in hs_desc if h["periodo"]["id"] == p["id"]]
        rr = [h for h in hs_ret if h["periodo"]["id"] == p["id"]]
        ativos = [r for r in lista if r.get("status") not in ("Cancelado", "No-show")]
        blocos.append(
            f'<div class="pt-jan"><div class="hd"><b>{"🌙" if noite else "☀️"} {_e(jsvc.rotulo(p))}</b>'
            f'<span class="{"ok" if ativos else "livre"}">{len(ativos)} descarga(s)</span></div>'
            f'<div class="sub">🥫 descartável {jsvc.dur_txt(p.get("dur_desc_min"))} · ♻️ retornável '
            f'{jsvc.dur_txt(p.get("dur_ret_min"))} · {int(p.get("slots") or 1)} doca(s)</div>'
            + ("".join(_card(r) for r in lista) or '<div class="pt-vazio">nenhuma descarga agendada</div>')
            + f'<div class="pt-livres"><b>🥫 livres:</b> {_chips_livres(dd)}</div>'
            f'<div class="pt-livres"><b>♻️ livres:</b> {_chips_livres(rr)}</div></div>')
    if fora:
        blocos.append('<div class="pt-jan"><div class="hd"><b>📋 Fora dos períodos</b></div>'
                      + "".join(_card(r) for r in fora) + "</div>")
    st.markdown(_CSS + f'<div class="pt-quadro">{"".join(blocos)}</div>', unsafe_allow_html=True)
    st.caption("Horários livres = início possível da descarga sem encostar em outra. Retornável ocupa a doca por "
               "mais tempo e bloqueia o descartável no mesmo horário.")


def proximos_dias(operacao_id: int, dias: int = 7) -> None:
    """Ocupação da doca nos próximos dias (o que os motoristas já agendaram) e horários livres."""
    hoje = tempo.hoje()
    prox = logistica_repo.agendamentos_df(operacao_id, hoje.isoformat(), (hoje + dt.timedelta(days=dias)).isoformat())
    if jsvc.tem_janelas(operacao_id):
        linhas = []
        for i in range(dias + 1):
            d = hoje + dt.timedelta(days=i)
            r = jsvc.resumo_dia(operacao_id, d)
            nome = "Hoje" if i == 0 else "Amanhã" if i == 1 else jsvc.DIAS[d.weekday()]
            cls_d = "cheia" if not r["livres_desc"] else "ok"
            cls_r = "cheia" if not r["livres_ret"] else "ok"
            linhas.append(f"<tr><td><b>{nome}</b> {d:%d/%m}</td><td>{r['ocupados']}</td>"
                          f"<td class='{cls_d}'>{r['livres_desc']} · próx. {r['prox_desc'] or '—'}</td>"
                          f"<td class='{cls_r}'>{r['livres_ret']} · próx. {r['prox_ret'] or '—'}</td></tr>")
        st.markdown(_CSS + '<div class="pt-dias"><table><thead><tr><th>Dia</th><th>Descargas</th>'
                    '<th>🥫 Horários livres descartável</th><th>♻️ Horários livres retornável</th></tr></thead>'
                    f'<tbody>{"".join(linhas)}</tbody></table></div>', unsafe_allow_html=True)
        st.caption("Vermelho = sem horário livre (o produto some do app do motorista naquele dia).")
    vis = tabela_legivel(prox, logistica_repo.janelas(operacao_id, False), com_data=True)
    if not vis.empty:
        ui.tabela(vis, baixar="agendamentos_descarga")
    else:
        st.info("Nenhuma descarga agendada nos próximos dias.")


def painel_dia(operacao_id: int, dia: dt.date, editar: bool, key: str) -> pd.DataFrame:
    df = logistica_repo.agendamentos_df(operacao_id, dia.isoformat(), dia.isoformat())
    js_todas = logistica_repo.janelas(operacao_id, apenas_ativas=False)
    vis = tabela_legivel(df, js_todas)

    def filtro(*status):
        return vis[vis["Status"].str.contains("|".join(status), regex=True)] if not vis.empty else vis

    no_patio, a_caminho = filtro("Chegou", "Descarregando"), filtro("A caminho")
    perdidos = filtro("No-show", "Cancelado")
    tem = jsvc.tem_janelas(operacao_id)
    res = jsvc.resumo_dia(operacao_id, dia) if tem else {}
    tema.kpis([
        {"titulo": f"Agendados em {dia:%d/%m}", "valor": len(df), "icone": "🗓️", "status": "info", "dados": vis},
        {"titulo": "A caminho (App)", "valor": len(a_caminho), "icone": "🛣️", "status": "info", "dados": a_caminho,
         "detalhe": "saíram da cervejaria"},
        {"titulo": "No pátio agora", "valor": len(no_patio), "icone": "🅿️",
         "status": "atencao" if len(no_patio) else "info", "dados": no_patio},
        {"titulo": "Descarregados", "valor": len(filtro("Descarregado")), "icone": "✅", "status": "bom",
         "dados": filtro("Descarregado")},
        {"titulo": "Horários livres", "valor": f"🥫 {res['livres_desc']} · ♻️ {res['livres_ret']}" if tem else "—",
         "icone": "🕒", "status": "info",
         "detalhe": (f"próximo: desc. {res['prox_desc'] or '—'} · ret. {res['prox_ret'] or '—'}" if tem
                     else "sem períodos cadastrados")},
        {"titulo": "No-show / cancelados", "valor": len(perdidos), "icone": "⚠️",
         "status": "serio" if len(filtro("No-show")) else "info", "dados": perdidos},
    ], key=f"kp_desc_{key}")

    quadro_dia(operacao_id, dia, df)
    _manutencoes(operacao_id, dia)
    if df.empty:
        return df
    if editar:
        with st.expander("✏️ Atualizar status, doca e observação", expanded=False):
            ed = df[["id", "hora", "placa", "motorista", "pedido_app", "tipo_carga", "status", "slot", "observacao"]]
            editor_autosave(ed, f"ed_desc_{key}_{dia}", ["status", "slot", "hora", "observacao"],
                            lambda l, alt: logistica_repo.atualizar_agendamento(int(l["id"]), **alt), column_config={
                                "id": None, "placa": "Placa", "motorista": "Motorista", "pedido_app": "Pedido",
                                "tipo_carga": "Produto",
                                "status": st.column_config.SelectboxColumn("Status ✏️", options=STATUS),
                                "hora": st.column_config.SelectboxColumn("Hora ✏️", options=HORAS),
                                "slot": "Doca ✏️", "observacao": st.column_config.TextColumn("Observação ✏️",
                                                                                            width="large")})
            st.caption("Salva sozinho. As linhas 📱 do App acompanham a viagem (A caminho → Chegou → Descarregado).")
    return df


# --- Cadastro das janelas ------------------------------------------------------------
def janelas_cadastro(operacao_id: int) -> None:
    df = logistica_repo.janelas_df(operacao_id)
    if not df.empty:
        df["dias_txt"] = df["dias"].map(jsvc.dias_texto)
        df["dias"] = df["dias"].map(jsvc.dias_lista)
        df["desc_txt"] = df["dur_desc_min"].map(lambda m: jsvc.dur_txt(m) if m == m and m else "—")
        df["ret_txt"] = df["dur_ret_min"].map(lambda m: jsvc.dur_txt(m) if m == m and m else "—")
    tela(chave=f"jan_{operacao_id}", titulo="Slots de descarga (tempo de doca)", icone="🕒", df=df, por_linha=4,
         descricao="Em cada período, quanto tempo uma descarga ocupa a doca. O retornável ocupa mais tempo e "
                   "bloqueia o descartável no mesmo horário (a doca não faz os dois ao mesmo tempo). "
                   "Período que vira a meia-noite: fim menor que o início (ex.: 20:00 → 02:00).",
         campos=[Campo("hora_inicio", "Início do período", "opcoes", True, HORAS, padrao="02:00"),
                 Campo("hora_fim", "Fim do período", "opcoes", True, HORAS, padrao="20:00"),
                 Campo("dur_desc_min", "🥫 Descartável (minutos)", "inteiro", True, padrao=60, passo=15,
                       na_tabela=False),
                 Campo("dur_ret_min", "♻️ Retornável (minutos)", "inteiro", True, padrao=120, passo=15,
                       na_tabela=False),
                 Campo("slots", "Docas (descargas ao mesmo tempo)", "inteiro", True, padrao=1),
                 Campo("dias", "Dias da semana", "multi", True, {i: d for i, d in enumerate(jsvc.DIAS)},
                       padrao=jsvc.DIAS_PADRAO, na_tabela=False),
                 Campo("ativo", "Situação", "opcoes", True, {1: "✅ Ativo", 0: "⏸️ Pausado"}, padrao=1)],
         colunas_extras=[("desc_txt", "🥫 Descartável"), ("ret_txt", "♻️ Retornável"), ("dias_txt", "Dias")],
         rotulo_registro=lambda r: f"{r['hora_inicio']}–{r['hora_fim']} · "
                                   f"{jsvc.dias_texto(','.join(map(str, r['dias']))) if isinstance(r.get('dias'), list) else ''}",
         salvar=lambda jid, d: jsvc.salvar_janela(operacao_id, jid, d["hora_inicio"], d["hora_fim"], d["slots"],
                                                  d.get("dias") or [], d.get("dur_desc_min"), d.get("dur_ret_min"),
                                                  bool(d.get("ativo", 1))),
         excluir=lambda jid: logistica_repo.excluir("janelas_descarga", jid),
         aviso_vazio="Nenhum período cadastrado — o motorista informa a hora livremente.")
    if st.button("↺ Voltar ao padrão (20h–02h: 1h30/2h30 · 02h–20h: 1h/2h)", key=f"jan_padrao_{operacao_id}"):
        ui.acao(jsvc.criar_padrao, operacao_id, sucesso="Períodos padrão criados (os anteriores foram pausados).")


# --- Tela -----------------------------------------------------------------------------
def tela_patio(usuario: dict, operacao_id: int, key: str) -> None:
    consolidada = ui.somente_leitura(operacao_id)
    partes = {"dia": "🗓️ Agenda do dia", "prox": "📅 Próximos dias", "janelas": "🕒 Slots de descarga"}
    if consolidada:
        partes.pop("janelas")
    parte = ui._escolha(f"pt_parte_{key}", list(partes), "dia", formatar=partes.get, pills=True)
    if parte == "prox":
        tema.secao("📅 Próximos 7 dias", "O que já foi agendado (inclusive pelos motoristas no app) e os horários "
                   "livres da doca para cada produto.")
        proximos_dias(operacao_id)
        return
    if parte == "janelas":
        janelas_cadastro(operacao_id)
        return
    c1, c2 = st.columns([1, 3])
    dia = c1.date_input("Dia", value=tempo.hoje(), format="DD/MM/YYYY", key=f"desc_dia_{key}")
    if not consolidada:
        with c2.expander("➕ Lançar descarga manual (sem App)", expanded=False):
            _form_manual(usuario, operacao_id, dia, key)
    painel_dia(operacao_id, dia, editar=not consolidada, key=key)


def _form_manual(usuario: dict, operacao_id: int, dia: dt.date, key: str) -> None:
    carretas = logistica_repo.carretas_df(operacao_id)["placa"].tolist()
    a, b, c = st.columns(3)
    data = a.date_input("Data", value=dia, format="DD/MM/YYYY", key=f"fm_d_{key}")
    tipo = c.selectbox("Produto", ["Descartável", "Retornável", "Misto"], key=f"fm_t_{key}")
    if jsvc.tem_janelas(operacao_id):
        livres = jsvc.horarios_livres(operacao_id, data, tipo)
        nomes = {h["hora"]: h["rotulo"] for h in livres}
        hora = b.selectbox("Horário livre", list(nomes), format_func=nomes.get, key=f"fm_h_{key}_{data}_{tipo}",
                           placeholder="sem horário livre" if not nomes else "Selecione...", index=0 if nomes else None)
    else:
        hora = b.selectbox("Hora", HORAS, index=HORAS.index("08:00"), key=f"fm_h_{key}")
    e, f, g = st.columns(3)
    placa_sel = e.selectbox("Carreta cadastrada", ["— digitar placa —"] + carretas, key=f"fm_p_{key}")
    placa_txt = f.text_input("Placa (se não estiver cadastrada)", key=f"fm_pt_{key}")
    slot = g.text_input("Doca (opcional)", key=f"fm_s_{key}")
    obs = st.text_input("Observação", key=f"fm_o_{key}")
    if st.button("🚚 Agendar descarga", type="primary", key=f"fm_ok_{key}"):
        placa = placa_txt if placa_sel.startswith("—") else placa_sel
        ui.acao(agendar, operacao_id, data, hora, placa, slot, tipo, obs, usuario["login"],
                sucesso="Descarga agendada!")


def render(usuario: dict, operacao_id: int) -> None:
    tela_patio(usuario, operacao_id, "pux")
