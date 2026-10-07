"""Puxada › App Carreteiro — visão da equipe da Puxada.

• Ao vivo: onde está cada viagem agora e as placas paradas na revenda.
• Viagens & NFs: histórico com correção de horários (salva sozinho), GPS, notas e fotos.
• Acessos dos motoristas: cria o login do motorista (e-mail ou CPF/celular) e senha provisória.
• Revenda (GPS): ponto e raio da revenda usados para conferir chegada e saída (TMA).
"""
import datetime as dt

import pandas as pd
import streamlit as st

from config.settings import RAIO_REVENDA_PADRAO_M
from core import tema, tempo, ui
from modules.componentes.autosave import editor_autosave
from modules.componentes.geolocalizacao import localizacao, ponto
from repositories import carreteiro_repo as repo
from services import carreteiro_service as svc
from services.erros import RegraNegocioError

FASES = {  # etapa já feita -> (onde está, status de cor)
    "inicio": ("Indo para a cervejaria", "info"),
    "apresentado": ("Aguardando chamada", "atencao"),
    "chamado": ("Carregando", "atencao"),
    "carregado": ("Carregado — falta agendar a descarga", "atencao"),
    "agendado": ("Descarga agendada — saindo da cervejaria", "atencao"),
    "saida": ("Retornando à revenda", "info"),
    "chegada": ("Na revenda — descarga", "bom"),
}
_FMT = "%d/%m/%Y %H:%M"


def mapa_url(lat, lon) -> str | None:
    """Link do Google Maps no ponto exato (abre no celular ou no computador)."""
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if la != la or lo != lo:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={la:.6f},{lo:.6f}"


def _fmt(ts) -> str:
    d = tempo.parse_dt(ts)
    return d.strftime(_FMT) if d else ""


def _desde(ts) -> float | None:
    d = tempo.parse_dt(ts)
    return (tempo.agora() - d).total_seconds() / 3600 if d else None


# --- Ao vivo -----------------------------------------------------------------
_COLS_VIAGEM = {"id": "Nº", "motorista": "Motorista", "placa": "Placa", "numero_pedido": "Pedido",
                "destino": "Destino", "etapa": "Etapa atual", "desde": "Desde", "agendamento": "Agendamento"}


def _tabela_viagens(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(_COLS_VIAGEM))
    linhas = []
    for r in df.to_dict("records"):
        ult = svc.ultima_etapa(r)
        linhas.append({"id": r["id"], "motorista": r["motorista"], "placa": r["placa"],
                       "numero_pedido": r["numero_pedido"], "destino": r.get("destino"),
                       "etapa": svc.ETAPAS[ult]["nome"] if ult else "—",
                       "desde": _fmt(r[svc.ETAPAS[ult]["coluna"]]) if ult else "",
                       "agendamento": _fmt(r.get("agendamento"))})
    return pd.DataFrame(linhas)


@st.dialog("🚛 Viagem", width="large")
def _dialogo_viagem(vid: int) -> None:
    v = repo.viagem(vid)
    if not v:
        st.info("Viagem não encontrada.")
        return
    st.markdown(f"#### {v['placa']} · {v['motorista']}")
    st.caption(f"Pedido {v['numero_pedido']} · {v.get('destino') or '—'} · "
               f"agendamento {_fmt(v.get('agendamento')) or '—'} · {v['status']}")
    aviso = svc.mensagem_apresentacao(v)
    if aviso:
        getattr(st, "error" if aviso[0] == "error" else "success")(aviso[1])
    ev = repo.eventos_df(vid)
    gps = {r["etapa"]: r for r in ev.to_dict("records")} if not ev.empty else {}
    linhas = []
    for chave in svc.ORDEM:
        e = svc.ETAPAS[chave]
        g = gps.get(chave, {})
        dentro = g.get("dentro_raio")
        linhas.append({"etapa": f"{e['icone']} {e['nome']}", "data_hora": _fmt(v.get(e["coluna"])) or "⏳ pendente",
                       "mapa": mapa_url(g.get("lat"), g.get("lon")) if g else None,
                       "gps": "" if not g or g.get("lat") is None else
                       (f"{g.get('distancia_m'):.0f} m da revenda" if g.get("distancia_m") == g.get("distancia_m")
                        and g.get("distancia_m") is not None else "registrado")
                       + ("" if dentro is None or dentro != dentro else (" ✅" if int(dentro) else " ⚠️ fora do raio"))})
    pos = repo.ultimas_posicoes([vid]).get(vid)
    if pos:
        st.link_button(f"📍 Ver a última localização do motorista no mapa ({svc.ETAPAS.get(pos['etapa'], {}).get('nome', pos['etapa'])}"
                       f" · {_fmt(pos['ts'])})", mapa_url(pos["lat"], pos["lon"]), type="primary")
    ui.tabela(pd.DataFrame(linhas), column_config={
        "etapa": "Etapa", "data_hora": "Data/hora", "gps": "GPS",
        "mapa": st.column_config.LinkColumn("Localização", display_text="📍 ver no mapa")})
    pars = repo.paradas_df([vid])
    for p in pars.to_dict("records"):
        fim = _fmt(p["fim"]) if isinstance(p.get("fim"), str) else "em andamento"
        st.warning(f"🔧 Parada para manutenção: {_fmt(p['inicio'])} → {fim}"
                   + (f" · {p['observacao']}" if isinstance(p.get("observacao"), str) else ""))
    _fotos(vid, prefixo="dlg_")


