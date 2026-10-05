"""App Carreteiro — tela do motorista (celular).

O motorista entra com o próprio acesso e vê só esta tela: abre a viagem
(pedido, agendamento, destino e placa), aperta o botão verde e vai marcando
cada passo. Cada clique grava data, hora e — se o celular permitir — o GPS.
"""
import datetime as dt

import streamlit as st

from core import session, tema, tempo, ui
from modules.componentes.geolocalizacao import localizacao, ponto
from repositories import carreteiro_repo as repo
from services import carreteiro_service as svc
from services import usuarios_service
from services.erros import RegraNegocioError

VERDE, AZUL, LARANJA = "#0ca30c", "#2a78d6", "#ec835a"

_CSS = f"""
<style>
.block-container {{ max-width: 640px; padding-top: 1.2rem; padding-left: 1rem; padding-right: 1rem; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
.car-topo {{ background: linear-gradient(135deg, #0B1F3A 0%, #1f4a8a 100%); color: #fff; border-radius: 18px;
    padding: 1rem 1.2rem; margin-bottom: .8rem; }}
.car-topo b {{ font-size: 1.25rem; display: block; }}
.car-topo span {{ opacity: .8; font-size: .88rem; }}
.car-viagem {{ background: #fff; border: 1px solid #e1e0d9; border-radius: 16px; padding: .9rem 1.1rem; margin: .4rem 0 .8rem; }}
.car-viagem .lin {{ display: flex; justify-content: space-between; gap: .6rem; padding: .2rem 0; font-size: .95rem; }}
.car-viagem .lin span {{ color: #898781; }}
.car-viagem .lin b {{ text-align: right; }}
.car-passos {{ margin: .4rem 0 1rem; }}
.car-passo {{ display: flex; align-items: center; gap: .75rem; padding: .55rem .2rem; border-left: 3px solid #e1e0d9;
    margin-left: .9rem; padding-left: 1rem; position: relative; }}
.car-passo .ic {{ position: absolute; left: -1.05rem; width: 1.8rem; height: 1.8rem; border-radius: 50%;
    display: grid; place-items: center; font-size: .95rem; background: #f0efec; border: 2px solid #e1e0d9; }}
.car-passo.feito {{ border-left-color: {VERDE}; }}
.car-passo.feito .ic {{ background: #e8f6e8; border-color: {VERDE}; }}
.car-passo.atual .ic {{ background: #eaf2fc; border-color: {AZUL}; box-shadow: 0 0 0 4px rgba(42,120,214,.15); }}
.car-passo.atual {{ font-weight: 700; }}
.car-passo .nm {{ flex: 1; }}
.car-passo .hr {{ color: #52514e; font-size: .88rem; font-variant-numeric: tabular-nums; }}
.car-passo.pend .nm {{ color: #898781; }}
.car-nf {{ background: #f7f7f5; border-radius: 12px; padding: .55rem .8rem; margin: .3rem 0; font-size: .92rem; }}
.st-key-car_verde button {{ background: {VERDE} !important; border-color: {VERDE} !important; min-height: 3.6rem;
    border-radius: 14px !important; box-shadow: 0 8px 18px -8px rgba(12,163,12,.7); }}
.st-key-car_verde button p {{ color: #fff !important; font-size: 1.2rem !important; font-weight: 800; }}
.st-key-car_etapa button {{ background: {AZUL} !important; border-color: {AZUL} !important; min-height: 3.6rem;
    border-radius: 14px !important; }}
.st-key-car_etapa button p {{ color: #fff !important; font-size: 1.15rem !important; font-weight: 800; }}
.st-key-car_fim button {{ background: {VERDE} !important; border-color: {VERDE} !important; min-height: 3.6rem;
    border-radius: 14px !important; }}
.st-key-car_fim button p {{ color: #fff !important; font-size: 1.15rem !important; font-weight: 800; }}
.st-key-car_form input {{ height: 2.9rem; font-size: 1rem; }}
</style>
"""


def _fmt(ts) -> str:
    d = tempo.parse_dt(ts)
    return d.strftime("%d/%m %H:%M") if d else "—"


def _topo(usuario: dict, mot: dict) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1.2])
    with c1:
        st.markdown(f'<div class="car-topo"><b>🚛 Olá, {tema._e(mot["nome"].split()[0])}!</b>'
                    f'<span>App Carreteiro · {tema._e(tempo.agora().strftime("%d/%m/%Y %H:%M"))}</span></div>',
                    unsafe_allow_html=True)
    with c2:
        with st.popover("👤 Conta"):
            with st.form("car_senha", clear_on_submit=True):
                atual = st.text_input("Senha atual", type="password")
                nova = st.text_input("Nova senha", type="password")
                conf = st.text_input("Confirme", type="password")
                if st.form_submit_button("Trocar senha"):
                    ui.acao(usuarios_service.trocar_propria_senha, usuario["id"], atual, nova, conf,
                            sucesso="Senha alterada!")
            if st.button("🚪 Sair", key="car_sair", **ui.LARGURA):
                session.sair()
                st.rerun()


