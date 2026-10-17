"""📱 App de Recontagem do inventário (tela de celular).

Início: as áreas com recontagem → clicando na área, os endereços → clicando no endereço, os produtos para contar
(contagem cega: o conferente não vê a 1ª nem a 2ª contagem). Endereço contado fica ✅; com todos contados aparece
📤 Descarga, que manda para a gestão conciliar e avisa os responsáveis.
Abre pela aba do Armazém ou direto pelo link ...?app=recontagem (entra com o login do sistema).
"""
import pandas as pd
import streamlit as st

from core import tema, ui
from services import inventario_service as inv
from services.erros import RegraNegocioError

_CSS = """
<style>
.st-key-rapp div.stButton > button {min-height: 3.4rem; font-size: 1.05rem; text-align: left; justify-content: flex-start;}
.rapp-prod {border: 1px solid #e3e7ee; border-radius: 12px; padding: .6rem .8rem; margin: .4rem 0 .2rem 0;
            background: #fff;}
.rapp-prod b {font-size: 1.05rem;}
.rapp-prod span {color: #5b6575; font-size: .85rem;}
</style>
"""


def _ir(area=None, end=None) -> None:
    st.session_state["rapp_area"] = area
    st.session_state["rapp_end"] = end


def render(usuario: dict, operacao_id: int, modo_app: bool = False) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    if modo_app:
        tema.cabecalho("Recontagem", f"Olá, {str(usuario.get('nome') or '').split(' ')[0]}! Conte o que aparece "
                                     "em cada endereço.", "📱")
    pend = inv.app_pendentes(operacao_id)
    with st.container(key="rapp"):
        area, end = st.session_state.get("rapp_area"), st.session_state.get("rapp_end")
        if pend.empty:
            _ir()
            st.success("Nada para recontar agora. 👏")
            if st.button("🔄 Atualizar", key="rapp_atual", **ui.LARGURA):
                st.rerun()
            return
        if area and area not in set(pend["area"]):
            _ir()
            area = end = None
        if not area:
            _inicio(pend)
        elif end is None or end not in set(pend.loc[pend["area"] == area, "endereco"]):
            _area(pend, area, usuario, operacao_id)
        else:
            _endereco(pend, area, end, usuario)


def _inicio(pend: pd.DataFrame) -> None:
    st.markdown("#### 🗺️ Áreas para recontar")
    for (area, nome), d in pend.groupby(["area", "area_nome"], sort=False):
        feitos = d.groupby("endereco")["status"].apply(lambda s: (s == "contado").all()).sum()
        tot = d["endereco"].nunique()
        icone = "✅" if feitos == tot else "📍"
        rot = f"{icone}  {nome}  ·  {tot - feitos} de {tot} endereço(s) para contar · {len(d)} item(ns)"
        if d["armazem"].iloc[0] and d["armazem"].iloc[0] != "— sem armazém":
            rot += f"  ·  {d['armazem'].iloc[0]}"
        if st.button(rot, key=f"rapp_a_{area}", **ui.LARGURA):
            _ir(area)
            st.rerun()


def _area(pend: pd.DataFrame, area: str, usuario: dict, op: int) -> None:
    d = pend[pend["area"] == area]
    if st.button("← Áreas", key="rapp_volta_a"):
        _ir()
        st.rerun()
    st.markdown(f"#### 📍 {d['area_nome'].iloc[0]}")
    ends = d.groupby("endereco", sort=True).agg(itens=("id", "size"),
                                                feito=("status", lambda s: (s == "contado").all()))
    for e, r in ends.iterrows():
        rot = f"{'✅' if r.feito else '🔲'}  Endereço {e or '(sem endereço)'}  ·  {int(r.itens)} produto(s)"
        if st.button(rot, key=f"rapp_e_{area}_{e}", **ui.LARGURA):
            _ir(area, e)
            st.rerun()
    if ends["feito"].all():
        st.success("Todos os endereços desta área foram contados.")
        if st.button("📤 Descarga — enviar a recontagem", type="primary", key=f"rapp_desc_{area}", **ui.LARGURA):
            try:
                n = inv.descarga(op, area, usuario)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                _ir()
                ui.avisar(f"Descarga feita: {n} item(ns) enviados para a gestão conciliar. Obrigado!")
                st.rerun()
    else:
        st.caption(f"Faltam {int((~ends['feito']).sum())} endereço(s). Depois de contar todos aparece a 📤 Descarga.")