def _motoristas_agora(operacao_id: int) -> None:
    """Situação de cada motorista: em viagem, interjornada (com a hora em que libera), em serviço, férias, disponível."""
    from services import disp_motoristas_service as dms

    try:
        ag = dms.agora(operacao_id)
    except Exception:
        return
    if ag.empty:
        return
    tab = pd.DataFrame({"Motorista": ag["nome"],
                        "Situação": [f"{dms.ICONES.get(x, '')} {x}" for x in ag["status"]],
                        "Detalhe": ag["detalhe"].fillna("")})

    def card(status, titulo, cor):
        f = tab[ag["status"].values == status]
        return {"titulo": titulo, "valor": len(f), "icone": dms.ICONES.get(status, ""),
                "status": cor if len(f) else "neutro", "dados": f if len(f) else None}

    tema.secao("👤 Motoristas agora", "Inclui quem está em interjornada (descanso de 11 h) e até que horas.")
    tema.kpis([card("Disponível", "Disponíveis", "bom"), card("Em viagem", "Em viagem", "info"),
               card("Interjornada", "Em interjornada", "atencao"), card("Em serviço", "Em serviço", "info"),
               card("Férias", "De férias", "neutro")], key="kp_car_mot")


def _ao_vivo(operacao_id: int) -> None:
    df = repo.viagens_df(operacao_id, de=(tempo.hoje() - dt.timedelta(days=30)).isoformat())
    ativas = df[df["status"] == repo.EM_VIAGEM] if not df.empty else df
    hoje = tempo.hoje().isoformat()
    finalizadas = df[df["ts_fim"].fillna("").str[:10] == hoje] if not df.empty else df
    fases = [svc.ultima_etapa(r) for r in ativas.to_dict("records")] if not ativas.empty else []
    tab_ativas = _tabela_viagens(ativas)

    def em(*etapas):
        return tab_ativas[[f in etapas for f in fases]] if fases else tab_ativas

    manut = repo.paradas_ativas(operacao_id)
    em_manut = ativas[ativas["id"].isin(list(manut))] if not ativas.empty else ativas
    parados = svc.placas_na_revenda(operacao_id)
    parados = parados[~parados["placa"].isin(ativas["placa"])] if not ativas.empty else parados
    tab_parados = parados.assign(chegada=parados["chegada"].dt.strftime(_FMT),
                                 parada=parados["parada_h"].map(svc.formatar_duracao))[
        ["placa", "motorista", "chegada", "parada"]] if not parados.empty else parados
    col_parados = {"placa": "Placa", "motorista": "Último motorista", "chegada": "Chegou em", "parada": "Parada há"}
    def card(titulo, icone, etapas, status="info", detalhe=None):
        n = sum(f in etapas for f in fases)
        return {"titulo": titulo, "valor": n, "icone": icone, "status": status if n else "neutro",
                "detalhe": detalhe, "dados": em(*etapas), "colunas": _COLS_VIAGEM}

    tema.secao("🚛 Viagens por fase", "Cada etapa do App Carreteiro. Toque no card para ver quem está nela.")
    tema.kpis([
        {"titulo": "Em viagem agora", "valor": len(ativas), "icone": "🚛", "status": "info", "dados": tab_ativas,
         "colunas": _COLS_VIAGEM},
        card("Indo p/ cervejaria", "🛣️", ("inicio",), detalhe="iniciou a viagem"),
        card("Aguardando chamada", "🙋", ("apresentado",), "atencao", "apresentou na cervejaria"),
        card("Carregando", "📣", ("chamado",), "atencao", "chamado p/ carregar"),
        card("Carregado · falta agendar", "📦", ("carregado",), "critico", "ainda sem descarga agendada"),
        card("Descarga agendada", "🗓️", ("agendado",), "info", "saindo da cervejaria"),
        card("Retornando", "↩️", ("saida",), "info", "saiu da cervejaria"),
        card("Na revenda · descarga", "🏁", ("chegada",), "bom", "chegou, falta finalizar"),
        {"titulo": "Parada p/ manutenção", "valor": len(em_manut), "icone": "🔧",
         "status": "critico" if len(em_manut) else "bom", "dados": _tabela_viagens(em_manut), "colunas": _COLS_VIAGEM},
        {"titulo": "Placas paradas na revenda", "valor": len(parados), "icone": "🅿️", "status": "neutro",
         "dados": tab_parados, "colunas": col_parados},
        {"titulo": "Finalizadas hoje", "valor": len(finalizadas), "icone": "✅",
         "status": "bom" if len(finalizadas) else "neutro", "dados": _tabela_viagens(finalizadas),
         "colunas": _COLS_VIAGEM},
    ], key="kp_car_vivo")
    _motoristas_agora(operacao_id)
    c1, c2 = st.columns([1, 5])
    if c1.button("🔄 Atualizar", key="car_gv_atualizar"):
        st.rerun()
    c2.caption(f"Atualizado às {tempo.agora().strftime('%H:%M')}. Toque num card para ver os detalhes.")

    tema.secao("Viagens em andamento", "Toque na viagem para ver as etapas, o GPS e as fotos das NFs.")
    if ativas.empty:
        st.info("Nenhuma viagem em andamento agora.")
    else:
        cards = []
        for r, fase in zip(ativas.to_dict("records"), fases):
            onde, status = FASES.get(fase, ("—", "neutro"))
            ha = svc.formatar_duracao(_desde(r[svc.ETAPAS[fase]["coluna"]]))
            selo = None
            if r.get("apresentou_no_prazo") is not None and not pd.isna(r.get("apresentou_no_prazo")):
                if int(r["apresentou_no_prazo"]):
                    selo = "Apresentou no prazo"
                else:
                    status, selo = "critico", f"Atraso {svc.formatar_duracao((r.get('atraso_min') or 0) / 60)}"
            elif r.get("agendamento") and not r.get("ts_apresentado"):
                ag = tempo.parse_dt(r["agendamento"])
                if ag and tempo.agora() > ag:
                    status, selo = "critico", "Agendamento vencido"
            pm = manut.get(int(r["id"]))
            if pm:
                ini = tempo.parse_dt(pm["inicio"])
                onde, status = "🔧 Em manutenção", "critico"
                selo = f"parada há {svc.formatar_duracao(_desde(pm['inicio']))}" if ini else "manutenção"
            cards.append({
                "titulo": f"{r['placa']} · {r['motorista']}", "icone": "🚛", "valor": onde, "status": status,
                "selo": selo or svc.ETAPAS[fase]["nome"],
                "detalhe": f"Pedido {r['numero_pedido']} · {svc.ETAPAS[fase]['nome']} há {ha}",
                "ver": "viagem", "ao_clicar": lambda vid=int(r["id"]): _dialogo_viagem(vid)})
        tema.kpis(cards, key="kp_car_ativas")

    tema.secao("Placas paradas na revenda", "Chegaram e ainda não iniciaram nova viagem (TMA em aberto).")
    if parados.empty:
        st.info("Nenhuma placa parada na revenda.")
    else:
        ui.tabela(tab_parados, column_config=col_parados)