def _resumo(v: dict) -> None:
    linhas = [("Pedido", v["numero_pedido"]), ("Destino", v.get("destino") or "—"), ("Placa do cavalo", v["placa"]),
              ("Agendamento", _fmt(v.get("agendamento")) if v.get("agendamento") else "sem agendamento")]
    st.markdown('<div class="car-viagem">' + "".join(
        f'<div class="lin"><span>{tema._e(a)}</span><b>{tema._e(b)}</b></div>' for a, b in linhas) + "</div>",
        unsafe_allow_html=True)


def _linha_do_tempo(v: dict) -> None:
    prox = svc.proxima_etapa(v)
    partes = []
    for chave in svc.ORDEM:
        e = svc.ETAPAS[chave]
        ts = v.get(e["coluna"])
        cls = "feito" if ts else ("atual" if chave == prox else "pend")
        extra = ""
        if chave == "apresentado" and ts and v.get("apresentou_no_prazo") is not None:
            extra = " · " + ("<span style='color:#0ca30c'>no prazo</span>" if v["apresentou_no_prazo"]
                             else "<span style='color:#d03b3b'>fora do prazo</span>")
        partes.append(f'<div class="car-passo {cls}"><div class="ic">{e["icone"] if ts or cls == "atual" else "•"}</div>'
                      f'<div class="nm">{tema._e(e["nome"])}{extra}</div>'
                      f'<div class="hr">{_fmt(ts) if ts else ""}</div></div>')
    st.markdown(f'<div class="car-passos">{"".join(partes)}</div>', unsafe_allow_html=True)


def _gps(valor: dict | None) -> dict | None:
    return ponto(valor)


# --- Nova viagem -------------------------------------------------------------
def _nova_viagem(usuario: dict, mot: dict, geo: dict | None) -> None:
    destinos = repo.destinos()
    placas = repo.placas(mot["operacao_id"])
    tema.secao("Nova viagem", "Preencha os dados e toque no botão verde para iniciar.")
    if not destinos or not placas:
        st.warning("Ainda faltam cadastros: peça à Puxada para cadastrar "
                   + " e ".join(x for x, falta in (("os destinos (fábricas)", not destinos),
                                                   ("as placas", not placas)) if falta) + ".")
        return
    with st.container(key="car_form"):
        with st.form("car_nova", clear_on_submit=False):
            pedido = st.text_input("Número do pedido *", placeholder="Ex.: 4500123456")
            c1, c2 = st.columns(2)
            data_ag = c1.date_input("Data do agendamento", value=None, format="DD/MM/YYYY")
            hora_ag = c2.time_input("Hora do agendamento", value=None, step=dt.timedelta(minutes=15))
            destino = st.selectbox("Destino *", [None] + [d["id"] for d in destinos],
                                   format_func=lambda i: "Selecione..." if i is None else next(
                                       f'{d["nome"]}' + (f' — {d["cidade"]}/{d["uf"]}' if d.get("cidade") else "")
                                       for d in destinos if d["id"] == i))
            placa = st.selectbox("Placa do cavalo *", [None] + [p["placa"] for p in placas],
                                 format_func=lambda p: "Selecione..." if p is None else p)
            with st.container(key="car_verde"):
                enviar = st.form_submit_button("🟢  INICIAR VIAGEM", type="primary", **ui.LARGURA)
    if enviar:
        try:
            svc.iniciar_viagem(usuario, pedido, data_ag, hora_ag, destino, placa, _gps(geo))
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar(f"Viagem iniciada às {tempo.agora().strftime('%H:%M')}. Boa viagem! 🚛")
            st.rerun()


# --- Notas fiscais (etapa "Pedido carregado") --------------------------------
def _notas(usuario: dict, v: dict, obrigatorio: bool) -> None:
    notas = repo.notas(v["id"])
    tema.secao("📄 Notas fiscais", "Digite o número de cada NF e tire foto(s) dela. Pode adicionar várias notas.")
    for n in notas:
        c1, c2, c3 = st.columns([3, 1.3, .8])
        c1.markdown(f'<div class="car-nf">🧾 <b>NF {tema._e(n["numero_nf"])}</b> · {n["fotos"]} foto(s)</div>',
                    unsafe_allow_html=True)
        with c2.popover("➕ fotos"):
            vk = st.session_state.get(f"car_fv_{n['id']}", 0)
            arqs = st.file_uploader("Fotos", type=["jpg", "jpeg", "png", "webp", "heic", "pdf"],
                                    accept_multiple_files=True, key=f"car_fotos_{n['id']}_{vk}")
            if st.button("Enviar fotos", key=f"car_envf_{n['id']}"):
                try:
                    qtd = svc.adicionar_fotos(usuario, v["id"], n["id"], arqs)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    st.session_state[f"car_fv_{n['id']}"] = vk + 1
                    ui.avisar(f"{qtd} foto(s) adicionada(s) à NF {n['numero_nf']}.")
                    st.rerun()
        if c3.button("🗑️", key=f"car_rm_{n['id']}", help="Remover esta NF"):
            ui.acao(svc.remover_nota, usuario, v["id"], n["id"], sucesso=f"NF {n['numero_nf']} removida.")

    versao = st.session_state.get("car_nf_v", 0)
    with st.expander("➕ Adicionar nota fiscal", expanded=obrigatorio and not notas):
        numero = st.text_input("Número da NF *", key=f"car_nf_num_{versao}", placeholder="Ex.: 123456")
        arqs = st.file_uploader("📷 Fotos da nota * (tire na hora ou escolha da galeria)",
                                type=["jpg", "jpeg", "png", "webp", "heic", "pdf"], accept_multiple_files=True,
                                key=f"car_nf_fotos_{versao}")
        camera = None
        if st.toggle("Usar a câmera aqui na tela", key=f"car_cam_t_{versao}"):
            camera = st.camera_input("Foto da nota", key=f"car_cam_{versao}")
        if st.button("💾 Salvar NF", key=f"car_nf_salvar_{versao}", type="primary", **ui.LARGURA):
            try:
                svc.adicionar_nota(usuario, v["id"], numero, list(arqs or []) + ([camera] if camera else []))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["car_nf_v"] = versao + 1
                ui.avisar(f"NF {numero.strip()} salva. Tem outra nota? Adicione abaixo.")
                st.rerun()


