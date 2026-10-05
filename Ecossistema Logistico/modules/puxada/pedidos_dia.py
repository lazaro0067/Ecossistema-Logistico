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
.pp-ped { font-size:.86rem; color:#3d3c39; margin-top:.1rem; }
.pp-tipo { display:inline-block; font-size:.74rem; font-weight:700; padding:.1rem .5rem; border-radius:999px;
    background:#eef3fa; color:#2a5ca8; margin:.35rem 0 .25rem; }
.pp-emb { display:grid; grid-template-columns: repeat(4, 1fr); gap:.3rem; margin-top:.2rem; }
.pp-emb div { background:#f6f8fb; border-radius:8px; padding:.25rem .3rem; text-align:center; font-size:.7rem; color:#5f6b7a; }
.pp-emb div b { display:block; font-size:1rem; color:#0B1F3A; }
.pp-emb div.zero b { color:#c3c2bc; }
.pp-rod { font-size:.74rem; color:#77766f; margin-top:.4rem; }
.pp-placas { display:flex; flex-wrap:wrap; gap:.4rem; margin:.3rem 0 .8rem; }
.pp-placa { border:1.5px solid var(--c); border-radius:10px; padding:.3rem .6rem; font-size:.8rem; background:#fff; }
.pp-placa b { color:#0B1F3A; } .pp-placa span { color:var(--c); font-weight:700; }
</style>
"""
_COR_ST = {"Aberto": ("#b7791f", "#fdf3e1"), "Finalizado": ("#146c43", "#e8f6ee"), "Cancelado": ("#77766f", "#f0efec")}


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
            f'<div class="{"zero" if not float(r.get(k) or 0) else ""}"><b>{_f(r.get(k))}</b>{_e(rot)}</div>'
            for k, rot in EMBALAGENS_RETORNAVEL.items()) + "</div>"
    else:
        corpo = ""
    fim = ""
    if r["status"] == "Finalizado" and isinstance(r.get("finalizado_em"), str):
        d = tempo.parse_dt(r["finalizado_em"])
        fim = f" · ✅ {_e(r.get('finalizado_por'))} {d:%d/%m %H:%M}" if d else ""
    filial = f"🏢 {_e(r.get('filial'))} · " if com_filial else ""
    obs = f"<br>📝 {_e(r.get('observacao'))}" if isinstance(r.get("observacao"), str) and r.get("observacao") else ""
    return (f'<div class="pp-card {"cancelado" if r["status"] == "Cancelado" else ""}" style="--c:{cor};--f:{fundo}">'
            f'<div class="pp-top"><b>🚛 {_e(r["placa"])}</b><span class="pp-st">{svc.STATUS_ICONE.get(r["status"], "")} '
            f'{_e(r["status"])}</span></div><div class="pp-ped">Pedido <b>{_e(r["numero_pedido"])}</b> · '
            f'{_e(svc.rotulo_dia(dt.date.fromisoformat(str(r["data"])[:10])))}</div>'
            f'<span class="pp-tipo">{ICONE_TIPO.get(r["tipo"], "")} {_e(r["tipo"])} · {_f(r.get("paletes"))} palete(s)</span>'
            f'{corpo}<div class="pp-rod">{filial}lançado por {_e(r.get("criado_por"))}{fim}{obs}</div></div>')


def _cards(df: pd.DataFrame, com_filial: bool = False) -> None:
    if df.empty:
        return
    ordem = {"Aberto": 0, "Finalizado": 1, "Cancelado": 2}
    regs = sorted(df.to_dict("records"), key=lambda r: (ordem.get(r["status"], 3), str(r["placa"])))
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
        return f"{p} · {r['status']}" + (f" · sugestão {sug}" if sug else "")

    c1, c2, c3 = st.columns([1.6, 1, 1.4])
    placa = c1.selectbox("🚛 Placa *", ordem, key=f"{chave}_placa", format_func=rot_placa,
                         index=ordem.index(atual["placa"]) if atual else 0)
    st_placa = info.get(placa, {}).get("status")
    if st_placa and st_placa != "Disponível":
        c1.caption(f"⚠️ Esta placa está **{st_placa}** em {d:%d/%m}.")
    numero = c2.text_input("Nº do pedido *", value=(atual or {}).get("numero_pedido") or "", key=f"{chave}_num")
    sug = info.get(placa, {}).get("sugestao")
    padrao = (atual or {}).get("tipo") or (sug if sug in SUGESTAO_PEDIDO else None)
    tipo = c3.radio("Tipo *", SUGESTAO_PEDIDO, horizontal=True, key=f"{chave}_tipo_{placa}",
                    index=SUGESTAO_PEDIDO.index(padrao) if padrao in SUGESTAO_PEDIDO else None,
                    format_func=lambda t: f"{ICONE_TIPO.get(t, '')} {t}")
    qtds, paletes = {}, 0.0
    if tipo == "Retornável":
        st.markdown("**♻️ Paletes por embalagem**")
        cols = st.columns(len(EMBALAGENS_RETORNAVEL))
        for col, (k, rot) in zip(cols, EMBALAGENS_RETORNAVEL.items()):
            qtds[k] = col.number_input(rot, min_value=0.0, step=1.0, format="%.0f", key=f"{chave}_{k}",
                                       value=float((atual or {}).get(k) or 0))
        st.caption(f"Total: **{_f(sum(qtds.values()))} palete(s)**")
    elif tipo == "Descartável":
        paletes = st.number_input("🥫 Quantidade de paletes *", min_value=0.0, step=1.0, format="%.0f",
                                  key=f"{chave}_pal", value=float((atual or {}).get("paletes") or 0))
    obs = st.text_input("Observação", value=(atual or {}).get("observacao") or "", key=f"{chave}_obs",
                        placeholder="opcional")
    if st.button("💾 Salvar pedido" if not atual else "💾 Salvar alteração", type="primary", key=f"{chave}_ok"):
        try:
            svc.salvar_pedido(operacao_id, atual["id"] if atual else None, d, placa, numero, tipo, qtds, paletes, obs,
                              usuario.get("nome") or usuario.get("login") or "")
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            st.session_state[f"pp_form_v_{operacao_id}"] = st.session_state.get(f"pp_form_v_{operacao_id}", 0) + 1
            ui.avisar(f"Pedido {numero} salvo — já aparece para o Ressuprimento e o Armazém.")
            st.rerun()


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
    com_pedido = set(df[df["status"] != "Cancelado"]["placa"].str.upper()) if not df.empty else set()
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
    abertos = df[df["status"] == "Aberto"]
    if not abertos.empty:
        with st.container(key="cad_alt_pp"):
            st.markdown('<div class="eco-alt-titulo">✏️ Alterar ou cancelar pedido</div>', unsafe_allow_html=True)
            nomes = {int(r["id"]): f"{r['placa']} · pedido {r['numero_pedido']} · {r['tipo']}"
                     for r in abertos.to_dict("records")}
            pid = st.selectbox("Pedido", [None, *nomes], key=f"pp_alt_{d}",
                               format_func=lambda i: "Selecione..." if i is None else nomes[i])
            if pid:
                _form(usuario, operacao_id, d, repo.pedido(pid), f"pp_a_{pid}_{v}")
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
    _kpis(df, "kp_pp_arm", [{"titulo": "Abertos de dias anteriores", "valor": len(atrasados), "icone": "⏰",
                            "status": "critico" if len(atrasados) else "bom",
                            "dados": svc.tabela(atrasados, consolidada)}])
    opcoes = {"D0": svc.rotulo_dia(ds[0]), "D1": svc.rotulo_dia(ds[1])}
    if len(atrasados):
        opcoes["ATR"] = f"⏰ Pendentes anteriores ({len(atrasados)})"
    esc = ui._escolha("pp_arm_dia", list(opcoes), "D0", formatar=opcoes.get, pills=True)
    if esc == "ATR":
        lista = atrasados
    else:
        d = ds[0] if esc == "D0" else ds[1]
        lista = df[df["data"] == d.isoformat()] if not df.empty else df
    st.caption("Confira a carga e clique em **✅ Finalizado** — o status muda na Puxada e no Ressuprimento na hora.")
    if lista.empty:
        st.info("Nenhum pedido para este dia.")
        return
    regs = lista.sort_values(["status", "placa"]).to_dict("records")
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