# --- Viagens & NFs -------------------------------------------------------------
def _fotos(vid: int, prefixo: str = "") -> None:
    notas = repo.notas(vid)
    if not notas:
        st.caption("Sem notas fiscais lançadas.")
        return
    for n in notas:
        st.markdown(f"**🧾 NF {n['numero_nf']}** · {n['fotos']} foto(s) · lançada em {_fmt(n['criado_em'])}")
        fotos = repo.fotos(vid, n["id"])
        imgs = [f for f in fotos if (f["tipo"] or "").startswith("image/")]
        if imgs:
            cols = st.columns(min(4, len(imgs)))
            for i, f in enumerate(imgs):
                cols[i % len(cols)].image(f["conteudo"], caption=f["nome"])
        for f in fotos:
            if f not in imgs:
                st.download_button(f"⬇️ {f['nome']}", f["conteudo"], file_name=f["nome"] or "arquivo",
                                   mime=f["tipo"] or "application/octet-stream", key=f"car_dl_{prefixo}{f['id']}")


def _viagens(usuario: dict, operacao_id: int) -> None:
    c1, c2, c3 = st.columns([1, 1, 2])
    de = c1.date_input("De", value=tempo.hoje().replace(day=1), format="DD/MM/YYYY", key="car_v_de")
    ate = c2.date_input("Até", value=tempo.hoje(), format="DD/MM/YYYY", key="car_v_ate")
    mots = repo.motoristas_lista(operacao_id)
    mid = ui.select_registro("Motorista", mots, key="car_v_mot", container=c3)
    df = repo.viagens_df(operacao_id, de.isoformat() if de else None, ate.isoformat() if ate else None,
                         motorista_id=mid, incluir_canceladas=True)
    if df.empty:
        st.info("Nenhuma viagem no período.")
        return
    ed = df[["id", "status", "motorista", "numero_pedido", "placa", "destino", "agendamento", *repo.COLUNAS_TS,
             "apresentou_no_prazo", "qtd_nfs", "qtd_fotos"]].copy()
    for c in ["agendamento", *repo.COLUNAS_TS]:
        ed[c] = ed[c].map(_fmt)
    ed["apresentou_no_prazo"] = ed["apresentou_no_prazo"].map(
        lambda x: "" if pd.isna(x) else ("✅ No prazo" if int(x) else "⚠️ Fora"))

    def alterar(linha, alt):
        svc.corrigir_viagem(int(linha["id"]), alt, usuario["nome"])

    st.caption("✏️ Corrija horários, pedido ou placa direto na tabela (formato DD/MM/AAAA HH:MM) — salva sozinho.")
    rot = {e["coluna"]: e["nome"] for e in svc.ETAPAS.values()}
    editor_autosave(ed, f"ed_car_viagens_{operacao_id}", ["numero_pedido", "placa", "agendamento", *repo.COLUNAS_TS],
                    alterar, column_config={
                        "id": st.column_config.NumberColumn("Nº", width="small"), "status": "Status",
                        "motorista": "Motorista", "numero_pedido": "Pedido ✏️", "placa": "Placa ✏️",
                        "destino": "Destino", "agendamento": "Agendamento ✏️",
                        **{c: f"{r} ✏️" for c, r in rot.items()},
                        "apresentou_no_prazo": "Apresentação", "qtd_nfs": "NFs", "qtd_fotos": "Fotos"})
    exp = df.copy()
    exp["notas_fiscais"] = [repo.nfs_texto(int(i)) for i in exp["id"]]
    ui.downloads(exp.drop(columns=["operacao_id", "motorista_id"]), "viagens_carreteiro", key="dl_car_viagens")

    tema.secao("Detalhe da viagem", "GPS de cada etapa, notas fiscais e fotos.")
    regs = [{"id": int(r.id), "nome": f"Nº {r.id} · {_fmt(r.ts_inicio)} · {r.motorista} · {r.placa} · Pedido {r.numero_pedido}"}
            for r in df.itertuples()]
    vid = ui.select_registro("Viagem", regs, key="car_v_det")
    if not vid:
        return
    v = repo.viagem(vid)
    ev = repo.eventos_df(vid)
    if not ev.empty:
        ev["etapa"] = ev["etapa"].map(lambda k: svc.ETAPAS.get(k, {}).get("nome", k))
        ev["ts"] = ev["ts"].map(_fmt)
        ev["dentro_raio"] = ev["dentro_raio"].map(lambda x: "" if pd.isna(x) else ("✅ Dentro" if int(x) else "⚠️ Fora"))
        ui.tabela(ev, column_config={"etapa": "Etapa", "ts": "Data/hora", "lat": "Latitude", "lon": "Longitude",
                                     "precisao_m": "Precisão (m)", "distancia_m": "Distância da revenda (m)",
                                     "dentro_raio": "Raio da revenda"})
    pars = repo.paradas_df([vid])
    if not pars.empty:
        st.markdown("**🔧 Paradas para manutenção**")
        ui.tabela(pars.assign(
            inicio=pars["inicio"].map(_fmt), fim=pars["fim"].map(lambda x: _fmt(x) if isinstance(x, str) else "em andamento"),
            duracao=[svc.formatar_duracao(((tempo.parse_dt(f) if isinstance(f, str) else tempo.agora())
                                           - tempo.parse_dt(i)).total_seconds() / 3600) for i, f in zip(pars["inicio"], pars["fim"])],
        )[["inicio", "fim", "duracao", "observacao"]], column_config={
            "inicio": "Início", "fim": "Fim", "duracao": "Tempo parado", "observacao": "Motivo"}, baixar=False)
    if v.get("observacao"):
        st.caption(f"📝 {v['observacao']}")
    _fotos(vid)
    if v["status"] == repo.EM_VIAGEM:
        with st.popover("🚫 Cancelar esta viagem"):
            motivo = st.text_input("Motivo", key=f"car_cancel_mot_{vid}")
            if st.button("Confirmar cancelamento", key=f"car_cancel_{vid}"):
                ui.acao(svc.cancelar_viagem, vid, motivo, usuario["nome"], sucesso="Viagem cancelada.")