def _endereco(pend: pd.DataFrame, area: str, end: str, usuario: dict) -> None:
    d = pend[(pend["area"] == area) & (pend["endereco"] == end)]
    if st.button("← Endereços", key="rapp_volta_e"):
        _ir(area)
        st.rerun()
    st.markdown(f"#### 🔲 {d['area_nome'].iloc[0]} · endereço **{end or '(sem endereço)'}**")
    st.caption("Conte e informe as caixas e as unidades soltas de cada produto.")
    with st.form(f"rapp_f_{area}_{end}"):
        valores = {}
        for r in d.itertuples():
            fator = float(r.fator or 1)
            ja = r.qtd_un if r.status == "contado" and pd.notna(r.qtd_un) else None
            st.markdown(f'<div class="rapp-prod"><b>{tema._e(r.produto)} · {tema._e(r.descricao or "")}</b><br>'
                        f'<span>{"caixa com " + str(int(fator)) + " un" if fator > 1 else "unidade de venda"}'
                        f'{" · já contado" if ja is not None else ""}</span></div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            cx = c1.number_input("Caixas", min_value=0, step=1, key=f"rapp_cx_{r.id}",
                                 value=int(ja // fator) if ja is not None else 0)
            un = c2.number_input("Unidades soltas", min_value=0, step=1, key=f"rapp_un_{r.id}",
                                 value=int(round(ja - (ja // fator) * fator)) if ja is not None else 0,
                                 disabled=fator <= 1)
            valores[int(r.id)] = (cx, un)
        if st.form_submit_button("💾 Salvar endereço", type="primary", **ui.LARGURA):
            try:
                for rid, (cx, un) in valores.items():
                    inv.registrar_app(rid, cx, un, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                _ir(area)
                ui.avisar(f"Endereço {end} salvo.")
                st.rerun()


# --- link da revenda (…?app=recontagem&k=…): login próprio dos conferentes -------------------------------------------
def app_link(token: str) -> None:
    """Abre o app pelo link da revenda: o conferente entra com o login cadastrado em Acuracidade › Cadastros."""
    op = inv.op_por_link(token)
    if not op:
        tema.cabecalho("Recontagem", "", "📱")
        st.warning("🔒 Link inválido ou trocado. Peça o link atualizado à gestão do armazém.")
        return
    from repositories import operacoes_repo

    revenda = (operacoes_repo.buscar(op) or {}).get("nome", "")
    conf = st.session_state.get("rapp_conf")
    if conf and int(conf.get("operacao_id", 0)) != op:
        conf = None
    if not conf and st.query_params.get("c"):
        conf = inv.conferente_por_token(st.query_params.get("c"), op)
        if conf:
            st.session_state["rapp_conf"] = conf
        else:
            del st.query_params["c"]
    ui.mostrar_avisos()
    if not conf:
        _login(op, revenda)
        return
    st.caption(f"🏢 {revenda}")
    render(conf, op, modo_app=True)
    if st.button("🚪 Sair", key="rapp_sair_conf"):
        st.session_state.pop("rapp_conf", None)
        if "c" in st.query_params:
            del st.query_params["c"]
        st.rerun()


def _login(op: int, revenda: str) -> None:
    tema.cabecalho("Recontagem do inventário", revenda, "📱")
    st.markdown("#### 🔐 Entrar")
    login = st.text_input("Login (o que a gestão cadastrou: CPF, matrícula…)", key="rapp_login")
    if not login.strip():
        return
    sit = inv.situacao_conferente(op, login)
    if sit == "sem_cadastro":
        st.error("Login não cadastrado nesta revenda. Peça à gestão do armazém.")
    elif sit == "bloqueado":
        st.error("Acesso bloqueado. Fale com a gestão do armazém.")
    elif sit == "criar_senha":
        st.info("👋 Primeiro acesso: crie a sua senha (mínimo 4 caracteres).")
        s1 = st.text_input("Nova senha", type="password", key="rapp_s1")
        s2 = st.text_input("Confirme a senha", type="password", key="rapp_s2")
        if st.button("Criar senha e entrar", type="primary", key="rapp_criar", **ui.LARGURA):
            try:
                conf = inv.criar_senha_conferente(op, login, s1, s2)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                _logar(conf)
    else:
        senha = st.text_input("Senha", type="password", key="rapp_senha")
        manter = st.checkbox("Manter conectado neste celular", value=True, key="rapp_manter")
        if st.button("Entrar", type="primary", key="rapp_entrar", **ui.LARGURA):
            try:
                conf = inv.entrar_conferente(op, login, senha)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                _logar(conf, manter)
        st.caption("Esqueceu a senha? Peça à gestão para zerar — no próximo acesso você cria outra.")


def _logar(conf: dict, manter: bool = True) -> None:
    st.session_state["rapp_conf"] = conf
    if manter:
        tok = inv.token_conferente(conf)
        if tok:
            st.query_params["c"] = tok
    st.rerun()