# --- Viagem em andamento ------------------------------------------------------
def _viagem(usuario: dict, v: dict, geo: dict | None) -> None:
    _resumo(v)
    aviso = svc.mensagem_apresentacao(v)
    if aviso:
        getattr(st, aviso[0])(aviso[1])
    _linha_do_tempo(v)

    prox = svc.proxima_etapa(v)
    if prox is None:
        return
    e = svc.ETAPAS[prox]
    if prox == "carregado" or v.get("ts_carregado"):
        _notas(usuario, v, obrigatorio=prox == "carregado")

    rotulo = f"{e['icone']}  {e['botao'].upper()}"
    with st.container(key="car_fim" if prox == "fim" else "car_etapa"):
        clicou = st.button(rotulo, key=f"car_btn_{prox}", type="primary", **ui.LARGURA)
    if prox == "apresentado":
        st.caption("Toque assim que se apresentar na cervejaria. O sistema compara com o horário do agendamento.")
    if clicou:
        try:
            nova = svc.registrar_etapa(usuario, v["id"], prox, _gps(geo))
        except RegraNegocioError as err:
            st.error(str(err))
        else:
            if prox == "apresentado":
                tipo, msg = svc.mensagem_apresentacao(nova) or ("success", "Apresentação registrada.")
                ui.avisar(msg, "error" if tipo == "error" else "success")
            elif prox == "fim":
                ui.avisar(f"Viagem finalizada! TMV: {svc.formatar_duracao(_horas(nova['ts_inicio'], nova['ts_fim']))}.")
            else:
                ui.avisar(f"{e['nome']} registrado às {tempo.agora().strftime('%H:%M')}.")
            st.rerun()

    ultima = svc.ultima_etapa(v)
    if ultima:
        with st.popover(f"↩️ Desfazer “{svc.ETAPAS[ultima]['nome']}”"):
            st.caption("Use só se tocou por engano. Depois de alguns minutos, peça a correção para a Puxada.")
            if st.button("Confirmar desfazer", key="car_desfazer"):
                ui.acao(svc.desfazer_ultima, usuario, v["id"], sucesso="Etapa desfeita.")


def _horas(a, b) -> float | None:
    da, db = tempo.parse_dt(a), tempo.parse_dt(b)
    return (db - da).total_seconds() / 3600 if da and db else None


def _historico(mot: dict) -> None:
    df = repo.viagens_df(mot["operacao_id"], motorista_id=mot["id"])
    df = df[df["status"] == repo.FINALIZADA].head(10) if not df.empty else df
    if df.empty:
        return
    with st.expander(f"🕘 Minhas últimas viagens ({len(df)})"):
        for r in df.itertuples():
            st.markdown(f"**{_fmt(r.ts_inicio)}** · Pedido {r.numero_pedido} · {r.placa} · {r.destino or ''} · "
                        f"TMV {svc.formatar_duracao(_horas(r.ts_inicio, r.ts_fim))}")


def render(usuario: dict) -> None:
    mot = repo.motorista_do_usuario(usuario["id"])
    if not mot:
        st.markdown(_CSS, unsafe_allow_html=True)
        st.warning("Seu acesso ainda não está ligado a um motorista. Fale com a equipe da Puxada.")
        if st.button("🚪 Sair"):
            session.sair()
            st.rerun()
        return
    _topo(usuario, mot)
    ui.mostrar_avisos()
    geo = localizacao(key="geo_motorista")
    if geo and geo.get("erro"):
        st.caption("Sem GPS o app funciona normalmente — mas a Puxada não consegue confirmar a chegada na revenda.")

    v = repo.viagem_ativa_motorista(mot["id"])
    if v:
        _viagem(usuario, v, geo)
    else:
        _nova_viagem(usuario, mot, geo)
    _historico(mot)