# --- Acessos dos motoristas ------------------------------------------------------
def _link_relato(operacao_id: int) -> None:
    """Link do formulário (ex.: Microsoft Forms / Google Forms) do botão “📝 Faça seu relato aqui” do app."""
    if ui.somente_leitura(operacao_id):
        return
    atual = repo.link_relato(operacao_id)
    with st.expander(f"📝 Formulário “Faça seu relato aqui” · {'✅ configurado' if atual else 'não configurado'}",
                     expanded=not atual):
        st.caption("Cole o link do formulário. No app, o motorista toca em “📝 Faça seu relato aqui” e ele abre na hora.")
        with st.form(f"car_relato_{operacao_id}"):
            link = st.text_input("Link do formulário", value=atual, placeholder="https://forms.office.com/...")
            c1, c2 = st.columns(2)
            salvar = c1.form_submit_button("💾 Salvar link", type="primary")
            limpar = c2.form_submit_button("🗑️ Remover") if atual else False
        if salvar:
            ui.acao(svc.salvar_link_relato, operacao_id, link, sucesso="Link do relato salvo — já aparece no app.")
        if limpar:
            ui.acao(svc.salvar_link_relato, operacao_id, None, sucesso="Link do relato removido.")
        if atual:
            st.link_button("🔗 Testar o link", atual)


