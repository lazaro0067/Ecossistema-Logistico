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
.car-jans {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap:.45rem; margin:.3rem 0 .7rem; }}
.car-jan {{ border-radius:12px; padding:.5rem .6rem; border:1.5px solid; display:flex; flex-direction:column; gap:.1rem; }}
.car-jan b {{ font-size:1rem; }} .car-jan span {{ font-size:.82rem; font-weight:700; }} .car-jan i {{ font-size:.72rem; font-style:normal; opacity:.8; }}
.car-jan.ok {{ background:#ecfdf3; border-color:#34c27a; color:#0f5132; }}
.car-jan.cheia {{ background:#fdecec; border-color:#e5484d; color:#8a1c1f; }}
.car-jan.fim {{ background:#f2f2f0; border-color:#d0cfc8; color:#77766f; }}
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


_CSS_LOGIN = f"""
<style>
.block-container {{ max-width: 460px; padding-top: 6vh; }}
.car-login-topo {{ background: linear-gradient(150deg, #0B1F3A 0%, #16305A 55%, #1f4a8a 100%); color:#fff;
    border-radius: 22px; padding: 1.6rem 1.4rem 1.4rem; margin-bottom: 1rem; text-align:center;
    box-shadow: 0 18px 40px -18px rgba(11,31,58,.5); }}
.car-login-topo .ic {{ font-size: 2.6rem; line-height: 1; }}
.car-login-topo b {{ display:block; font-size: 1.5rem; margin-top:.4rem; letter-spacing:-.01em; }}
.car-login-topo span {{ opacity:.78; font-size:.9rem; }}
.st-key-car_login [data-testid="stForm"] {{ background:#fff; border-radius:18px; border:1px solid #e1e0d9;
    padding: 1.2rem 1.1rem; }}
.st-key-car_login input {{ height: 3rem; font-size: 1.05rem; }}
.st-key-car_login [data-testid="stFormSubmitButton"] button {{ background:{VERDE} !important;
    border-color:{VERDE} !important; min-height: 3.2rem; border-radius: 14px !important; }}
.st-key-car_login [data-testid="stFormSubmitButton"] button p {{ color:#fff !important; font-size:1.1rem !important;
    font-weight:800; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
</style>
"""


def _topo_login(sub: str) -> None:
    st.markdown(_CSS_LOGIN, unsafe_allow_html=True)
    st.markdown(f'<div class="car-login-topo"><div class="ic">🚛</div><b>App Carreteiro</b>'
                f'<span>{tema._e(sub)}</span></div>', unsafe_allow_html=True)


def tela_login() -> None:
    """Login do link exclusivo dos motoristas (CPF, celular ou e-mail)."""
    from core.auth import autenticar

    _topo_login("Grupo Lima · registre cada passo da sua viagem")
    with st.container(key="car_login"):
        with st.form("car_login_form"):
            acesso = st.text_input("CPF, celular ou e-mail", placeholder="Só os números do CPF ou celular",
                                   autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            lembrar = st.checkbox("Manter conectado neste celular", value=True,
                                  help="Ao abrir o app de novo, você continua de onde parou sem digitar a senha.")
            if st.form_submit_button("Entrar", type="primary", **ui.LARGURA):
                usuario = autenticar(acesso, senha)
                if usuario:
                    session.logar(usuario)
                    if lembrar:
                        from core.auth import gerar_token

                        token = gerar_token(usuario["id"])
                        if token:
                            st.query_params["k"] = token
                    st.rerun()
                st.error("Acesso ou senha inválidos.")
    st.caption("Esqueceu a senha ou ainda não tem acesso? Fale com a equipe da Puxada da sua unidade.")


def _sair() -> None:
    session.sair()
    if "k" in st.query_params:
        del st.query_params["k"]
    st.rerun()


def tela_criar_senha(usuario: dict) -> None:
    _topo_login(f"Olá, {usuario['nome'].split()[0]}! Crie a sua senha para começar.")
    with st.container(key="car_login"):
        with st.form("car_criar_senha"):
            nova = st.text_input("Nova senha", type="password", autocomplete="new-password")
            conf = st.text_input("Confirme a nova senha", type="password", autocomplete="new-password")
            if st.form_submit_button("Salvar e entrar", type="primary", **ui.LARGURA):
                try:
                    usuarios_service.trocar_propria_senha(usuario["id"], None, nova, conf)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    usuario["trocar_senha"] = 0
                    ui.avisar("Senha criada! Boa viagem. 🚛")
                    st.rerun()
    if st.button("Sair", key="car_sair_senha"):
        _sair()


def tela_nao_motorista(usuario: dict) -> None:
    from core.segredos import segredo

    _topo_login("Link exclusivo dos motoristas")
    st.warning(f"{usuario['nome'].split()[0]}, este endereço é só para motoristas. "
               "A gestão da puxada fica no link principal do sistema.")
    url = (segredo("APP_URL") or "").rstrip("/")
    if url:
        st.link_button("Abrir o sistema principal", url)
    if st.button("Sair", key="car_sair_outro"):
        _sair()


def link_do_app() -> str:
    """Endereço do App Carreteiro para mandar aos motoristas.
    Ordem: Secret CARRETEIRO_URL (app separado) → Secret APP_URL → endereço aberto agora → endereço padrão."""
    from config.settings import APP_URL_PADRAO
    from core.segredos import segredo

    proprio = (segredo("CARRETEIRO_URL") or "").strip()
    if proprio:
        return proprio
    url = (segredo("APP_URL") or "").strip().rstrip("/")
    if not url:
        try:
            host = st.context.headers.get("host") or ""
        except Exception:
            host = ""
        url = f"https://{host}" if host and "localhost" not in host and "127.0.0.1" not in host else APP_URL_PADRAO
    return f"{url}/?app=motorista"


def link_whatsapp(texto: str, telefone: str | None = None) -> str:
    """Link do WhatsApp com a mensagem pronta (para o número do motorista, se houver)."""
    from urllib.parse import quote

    numero = "".join(c for c in str(telefone or "") if c.isdigit())
    if len(numero) in (10, 11):
        numero = "55" + numero
    destino = numero if len(numero) in (12, 13) else ""
    return f"https://wa.me/{destino}?text={quote(texto)}"


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
        if st.button("🚪 Sair", key="car_sair", **ui.LARGURA):
            _sair()


def _resumo(v: dict) -> None:
    linhas = [("Pedido", v["numero_pedido"]), ("Destino", v.get("destino") or "—"), ("Placa do cavalo", v["placa"]),
              ("Agendamento", _fmt(v.get("agendamento")) if v.get("agendamento") else "sem agendamento")]
    marcado = repo.pedido_marcado(v["operacao_id"], v["numero_pedido"])
    if marcado:
        linhas.append(("Pedido marcado", f"{int(marcado['itens'])} itens · {ui.numero(marcado['cx'])} cx · "
                                         f"{ui.numero(marcado['hl'], 1)} HL"))
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
        pedido = st.text_input("Número do pedido *", placeholder="Ex.: 4500123456", key="car_nova_pedido")
        plan = svc.pedido_planejado(mot["operacao_id"], pedido) if (pedido or "").strip() else None
        data_ag = hora_ag = destino = placa = None
        if plan:
            ag = (f"{dt.date.fromisoformat(str(plan['data'])[:10]):%d/%m} às {plan['hora_agendamento']}"
                  if plan.get("hora_agendamento") else "sem horário")
            outro = plan.get("motorista_id") and int(plan["motorista_id"]) != int(mot["id"])
            st.markdown(
                f'<div class="car-viagem"><div class="lin"><span>✅ Pedido da Puxada</span><b>{tema._e(plan["numero_pedido"])}'
                f'</b></div><div class="lin"><span>Placa</span><b>{tema._e(plan["placa"])}</b></div>'
                f'<div class="lin"><span>Fábrica</span><b>{tema._e(plan.get("fabrica") or "—")}</b></div>'
                f'<div class="lin"><span>Agendamento</span><b>{tema._e(ag)}</b></div>'
                f'<div class="lin"><span>Motorista escalado</span><b>{tema._e(plan.get("motorista") or "—")}</b></div>'
                f'<div class="lin"><span>Carga</span><b>{tema._e(plan["tipo"])}</b></div></div>',
                unsafe_allow_html=True)
            if outro:
                st.warning(f"Este pedido está escalado para **{plan.get('motorista')}**. Se você assumiu a viagem, "
                           "pode iniciar — a Puxada verá o seu nome.")
            st.caption("Tudo já vem do pedido lançado pela Puxada — é só iniciar.")
        else:
            if (pedido or "").strip():
                st.info("Pedido não encontrado nos pedidos da Puxada — preencha os dados abaixo.")
            c1, c2 = st.columns(2)
            data_ag = c1.date_input("Data do agendamento", value=None, format="DD/MM/YYYY", key="car_nova_data")
            hora_ag = c2.time_input("Hora do agendamento", value=None, step=dt.timedelta(minutes=15),
                                    key="car_nova_hora")
            destino = st.selectbox("Destino *", [None] + [d["id"] for d in destinos], key="car_nova_dest",
                                   format_func=lambda i: "Selecione..." if i is None else next(
                                       f'{d["nome"]}' + (f' — {d["cidade"]}/{d["uf"]}' if d.get("cidade") else "")
                                       for d in destinos if d["id"] == i))
            placa = st.selectbox("Placa do cavalo *", [None] + [p["placa"] for p in placas], key="car_nova_placa",
                                 format_func=lambda p: "Selecione..." if p is None else p)
        with st.container(key="car_verde"):
            enviar = st.button("🟢  INICIAR VIAGEM", type="primary", key="car_nova_ok", **ui.LARGURA)
    if enviar:
        try:
            vid = svc.iniciar_viagem(usuario, pedido, data_ag, hora_ag, destino, placa, _gps(geo))
            st.session_state[f"car_aberta_{vid}"] = True  # já abre a viagem para registrar as etapas
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            for k in ("car_nova_pedido", "car_nova_data", "car_nova_hora", "car_nova_dest", "car_nova_placa"):
                st.session_state.pop(k, None)
            ui.avisar(f"Viagem iniciada às {tempo.agora().strftime('%H:%M')}. Boa viagem! 🚛")
            st.rerun()


# --- Notas fiscais (etapa "Pedido carregado") --------------------------------
def _notas(usuario: dict, v: dict, obrigatorio: bool) -> None:
    notas = repo.notas(v["id"])
    tema.secao("📄 Notas fiscais", "Digite o número de cada NF e tire foto(s) dela. Pode adicionar várias notas — "
               "elas já vão para a Puxada vinculadas ao seu pedido.")
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
    _etapa_atual(usuario, v, geo, prox)
    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    _cancelar(usuario, v)


def _etapa_atual(usuario: dict, v: dict, geo: dict | None, prox: str) -> None:
    e = svc.ETAPAS[prox]
    if prox == "carregado" or v.get("ts_carregado"):
        _notas(usuario, v, obrigatorio=prox == "carregado")
    if v.get("ts_agendado") and not v.get("ts_chegada_revenda"):
        _agenda_resumo(usuario, v, geo)
    if prox == "agendado":
        _agendar(usuario, v, geo)
        _desfazer(usuario, v)
        return

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

    _desfazer(usuario, v)


def _desfazer(usuario: dict, v: dict) -> None:
    ultima = svc.ultima_etapa(v)
    if ultima:
        with st.popover(f"↩️ Desfazer “{svc.ETAPAS[ultima]['nome']}”"):
            st.caption("Use só se tocou por engano. Depois de alguns minutos, peça a correção para a Puxada.")
            if st.button("Confirmar desfazer", key="car_desfazer"):
                ui.acao(svc.desfazer_ultima, usuario, v["id"], sucesso="Etapa desfeita.")


# --- Agendamento da descarga (entre carregar e sair da cervejaria) ------------------
def _chips_janelas(js: list[dict]) -> None:
    """Quadro das janelas do dia: verde = tem vaga, vermelho = lotada, cinza = já passou."""
    itens = []
    for j in js:
        if j["passou"]:
            cls, txt = "fim", "encerrada"
        elif j["livres"] <= 0:
            cls, txt = "cheia", "lotada"
        else:
            cls, txt = "ok", f"{j['livres']} de {j['slots']} vaga{'s' if int(j['slots']) > 1 else ''}"
        prod = f"<i>{tema._e(j['produto'])}</i>" if j.get("produto") else ""
        itens.append(f'<div class="car-jan {cls}"><b>{tema._e(j["rotulo"])}</b><span>{txt}</span>{prod}</div>')
    st.markdown(f'<div class="car-jans">{"".join(itens)}</div>', unsafe_allow_html=True)


def _form_agenda(usuario: dict, v: dict, chave: str, botao: str, sucesso: str, geo) -> None:
    """Dia + produto + janela (com as vagas de agora). Sem janelas cadastradas: hora livre."""
    from config.settings import TIPOS_DESCARGA_APP
    from services import janelas_service

    atual_data = dt.date.fromisoformat(v["desc_data"]) if v.get("desc_data") else tempo.hoje()
    atual_data = max(atual_data, tempo.hoje())
    c1, c2 = st.columns(2)
    data = c1.date_input("📅 Dia da chegada na revenda *", value=atual_data, format="DD/MM/YYYY",
                         min_value=tempo.hoje(), max_value=tempo.hoje() + dt.timedelta(days=15), key=f"{chave}_d")
    produto = c2.radio("📦 Produto *", TIPOS_DESCARGA_APP, horizontal=True, key=f"{chave}_p",
                       index=TIPOS_DESCARGA_APP.index(v["desc_tipo"]) if v.get("desc_tipo") in TIPOS_DESCARGA_APP
                       else None)
    hora = janela_id = None
    pode = True
    if janelas_service.tem_janelas(v["operacao_id"]):
        if not produto:
            st.caption("Escolha o produto para ver as janelas com vaga.")
            pode = False
        else:
            js = janelas_service.janelas_do_dia(v["operacao_id"], data, produto, ignorar_viagem=v["id"])
            if not js:
                st.warning(f"A revenda não recebe {produto.lower()} em {data:%d/%m} ({janelas_service.DIAS[data.weekday()]}). "
                           "Escolha outro dia.")
                pode = False
            else:
                st.markdown(f"**🕒 Janelas de {data:%d/%m}** · vagas de agora ({tempo.agora():%H:%M})")
                _chips_janelas(js)
                livres = [j for j in js if j["livres"] > 0 and not j["passou"]]
                if not livres:
                    st.error("Todas as janelas deste dia estão lotadas. Escolha outro dia.")
                    pode = False
                else:
                    ids = [j["id"] for j in livres]
                    nomes = {j["id"]: f"{j['rotulo']}  ·  {j['livres']} vaga(s)" for j in livres}
                    atual = v.get("desc_janela_id") if v.get("desc_data") == data.isoformat() else None
                    janela_id = st.radio("Escolha a janela de chegada *", ids, format_func=nomes.get,
                                         index=ids.index(atual) if atual in ids else None,
                                         key=f"{chave}_j_{data}_{produto}")
            if st.button("🔄 Atualizar vagas", key=f"{chave}_upd"):
                st.rerun()
    else:
        atual_hora = dt.datetime.strptime(v["desc_hora"], "%H:%M").time() if v.get("desc_hora") else None
        hora = st.time_input("🕒 Hora prevista *", value=atual_hora, step=dt.timedelta(minutes=30), key=f"{chave}_h")
    with st.container(key="car_etapa" if botao.startswith("🗓️") else f"{chave}_salvar"):
        ok = st.button(botao, key=f"{chave}_ok", type="primary", disabled=not pode, **ui.LARGURA)
    if ok:
        try:
            nova = svc.agendar_descarga(usuario, v["id"], data, hora, produto, _gps(geo), janela_id=janela_id)
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar(sucesso.format(data=f"{data:%d/%m}", hora=nova.get("desc_hora") or ""))
            st.rerun()


def _agendar(usuario: dict, v: dict, geo) -> None:
    tema.secao("🗓️ Agendar a descarga na revenda",
               "Escolha o dia, o produto e a janela com vaga. O armazém recebe a tarefa na hora.")
    with st.container(key="car_form"):
        _form_agenda(usuario, v, f"car_ag_{v['id']}", "🗓️  AGENDAR DESCARGA",
                     "Descarga agendada para {data} às {hora}. O armazém já foi avisado.", geo)


def _agenda_resumo(usuario: dict, v: dict, geo) -> None:
    from services import janelas_service
    from repositories import logistica_repo

    d = dt.date.fromisoformat(v["desc_data"])
    jan = janelas_service.janela_de_agendamento(logistica_repo.janelas(v["operacao_id"], False), v["desc_data"],
                                                v.get("desc_hora"), v.get("desc_janela_id"))
    quando = f"janela {jan}" if jan else f"às {v.get('desc_hora') or '--:--'}"
    st.markdown(f'<div class="car-nf">🗓️ <b>Descarga agendada:</b> {d:%d/%m/%Y} · {quando} · '
                f'{tema._e(v.get("desc_tipo") or "")}</div>', unsafe_allow_html=True)
    with st.expander("✏️ Editar agendamento da descarga"):
        _form_agenda(usuario, v, f"car_aged_{v['id']}", "💾 Salvar alteração",
                     "Agendamento alterado para {data} às {hora}. O armazém foi avisado.", geo)


def _cancelar(usuario: dict, v: dict) -> None:
    """Cancelar o pedido em qualquer etapa — pede a justificativa."""
    with st.popover("❌ Cancelar este pedido", **ui.LARGURA):
        st.markdown(f"**Cancelar o pedido {tema._e(v['numero_pedido'])}?**")
        st.caption("A Puxada e o armazém recebem o aviso com a sua justificativa, e a vaga da descarga é liberada.")
        just = st.text_area("Justificativa *", key=f"car_cancel_txt_{v['id']}", max_chars=400,
                            placeholder="Ex.: pedido cancelado pela cervejaria, carreta quebrou, ...")
        if st.button("Confirmar cancelamento", key=f"car_cancel_ok_{v['id']}", type="primary", **ui.LARGURA):
            try:
                svc.cancelar_pelo_motorista(usuario, v["id"], just)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state.pop(f"car_aberta_{v['id']}", None)
                ui.avisar(f"Pedido {v['numero_pedido']} cancelado. A Puxada foi avisada.", "info")
                st.rerun()


def _horas(a, b) -> float | None:
    da, db = tempo.parse_dt(a), tempo.parse_dt(b)
    return (db - da).total_seconds() / 3600 if da and db else None


AREAS = ["🚛 Viagem", "💵 Minhas variáveis", "🧾 Minhas viagens", "👤 Meus dados"]


def _continuar(v: dict) -> bool:
    """Ao abrir o app com viagem em andamento: mostra o pedido para tocar e voltar à etapa em que parou."""
    if st.session_state.get(f"car_aberta_{v['id']}"):
        return True
    prox = svc.proxima_etapa(v)
    ult = svc.ultima_etapa(v)
    etapa = svc.ETAPAS[prox]["nome"] if prox else "concluída"
    st.markdown(
        f'<div class="car-viagem"><div class="lin"><span>Viagem em andamento</span><b>Pedido {tema._e(v["numero_pedido"])}'
        f'</b></div><div class="lin"><span>Placa · destino</span><b>{tema._e(v["placa"])} · {tema._e(v.get("destino") or "")}'
        f'</b></div><div class="lin"><span>Última etapa</span><b>{tema._e(svc.ETAPAS[ult]["nome"]) if ult else "—"} '
        f'{_fmt(v.get(svc.ETAPAS[ult]["coluna"])) if ult else ""}</b></div><div class="lin"><span>Próxima etapa</span>'
        f'<b>{tema._e(etapa)}</b></div></div>', unsafe_allow_html=True)
    with st.container(key="car_verde"):
        if st.button(f"▶️  CONTINUAR · PEDIDO {v['numero_pedido']}", key=f"car_cont_{v['id']}", type="primary",
                     **ui.LARGURA):
            st.session_state[f"car_aberta_{v['id']}"] = True
            st.rerun()
    return False


def _area_viagem(usuario: dict, mot: dict) -> None:
    geo = localizacao(key="geo_motorista")
    if geo and geo.get("erro"):
        st.caption("Sem GPS o app funciona normalmente — mas a Puxada não consegue confirmar a chegada na revenda.")
    v = repo.viagem_ativa_motorista(mot["id"])
    if v:
        if _continuar(v):
            _viagem(usuario, v, geo)
    else:
        if _em_servico(mot):
            return
        _nova_viagem(usuario, mot, geo)


def _em_servico(mot: dict) -> bool:
    """➕ Em serviço: o motorista registra que está trabalhando fora de viagem. True = está em serviço agora."""
    from config.settings import TIPOS_SERVICO_MOTORISTA
    from repositories import motoristas_repo
    from services import disp_motoristas_service as dms

    ativo = motoristas_repo.servico_ativo(mot["id"])
    if ativo:
        ini = tempo.parse_dt(ativo["inicio"])
        st.markdown(
            f'<div class="car-viagem"><div class="lin"><span>🔧 Em serviço</span><b>{tema._e(ativo.get("tipo") or "")}</b>'
            f'</div><div class="lin"><span>Desde</span><b>{ini:%d/%m %H:%M}</b></div>'
            + (f'<div class="lin"><span>Obs.</span><b>{tema._e(ativo["observacao"])}</b></div>'
               if ativo.get("observacao") else "") + "</div>", unsafe_allow_html=True)
        with st.container(key="car_fim"):
            if st.button("⏹️  ENCERRAR SERVIÇO", type="primary", key="car_serv_fim", **ui.LARGURA):
                ui.acao(dms.encerrar_servico, mot, sucesso="Serviço encerrado.")
        st.caption("Ao iniciar uma viagem, encerre o serviço primeiro.")
        return True
    with st.expander("➕ Em serviço (outra atividade fora de viagem)"):
        tipo = st.selectbox("O que você vai fazer?", TIPOS_SERVICO_MOTORISTA, key="car_serv_tipo")
        obs = st.text_input("Observação", key="car_serv_obs", placeholder="opcional (obrigatório em “Outro”)")
        if st.button("▶️ Começar serviço", type="primary", key="car_serv_ini", **ui.LARGURA):
            ui.acao(dms.iniciar_servico, mot, tipo, obs, sucesso=f"Em serviço: {tipo}.")
    return False


MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
            "Novembro", "Dezembro"]


def _anos(mot: dict) -> list[int]:
    from database.connection import query_one

    r = query_one("""SELECT MIN(a) AS a FROM (
                       SELECT MIN(substr(ts_inicio, 1, 4)) AS a FROM viagens_carreteiro WHERE motorista_id = ?
                       UNION ALL SELECT MIN(substr(data_puxada, 1, 4)) FROM vinculos_pedidos
                       WHERE operacao_id = ? AND lower(trim(motorista)) = lower(trim(?))) x""",
                  (mot["id"], mot["operacao_id"], mot["nome"]))
    atual = tempo.hoje().year
    primeiro = int(r["a"]) if r and r.get("a") and str(r["a"]).isdigit() else atual
    return list(range(atual, min(primeiro, atual) - 1, -1))


def _meses_do_ano(ano: int) -> list[int]:
    hoje = tempo.hoje()
    ultimo = hoje.month if ano == hoje.year else 12
    return list(range(ultimo, 0, -1))  # mais recente primeiro


def _area_variaveis(mot: dict) -> None:
    from services import motoristas_service

    ano = st.selectbox("Ano", _anos(mot), key="car_var_ano")
    nome = mot["nome"].strip().lower()
    total_ano, linhas = 0.0, []
    for m in _meses_do_ano(ano):
        mes = f"{ano}-{m:02d}"
        r = motoristas_service.remuneracao(mot["operacao_id"], mes)
        res = r["resumo"]
        meu = res[res["motorista"].str.strip().str.lower() == nome] if not res.empty else res
        meu = meu.iloc[0].to_dict() if not meu.empty else {}
        v = r["viagens"]
        minhas = v[v["motorista"].fillna("").str.strip().str.lower() == nome] if not v.empty else v
        variavel = float(meu.get("variavel") or 0)
        total_ano += variavel
        linhas.append((m, meu, minhas, variavel))
    st.markdown(f'<div class="car-viagem"><div class="lin"><span>Variável em {ano}</span>'
                f'<b style="color:#0ca30c">{ui.moeda(total_ano)}</b></div></div>', unsafe_allow_html=True)
    st.caption("Toque no mês para abrir. Valores previstos pelas viagens lançadas — o fechamento oficial é da Puxada/RH.")
    for m, meu, minhas, variavel in linhas:
        fixo = float(meu.get("salario_fixo") or 0)
        with st.expander(f"{MESES_PT[m - 1]} · {len(minhas)} viagem(ns) · variável {ui.moeda(variavel)}",
                         expanded=False):
            st.markdown('<div class="car-viagem">' + "".join(
                f'<div class="lin"><span>{a}</span><b>{b}</b></div>' for a, b in [
                    ("Viagens", str(len(minhas))), ("Km rodados", ui.numero(meu.get("km") or 0)),
                    ("Variável", ui.moeda(variavel)), ("Fixo", ui.moeda(fixo)),
                    ("Total previsto", f"<span style='color:#0ca30c'>{ui.moeda(fixo + variavel)}</span>")]) +
                "</div>", unsafe_allow_html=True)
            if not minhas.empty:
                por_fab = minhas.groupby(minhas["fabrica"].fillna("—")).agg(
                    viagens=("valor", "size"), valor=("valor", "sum")).reset_index()
                for f in por_fab.to_dict("records"):
                    st.markdown(f'<div class="car-nf">🏭 <b>{tema._e(f["fabrica"])}</b> · {f["viagens"]} viagem(ns) · '
                                f'<b>{ui.moeda(f["valor"])}</b></div>', unsafe_allow_html=True)


def _area_viagens(mot: dict) -> None:
    ano = st.selectbox("Ano", _anos(mot), key="car_via_ano")
    df = repo.viagens_df(mot["operacao_id"], f"{ano}-01-01", f"{ano}-12-31", motorista_id=mot["id"])
    if df.empty:
        st.info(f"Nenhuma viagem registrada no app em {ano}.")
        return
    df["mes"] = df["ts_inicio"].str[5:7].astype(int)
    st.caption("Toque no mês para ver as viagens.")
    for m in _meses_do_ano(ano):
        doms = df[df["mes"] == m]
        if doms.empty:
            continue
        fin = doms[doms["status"] == repo.FINALIZADA]
        tmvs = [h for h in (_horas(a, b) for a, b in zip(fin["ts_inicio"], fin["ts_fim"])) if h is not None]
        tmv = svc.formatar_duracao(sum(tmvs) / len(tmvs)) if tmvs else "—"
        with st.expander(f"{MESES_PT[m - 1]} · {len(doms)} viagem(ns) · TMV médio {tmv}"):
            for r in doms.to_dict("records"):
                icone = {"Finalizada": "✅", "Em viagem": "🚛"}.get(r["status"], "⛔")
                tempo_v = svc.formatar_duracao(_horas(r["ts_inicio"], r["ts_fim"])) if r.get("ts_fim") else r["status"]
                st.markdown(f'<div class="car-nf">{icone} <b>{_fmt(r["ts_inicio"])}</b> · Pedido '
                            f'{tema._e(r["numero_pedido"])} · {tema._e(r.get("destino") or "")} · {tema._e(r["placa"])}'
                            f'<br><span style="color:#6b6a65">TMV {tempo_v} · {int(r.get("qtd_nfs") or 0)} NF(s)'
                            f'{" · descarga " + tema._e(r.get("desc_tipo")) if r.get("desc_tipo") else ""}</span></div>',
                            unsafe_allow_html=True)


def _area_dados(usuario: dict, mot: dict) -> None:
    from services.motoristas_service import status_cnh

    _, cnh, _ = status_cnh(mot.get("cnh_validade"))
    st.markdown('<div class="car-viagem">' + "".join(
        f'<div class="lin"><span>{a}</span><b>{tema._e(b)}</b></div>' for a, b in [
            ("Nome", mot["nome"]), ("Login (CPF)", usuario.get("login") or ""), ("Celular", mot.get("telefone") or "—"),
            ("CNH", mot.get("cnh") or "—"), ("Validade da CNH", cnh)]) + "</div>", unsafe_allow_html=True)
    st.caption("Algum dado errado? Fale com a Puxada para atualizar o cadastro.")
    tema.secao("🔑 Trocar minha senha")
    with st.form("car_senha", clear_on_submit=True):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Confirme a nova senha", type="password")
        if st.form_submit_button("Salvar nova senha", type="primary", **ui.LARGURA):
            try:
                usuarios_service.trocar_propria_senha(usuario["id"], atual, nova, conf)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                if "k" in st.query_params:  # o acesso lembrado antigo deixa de valer; gera um novo
                    from core.auth import gerar_token

                    st.query_params["k"] = gerar_token(usuario["id"])
                ui.avisar("Senha alterada!")
                st.rerun()
    if st.button("🚪 Sair do app", key="car_sair_dados", **ui.LARGURA):
        _sair()


def render(usuario: dict) -> None:
    mot = repo.motorista_do_usuario(usuario["id"])
    if not mot:
        st.markdown(_CSS, unsafe_allow_html=True)
        st.warning("Seu acesso ainda não está ligado a um motorista. Fale com a equipe da Puxada.")
        if st.button("🚪 Sair"):
            _sair()
        return
    _topo(usuario, mot)
    ui.mostrar_avisos()
    if mot.get("cnh_validade"):
        from services.motoristas_service import status_cnh

        cor, rotulo, dias = status_cnh(mot["cnh_validade"])
        if dias is not None and dias <= 90:
            (st.error if dias <= 30 else st.warning)(
                f"🪪 Sua CNH {'venceu' if dias < 0 else 'vence em breve'}: {rotulo.split(' ', 1)[-1]}. "
                "Renove e avise a Puxada para atualizar o cadastro.")
    with st.container(key="nav_mod_motorista"):
        area = ui._escolha("car_area", AREAS, AREAS[0])
    if area == AREAS[1]:
        _area_variaveis(mot)
    elif area == AREAS[2]:
        _area_viagens(mot)
    elif area == AREAS[3]:
        _area_dados(usuario, mot)
    else:
        _area_viagem(usuario, mot)
