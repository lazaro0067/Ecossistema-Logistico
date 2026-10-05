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
.pt-vazio { color:#9a9993; font-size:.8rem; font-style:italic; padding:.3rem 0; }
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
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


# --- Regras do agendamento manual ---------------------------------------------------
def agendar(operacao_id: int, data: dt.date, hora: str | None, placa: str, slot: str, tipo: str, obs: str,
            usuario: str, janela_id: int | None = None):
    placa, slot = (placa or "").strip().upper(), (slot or "").strip()
    if not placa:
        raise RegraNegocioError("Informe a placa.")
    if jsvc.tem_janelas(operacao_id):
        j = jsvc.validar_reserva(operacao_id, data, janela_id, tipo if tipo in ("Retornável", "Descartável") else None)
        hora, janela_id = j["hora_inicio"], j["id"]
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
    return jsvc.janela_de_agendamento(js_todas, r.get("data"), r.get("hora"), r.get("janela_id")) or "Fora de janela"


def tabela_legivel(df: pd.DataFrame, js_todas: list[dict], com_data: bool = False) -> pd.DataFrame:
    """Agendamentos no formato de leitura (para os detalhes e downloads)."""
    if df is None or df.empty:
        return pd.DataFrame()
    linhas = []
    for r in df.to_dict("records"):
        d = {}
        if com_data:
            d["Dia"] = pd.to_datetime(r["data"]).strftime("%d/%m/%Y") if r.get("data") else ""
        d.update({
            "Janela": _janela_txt(js_todas, r) if js_todas else "",
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
            d.pop("Janela")
        linhas.append(d)
    return pd.DataFrame(linhas)


def _card(r: dict) -> str:
    cor, fundo = _CORES.get(r.get("status"), ("#52514e", "#f0efec"))
    app = "📱 " if r.get("criado_por") == ORIGEM_APP else ""
    l2 = " · ".join(x for x in [_txt(r.get("motorista")), f"Ped. {_txt(r.get('pedido_app'))}" if r.get("pedido_app")
                                else "", _txt(r.get("tipo_carga"))] if x)
    l3 = " · ".join(x for x in [f"⏰ {_txt(r.get('hora'))}" if r.get("hora") else "",
                                f"Doca: {_txt(r.get('slot'))}" if r.get("slot") and r.get("slot") != "A definir" else "",
                                _andamento(r)] if x)
    apagado = ";opacity:.55" if r.get("status") in ("Cancelado", "No-show") else ""
    return (f'<div class="pt-card" style="--c:{cor};--f:{fundo}{apagado}"><div class="l1"><b>{app}{_e(r.get("placa"))}</b>'
            f'<span class="st">{ICONE_STATUS.get(r.get("status"), "")} {_e(r.get("status"))}</span></div>'
            f'{f"<div class=l2>{_e(l2)}</div>" if l2 else ""}{f"<div class=l3>{_e(l3)}</div>" if l3 else ""}</div>')


def quadro_dia(operacao_id: int, dia: dt.date, df: pd.DataFrame) -> None:
    """Quadro do dia: uma coluna por janela, com os slots ocupados e livres."""
    js = jsvc.janelas_do_dia(operacao_id, dia)
    js_todas = logistica_repo.janelas(operacao_id, apenas_ativas=False)
    regs = df.to_dict("records") if not df.empty else []
    grupos: dict = {j["id"]: [] for j in js}
    fora = []
    por_rotulo = {j["rotulo"]: j["id"] for j in js}
    for r in regs:
        jid = r.get("janela_id") if r.get("janela_id") in grupos else por_rotulo.get(_janela_txt(js_todas, r))
        (grupos[jid] if jid in grupos else fora).append(r)
    blocos = []
    for j in js:
        ativos = [r for r in grupos[j["id"]] if r.get("status") not in ("Cancelado", "No-show")]
        usados, total = len(ativos), int(j["slots"])
        cheia = usados >= total
        cls = "cheia" if cheia else ("ok" if usados else "livre")
        txt = "lotada" if cheia else f"{total - usados} livre(s)"
        pct = min(usados / total * 100, 100) if total else 0
        cards = "".join(_card(r) for r in sorted(grupos[j["id"]], key=lambda x: (
            x.get("status") in ("Cancelado", "No-show"), _txt(x.get("hora")))))
        vagas = "".join('<div class="pt-slot">○ slot livre</div>' for _ in range(max(total - usados, 0)))
        prod = f" · só {j['produto']}" if j.get("produto") else ""
        blocos.append(f'<div class="pt-jan"><div class="hd"><b>🕒 {_e(j["rotulo"])}</b><span class="{cls}">'
                      f'{usados}/{total} · {txt}</span></div><div class="sub">{total} slot(s){_e(prod)}'
                      f'{" · janela encerrada" if j["passou"] else ""}</div><div class="pt-bar"><i class="'
                      f'{"cheia" if cheia else ""}" style="width:{pct:.0f}%"></i></div>{cards}{vagas}</div>')
    if fora:
        titulo = "Fora das janelas" if js else "Descargas do dia"
        blocos.append(f'<div class="pt-jan"><div class="hd"><b>📋 {titulo}</b><span class="livre">{len(fora)}</span>'
                      f'</div><div class="sub">{"sem janela cadastrada neste horário" if js else "por horário"}</div>'
                      + "".join(_card(r) for r in sorted(fora, key=lambda x: _txt(x.get("hora")))) + "</div>")
    if not blocos:
        st.info(f"Nenhuma descarga em {dia:%d/%m} e nenhuma janela cadastrada para {jsvc.DIAS[dia.weekday()]}.")
        return
    st.markdown(_CSS + f'<div class="pt-quadro">{"".join(blocos)}</div>', unsafe_allow_html=True)


def proximos_dias(operacao_id: int, dias: int = 7) -> None:
    """Ocupação das janelas nos próximos dias (o que os motoristas já agendaram)."""
    hoje = tempo.hoje()
    todas = logistica_repo.janelas(operacao_id)
    prox = logistica_repo.agendamentos_df(operacao_id, hoje.isoformat(), (hoje + dt.timedelta(days=dias)).isoformat())
    if todas:
        rotulos = sorted({jsvc.rotulo(j) for j in todas})
        cab = "".join(f"<th>{_e(r)}</th>" for r in rotulos)
        linhas = []
        for i in range(dias + 1):
            d = hoje + dt.timedelta(days=i)
            js = {j["rotulo"]: j for j in jsvc.janelas_do_dia(operacao_id, d)}
            n = int(((prox["data"] == d.isoformat()) & ~prox["status"].isin(["Cancelado", "No-show"])).sum()) \
                if not prox.empty else 0
            tds = []
            for r in rotulos:
                j = js.get(r)
                if not j:
                    tds.append('<td class="na">—</td>')
                else:
                    cls = "cheia" if j["livres"] <= 0 else ("ok" if j["usados"] else "")
                    tds.append(f'<td class="{cls}">{j["usados"]}/{j["slots"]}</td>')
            nome = "Hoje" if i == 0 else "Amanhã" if i == 1 else jsvc.DIAS[d.weekday()]
            linhas.append(f"<tr><td><b>{nome}</b> {d:%d/%m} · {n} descarga(s)</td>{''.join(tds)}</tr>")
        st.markdown(_CSS + f'<div class="pt-dias"><table><thead><tr><th>Dia</th>{cab}</tr></thead>'
                    f'<tbody>{"".join(linhas)}</tbody></table></div>', unsafe_allow_html=True)
        st.caption("Ocupados / slots da janela. Vermelho = janela lotada (some do app do motorista).")
    vis = tabela_legivel(prox, logistica_repo.janelas(operacao_id, False), com_data=True)
    if not vis.empty:
        ui.tabela(vis)
        ui.downloads(vis, "agendamentos_descarga", key=f"dl_desc_prox_{operacao_id}")
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
    js_dia = jsvc.janelas_do_dia(operacao_id, dia)
    livres = sum(j["livres"] for j in js_dia if not j["passou"])
    tema.kpis([
        {"titulo": f"Agendados em {dia:%d/%m}", "valor": len(df), "icone": "🗓️", "status": "info", "dados": vis},
        {"titulo": "A caminho (App)", "valor": len(a_caminho), "icone": "🛣️", "status": "info", "dados": a_caminho,
         "detalhe": "saíram da cervejaria"},
        {"titulo": "No pátio agora", "valor": len(no_patio), "icone": "🅿️",
         "status": "atencao" if len(no_patio) else "info", "dados": no_patio},
        {"titulo": "Descarregados", "valor": len(filtro("Descarregado")), "icone": "✅", "status": "bom",
         "dados": filtro("Descarregado")},
        {"titulo": "Slots livres", "valor": livres if js_dia else "—", "icone": "🕒", "status": "info",
         "detalhe": f"em {len(js_dia)} janela(s)" if js_dia else "sem janelas cadastradas"},
        {"titulo": "No-show / cancelados", "valor": len(perdidos), "icone": "⚠️",
         "status": "serio" if len(filtro("No-show")) else "info", "dados": perdidos},
    ], key=f"kp_desc_{key}")

    tema.secao(f"🗓️ Agenda de {dia:%d/%m/%Y} ({jsvc.DIAS[dia.weekday()]})",
               "Cada coluna é uma janela da revenda. 📱 = agendado pelo motorista no App Carreteiro.")
    quadro_dia(operacao_id, dia, df)
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
    tela(chave=f"jan_{operacao_id}", titulo="Janelas de descarga da revenda", icone="🕒", df=df, por_linha=3,
         descricao="Horários em que o pátio recebe carretas e quantas cabem em cada intervalo (slots). "
                   "O motorista só vê as janelas com vaga — a cada agendamento a vaga é consumida.",
         campos=[Campo("hora_inicio", "Início", "opcoes", True, HORAS, padrao="07:00"),
                 Campo("hora_fim", "Fim", "opcoes", True, HORAS, padrao="09:00"),
                 Campo("slots", "Slots (carretas na janela)", "inteiro", True, padrao=2,
                       ajuda="Quantas carretas a revenda descarrega nesse intervalo."),
                 Campo("dias", "Dias da semana", "multi", True, {i: d for i, d in enumerate(jsvc.DIAS)},
                       padrao=jsvc.DIAS_PADRAO, na_tabela=False),
                 Campo("produto", "Só para o produto", "opcoes", False, {"Retornável": "Retornável",
                                                                        "Descartável": "Descartável"},
                       ajuda="Vazio = qualquer produto."),
                 Campo("ativo", "Situação", "opcoes", True, {1: "✅ Ativa", 0: "⏸️ Pausada"}, padrao=1)],
         colunas_extras=[("dias_txt", "Dias")],
         rotulo_registro=lambda r: f"{r['hora_inicio']}–{r['hora_fim']} · {jsvc.dias_texto(','.join(map(str, r['dias'])))}"
         if isinstance(r.get("dias"), list) else f"{r['hora_inicio']}–{r['hora_fim']}",
         salvar=lambda jid, d: jsvc.salvar_janela(operacao_id, jid, d["hora_inicio"], d["hora_fim"], d["slots"],
                                                  d.get("dias") or [], d.get("produto"), bool(d.get("ativo", 1))),
         excluir=lambda jid: logistica_repo.excluir("janelas_descarga", jid),
         aviso_vazio="Nenhuma janela cadastrada — o motorista informa a hora livremente.")


# --- Tela -----------------------------------------------------------------------------
def tela_patio(usuario: dict, operacao_id: int, key: str) -> None:
    consolidada = ui.somente_leitura(operacao_id)
    partes = {"dia": "🗓️ Agenda do dia", "prox": "📅 Próximos dias", "janelas": "🕒 Janelas & slots"}
    if consolidada:
        partes.pop("janelas")
    parte = ui._escolha(f"pt_parte_{key}", list(partes), "dia", formatar=partes.get, pills=True)
    if parte == "prox":
        tema.secao("📅 Próximos 7 dias", "O que já foi agendado (inclusive pelos motoristas no app) e as vagas de "
                   "cada janela.")
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
    js = logistica_repo.janelas(operacao_id)
    with st.form(f"f_desc_{key}", clear_on_submit=True):
        a, b, c = st.columns(3)
        data = a.date_input("Data", value=dia, format="DD/MM/YYYY")
        janela_id = hora = None
        if js:
            nomes = {j["id"]: f"{jsvc.rotulo(j)} · {jsvc.dias_texto(j['dias'])}" for j in js}
            janela_id = b.selectbox("Janela", list(nomes), format_func=nomes.get)
        else:
            hora = b.selectbox("Hora", HORAS, index=HORAS.index("08:00"))
        tipo = c.selectbox("Produto", TIPOS)
        e, f, g = st.columns(3)
        placa_sel = e.selectbox("Carreta cadastrada", ["— digitar placa —"] + carretas)
        placa_txt = f.text_input("Placa (se não estiver cadastrada)")
        slot = g.text_input("Doca (opcional)")
        obs = st.text_input("Observação")
        if st.form_submit_button("🚚 Agendar descarga", type="primary"):
            placa = placa_txt if placa_sel.startswith("—") else placa_sel
            ui.acao(agendar, operacao_id, data, hora, placa, slot, tipo, obs, usuario["login"], janela_id=janela_id,
                    sucesso="Descarga agendada!")


def render(usuario: dict, operacao_id: int) -> None:
    tela_patio(usuario, operacao_id, "pux")