def _acessos(operacao_id: int) -> None:
    df = repo.acessos_df(operacao_id)
    if df.empty:
        st.info("Cadastre os motoristas em **⚙️ Cadastros › 👤 Motoristas** e volte aqui para criar o acesso.")
        return
    from modules.puxada.app_motorista import link_do_app, link_whatsapp

    link = link_do_app()
    nova = st.session_state.pop("car_senha_nova", None)
    if nova:
        tel = next((r["telefone"] for r in df.to_dict("records") if r["nome"] == nova["nome"]), None)
        msg = (f"Olá, {nova['nome'].split()[0]}! Seu acesso ao App Carreteiro do Grupo Lima:\n\n"
               f"🔗 {link}\n👤 Login: {nova['login']}\n🔑 Senha provisória: {nova['senha']}\n\n"
               "No primeiro acesso você cria a sua senha. Dica: no celular, use “Adicionar à tela inicial”.")
        st.success(f"Acesso de **{nova['nome']}** pronto. A senha aparece só agora — envie ao motorista:")
        st.code(msg, language=None)
        st.link_button(f"📲 Enviar para {nova['nome'].split()[0]} pelo WhatsApp", link_whatsapp(msg, tel),
                       type="primary")
    ui.tabela(df.drop(columns=["usuario_id"]).assign(ultimo_acesso=df["ultimo_acesso"].fillna("")), column_config={
        "id": None, "nome": "Motorista", "cnh": "CNH", "telefone": "Telefone", "acesso": "Login",
        "situacao": "Situação", "ultimo_acesso": "Último acesso"})

    _link_relato(operacao_id)
    regs = df.to_dict("records")
    c1, c2 = st.columns(2)
    with c1, st.form("car_acesso", clear_on_submit=True):
        tema.secao("Criar / alterar acesso")
        mid = ui.select_registro("Motorista", regs, key="car_ac_mot", permitir_vazio=False)
        acesso = st.text_input("Login do motorista", placeholder="e-mail, CPF ou celular (só números)")
        if st.form_submit_button("💾 Salvar acesso", type="primary"):
            try:
                r = svc.salvar_acesso_motorista(mid, acesso)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                nome = next(x["nome"] for x in regs if x["id"] == mid)
                if r["senha"]:
                    st.session_state["car_senha_nova"] = {"nome": nome, **r}
                ui.avisar(f"Acesso de {nome} salvo.")
                st.rerun()
    com_acesso = [r for r in regs if r.get("usuario_id")]
    with c2:
        tema.secao("Senha e bloqueio")
        if not com_acesso:
            st.caption("Nenhum motorista com acesso ainda.")
            return
        mid2 = ui.select_registro("Motorista com acesso", com_acesso, key="car_ac_mot2", permitir_vazio=False)
        sel = next(x for x in com_acesso if x["id"] == mid2)
        b1, b2 = st.columns(2)
        if b1.button("🔄 Gerar nova senha", key="car_ac_reset"):
            try:
                senha = svc.nova_senha_motorista(mid2)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["car_senha_nova"] = {"nome": sel["nome"], "login": sel["acesso"], "senha": senha}
                st.rerun()
        from services import disp_motoristas_service as dms

        bloq = dms.bloqueio_acesso(int(mid2))
        if bloq:
            st.warning(f"😴 {sel['nome'].split()[0]} finalizou a viagem — app bloqueado até {bloq:%d/%m %H:%M} "
                       "(interjornada).")
            if st.button("🔓 Liberar o app agora", key="car_ac_liberar"):
                ui.acao(dms.liberar_acesso, int(mid2), sucesso="Acesso liberado antes do fim da interjornada.")
        ativo = sel["situacao"] == "Ativo"
        if b2.button("🔒 Bloquear" if ativo else "🔓 Desbloquear", key="car_ac_bloq"):
            ui.acao(svc.bloquear_acesso, mid2, not ativo, sucesso="Acesso bloqueado." if ativo else "Acesso liberado.")
        msg = (f"Olá, {sel['nome'].split()[0]}! Link do App Carreteiro do Grupo Lima:\n{link}\n\n"
               f"Login: {sel['acesso']} (use a senha que você criou).")
        st.link_button(f"📲 Mandar o link para {sel['nome'].split()[0]} pelo WhatsApp",
                       link_whatsapp(msg, sel.get("telefone")), **ui.LARGURA)
        if not sel.get("telefone"):
            st.caption("Sem telefone no cadastro — o WhatsApp abre para você escolher o contato.")


