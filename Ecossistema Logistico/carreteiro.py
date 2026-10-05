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
    "carregado": ("Carregado — aguardando saída", "atencao"),
    "saida": ("Retornando à revenda", "info"),
    "chegada": ("Na revenda — descarga", "bom"),
}
_FMT = "%d/%m/%Y %H:%M"


def _fmt(ts) -> str:
    d = tempo.parse_dt(ts)
    return d.strftime(_FMT) if d else ""


def _desde(ts) -> float | None:
    d = tempo.parse_dt(ts)
    return (tempo.agora() - d).total_seconds() / 3600 if d else None


# --- Ao vivo -----------------------------------------------------------------
def _ao_vivo(operacao_id: int) -> None:
    df = repo.viagens_df(operacao_id, de=(tempo.hoje() - dt.timedelta(days=30)).isoformat())
    ativas = df[df["status"] == repo.EM_VIAGEM] if not df.empty else df
    hoje = tempo.hoje().isoformat()
    fin_hoje = int((df["ts_fim"].fillna("").str[:10] == hoje).sum()) if not df.empty else 0
    fases = [svc.ultima_etapa(r) for r in ativas.to_dict("records")] if not ativas.empty else []
    parados = svc.placas_na_revenda(operacao_id)
    parados = parados[~parados["placa"].isin(ativas["placa"])] if not ativas.empty else parados
    tema.kpis([
        {"titulo": "Em viagem agora", "valor": len(ativas), "icone": "🚛", "status": "info"},
        {"titulo": "Indo p/ cervejaria", "valor": fases.count("inicio"), "icone": "🛣️", "status": "info"},
        {"titulo": "Na cervejaria", "valor": sum(f in ("apresentado", "chamado", "carregado") for f in fases),
         "icone": "🏭", "status": tema.status_contagem(sum(f in ("apresentado", "chamado") for f in fases), 3, 6)},
        {"titulo": "Retornando", "valor": fases.count("saida"), "icone": "↩️", "status": "info"},
        {"titulo": "Placas paradas na revenda", "valor": len(parados), "icone": "🅿️", "status": "neutro"},
        {"titulo": "Finalizadas hoje", "valor": fin_hoje, "icone": "✅", "status": "bom" if fin_hoje else "neutro"},
    ])
    c1, c2 = st.columns([1, 5])
    if c1.button("🔄 Atualizar", key="car_gv_atualizar"):
        st.rerun()
    c2.caption(f"Atualizado às {tempo.agora().strftime('%H:%M')}. Os horários são lançados pelos motoristas no celular.")

    tema.secao("Viagens em andamento")
    if ativas.empty:
        st.info("Nenhuma viagem em andamento agora.")
    else:
        cards = []
        for r, fase in zip(ativas.to_dict("records"), fases):
            onde, status = FASES.get(fase, ("—", "neutro"))
            coluna = svc.ETAPAS[fase]["coluna"]
            ha = svc.formatar_duracao(_desde(r[coluna]))
            prazo = ""
            if r.get("apresentou_no_prazo") is not None and not pd.isna(r.get("apresentou_no_prazo")):
                prazo = tema.selo("bom", "Apresentou no prazo") if int(r["apresentou_no_prazo"]) else \
                    tema.selo("critico", f"Atraso {svc.formatar_duracao((r.get('atraso_min') or 0) / 60)}")
            elif r.get("agendamento") and not r.get("ts_apresentado"):
                ag = tempo.parse_dt(r["agendamento"])
                if ag and tempo.agora() > ag:
                    prazo = tema.selo("critico", "Agendamento vencido sem apresentação")
            cards.append(
                f'<div class="eco-kpi" style="--cor:{tema.STATUS[status][0]}">'
                f'<div class="rot">🚛 {tema._e(r["placa"])} · {tema._e(r["motorista"])}</div>'
                f'<div class="val" style="font-size:1.05rem">{tema._e(onde)}</div>'
                f'<div class="det">Pedido {tema._e(r["numero_pedido"])} · {tema._e(r.get("destino") or "")}<br>'
                f'{tema._e(svc.ETAPAS[fase]["nome"])} há {ha}'
                f'{" · agend. " + tema._e(_fmt(r["agendamento"])) if r.get("agendamento") else ""}</div>{prazo}</div>')
        st.markdown(f'<div class="eco-kpis">{"".join(cards)}</div>', unsafe_allow_html=True)

    tema.secao("Placas paradas na revenda", "Chegaram e ainda não iniciaram nova viagem (TMA em aberto).")
    if parados.empty:
        st.info("Nenhuma placa parada na revenda.")
    else:
        tab = parados.assign(chegada=parados["chegada"].dt.strftime(_FMT),
                             parada=parados["parada_h"].map(svc.formatar_duracao))
        ui.tabela(tab[["placa", "motorista", "chegada", "parada"]], column_config={
            "placa": "Placa", "motorista": "Último motorista", "chegada": "Chegou em", "parada": "Parada há"})


# --- Viagens & NFs -------------------------------------------------------------
def _fotos(vid: int) -> None:
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
                                   mime=f["tipo"] or "application/octet-stream", key=f"car_dl_{f['id']}")


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
    if v.get("observacao"):
        st.caption(f"📝 {v['observacao']}")
    _fotos(vid)
    if v["status"] == repo.EM_VIAGEM:
        with st.popover("🚫 Cancelar esta viagem"):
            motivo = st.text_input("Motivo", key=f"car_cancel_mot_{vid}")
            if st.button("Confirmar cancelamento", key=f"car_cancel_{vid}"):
                ui.acao(svc.cancelar_viagem, vid, motivo, usuario["nome"], sucesso="Viagem cancelada.")


# --- Acessos dos motoristas ------------------------------------------------------
def _acessos(operacao_id: int) -> None:
    df = repo.acessos_df(operacao_id)
    if df.empty:
        st.info("Cadastre os motoristas em **⚙️ Cadastros › 👤 Motoristas** e volte aqui para criar o acesso.")
        return
    nova = st.session_state.pop("car_senha_nova", None)
    if nova:
        st.success(f"Acesso de **{nova['nome']}** pronto. Passe ao motorista (a senha aparece só agora):")
        st.code(f"Login: {nova['login']}\nSenha provisória: {nova['senha']}", language=None)
        st.caption("No primeiro acesso ele cria a própria senha. O endereço é o mesmo do sistema.")
    ui.tabela(df.drop(columns=["usuario_id"]).assign(ultimo_acesso=df["ultimo_acesso"].fillna("")), column_config={
        "id": None, "nome": "Motorista", "cnh": "CNH", "telefone": "Telefone", "acesso": "Login",
        "situacao": "Situação", "ultimo_acesso": "Último acesso"})

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
        ativo = sel["situacao"] == "Ativo"
        if b2.button("🔒 Bloquear" if ativo else "🔓 Desbloquear", key="car_ac_bloq"):
            ui.acao(svc.bloquear_acesso, mid2, not ativo, sucesso="Acesso bloqueado." if ativo else "Acesso liberado.")


# --- Revenda (GPS) --------------------------------------------------------------------
def _revenda(operacao_id: int) -> None:
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


def render(usuario: dict, operacao_id: int) -> None:
    abas = st.tabs(["📡 Ao vivo", "🗂️ Viagens & NFs", "🔑 Acessos dos motoristas", "📍 Revenda (GPS)"])
    with abas[0]:
        _ao_vivo(operacao_id)
    with abas[1]:
        _viagens(usuario, operacao_id)
    with abas[2]:
        _acessos(operacao_id)
    with abas[3]:
        _revenda(operacao_id)