# --- Revenda (GPS) --------------------------------------------------------------------
def _localizacoes(operacao_id: int) -> None:
    """Último ponto de GPS de cada viagem em andamento, com link para o mapa."""
    df = repo.viagens_df(operacao_id)
    ativas = df[df["status"] == repo.EM_VIAGEM] if not df.empty else df
    tema.secao("📍 Onde estão os motoristas",
               "Último ponto de GPS enviado pelo app em cada etapa. Toque em “ver no mapa” para abrir a localização exata.")
    if ativas.empty:
        st.info("Nenhuma viagem em andamento agora.")
        return
    pos = repo.ultimas_posicoes([int(i) for i in ativas["id"]])
    linhas = []
    for r in ativas.to_dict("records"):
        p = pos.get(int(r["id"]))
        ult = svc.ultima_etapa(r)
        linhas.append({"Motorista": r["motorista"], "Placa": r["placa"], "Pedido": r["numero_pedido"],
                       "Etapa atual": svc.ETAPAS[ult]["nome"] if ult else "—",
                       "Último GPS": (f"{svc.ETAPAS.get(p['etapa'], {}).get('nome', p['etapa'])} · {_fmt(p['ts'])}"
                                      if p else "sem GPS (celular não permitiu)"),
                       "Precisão": f"±{p['precisao_m']:.0f} m" if p and p.get("precisao_m") else "",
                       "Mapa": mapa_url(p["lat"], p["lon"]) if p else None})
    ui.tabela(pd.DataFrame(linhas), column_config={
        "Mapa": st.column_config.LinkColumn("Localização", display_text="📍 ver no mapa")},
        baixar="localizacao_motoristas")
    st.caption("A posição é a do último toque do motorista no app (cada etapa grava o GPS, se o celular permitir).")


def _revenda(operacao_id: int) -> None:
    _localizacoes(operacao_id)
    rev = repo.revenda(operacao_id)
    tema.secao("Ponto da revenda para o GPS",
               "Com o ponto e o raio salvos, cada “Chegada na revenda” e “Iniciar viagem” é conferido pelo GPS "
               "do celular — o TMA passa a mostrar quantas paradas foram confirmadas dentro da revenda.")
    if rev.get("lat") is not None:
        st.success(f"Ponto salvo: {rev['lat']:.6f}, {rev['lon']:.6f} · raio {int(rev.get('raio_m') or RAIO_REVENDA_PADRAO_M)} m")
    else:
        st.warning("Ponto da revenda ainda não cadastrado — o TMA é calculado só pelos horários.")
    st.caption("Dica: estando no pátio da revenda, permita a localização abaixo e toque em “Usar minha localização”.")
    geo = ponto(localizacao(key="geo_gestor_revenda"))
    if geo and st.button(f"📍 Usar minha localização (±{geo.get('precisao') or '?'} m)", key="car_rev_usar"):
        st.session_state["car_rev_lat"], st.session_state["car_rev_lon"] = float(geo["lat"]), float(geo["lon"])
    st.session_state.setdefault("car_rev_lat", float(rev["lat"]) if rev.get("lat") is not None else 0.0)
    st.session_state.setdefault("car_rev_lon", float(rev["lon"]) if rev.get("lon") is not None else 0.0)
    c1, c2, c3 = st.columns(3)
    lat = c1.number_input("Latitude", min_value=-90.0, max_value=90.0, format="%.6f", step=0.0001, key="car_rev_lat")
    lon = c2.number_input("Longitude", min_value=-180.0, max_value=180.0, format="%.6f", step=0.0001, key="car_rev_lon")
    raio = c3.number_input("Raio (metros)", min_value=30, max_value=5000, step=50,
                           value=int(rev.get("raio_m") or RAIO_REVENDA_PADRAO_M), key="car_rev_raio")
    b1, b2 = st.columns([1, 4])
    if b1.button("💾 Salvar ponto", type="primary", key="car_rev_salvar"):
        ui.acao(svc.salvar_revenda, operacao_id, lat, lon, raio, sucesso="Ponto da revenda salvo.")
    if rev.get("lat") is not None and b2.button("Remover ponto", key="car_rev_limpar"):
        ui.acao(svc.salvar_revenda, operacao_id, None, None, None, sucesso="Ponto removido.")
    if lat or lon:
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=15, size=float(raio))


def _painel_link() -> None:
    """Link do App Carreteiro sempre à mão: copiar, abrir ou mandar pelo WhatsApp."""
    from modules.puxada.app_motorista import link_do_app, link_whatsapp

    link = link_do_app()
    with st.expander("📲 Link do App Carreteiro — copiar ou enviar pelo WhatsApp", expanded=False):
        st.caption("O mesmo link para os motoristas das três operações. Toque no ícone ⧉ à direita para copiar.")
        st.code(link, language=None)
        msg = (f"🚛 App Carreteiro — Grupo Lima\nRegistre cada etapa da sua viagem por aqui:\n{link}\n\n"
               "Entre com o seu CPF/celular e a senha que a Puxada te passou.")
        c1, c2 = st.columns(2)
        c1.link_button("📲 Enviar pelo WhatsApp", link_whatsapp(msg), type="primary", **ui.LARGURA)
        c2.link_button("🔗 Abrir o app", link, **ui.LARGURA)


def render(usuario: dict, operacao_id: int) -> None:
    _painel_link()
    abas = st.tabs(["📡 Ao vivo", "🗂️ Viagens & NFs", "🔑 Acessos dos motoristas", "📍 Revenda (GPS)"])
    with abas[0]:
        _ao_vivo(operacao_id)
    with abas[1]:
        _viagens(usuario, operacao_id)
    with abas[2]:
        _acessos(operacao_id)
    with abas[3]:
        _revenda(operacao_id)
