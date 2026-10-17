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


def _ir(area=None, end=None, prod=None) -> None:
    st.session_state["rapp_area"] = area
    st.session_state["rapp_end"] = end
    st.session_state["rapp_prod"] = prod


def _como(r) -> str:
    """O que já foi lançado (ex.: 1 PL + 3 CX + 2 UN)."""
    partes = [f"{int(v)} {u}" for v, u in ((getattr(r, "pl", None), "PL"), (getattr(r, "cx", None), "CX"),
                                          (getattr(r, "un_s", None), "UN")) if v is not None and pd.notna(v) and v]
    if partes:
        return " + ".join(partes)
    return "0" if r.status == "contado" else ""


def render(usuario: dict, operacao_id: int, modo_app: bool = False) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    if modo_app:
        tema.cabecalho("Recontagem", f"Olá, {str(usuario.get('nome') or '').split(' ')[0]}! Escolha a área, o "
                                     "endereço e o produto para contar.", "📱")
    pend = inv.app_pendentes(operacao_id)
    with st.container(key="rapp"):
        area, end, prod = (st.session_state.get("rapp_area"), st.session_state.get("rapp_end"),
                           st.session_state.get("rapp_prod"))
        if pend.empty:
            _ir()
            st.success("Nada para recontar agora. 👏")
            if st.button("🔄 Atualizar", key="rapp_atual", **ui.LARGURA):
                st.rerun()
            return
        if area and area not in set(pend["area"]):
            _ir()
            area = end = prod = None
        if not area:
            _inicio(pend)
        elif end is None or end not in set(pend.loc[pend["area"] == area, "endereco"]):
            _area(pend, area, usuario, operacao_id)
        elif prod is None or int(prod) not in set(pend["id"].astype(int)):
            _endereco(pend, area, end)
        else:
            _produto(pend, area, end, int(prod), usuario)


def _inicio(pend: pd.DataFrame) -> None:
    st.markdown("#### 🗺️ Áreas para recontar")
    for (area, nome), d in pend.groupby(["area", "area_nome"], sort=False):
        falta = int((d["status"] == "pendente").sum())
        icone = "✅" if not falta else "📍"
        rot = f"{icone}  {nome}  ·  {falta} item(ns) para recontar" + (f" · {len(d) - falta} feito(s)" if len(d) > falta
                                                                         else "")
        if st.button(rot, key=f"rapp_a_{area}", **ui.LARGURA):
            _ir(area)
            st.rerun()


def _area(pend: pd.DataFrame, area: str, usuario: dict, op: int) -> None:
    d = pend[pend["area"] == area]
    if st.button("← Áreas", key="rapp_volta_a"):
        _ir()
        st.rerun()
    st.markdown(f"#### 📍 {d['area_nome'].iloc[0]} — endereços para recontar")
    ends = d.groupby("endereco", sort=True).agg(itens=("id", "size"),
                                                feitos=("status", lambda s: int((s == "contado").sum())))
    for e, r in ends.iterrows():
        feito = r.feitos == r.itens
        rot = f"{'✅' if feito else '🔲'}  {e or '(sem endereço)'}  ·  {int(r.feitos)}/{int(r.itens)} produto(s)"
        if st.button(rot, key=f"rapp_e_{area}_{e}", **ui.LARGURA):
            _ir(area, e)
            st.rerun()
    if (ends["feitos"] == ends["itens"]).all():
        st.success("Tudo desta área foi contado. Confira e faça a descarga — depois dela não dá mais para editar.")
        if st.button("📤 Descarga — enviar a recontagem", type="primary", key=f"rapp_desc_{area}", **ui.LARGURA):
            try:
                n = inv.descarga(op, area, usuario)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                _ir()
                ui.avisar(f"Descarga feita: {n} item(ns) enviados para a gestão. Obrigado!")
                st.rerun()
    else:
        st.caption(f"Faltam {int((ends['itens'] - ends['feitos']).sum())} produto(s). Depois de contar tudo aparece "
                   "a 📤 Descarga.")


def _endereco(pend: pd.DataFrame, area: str, end: str) -> None:
    d = pend[(pend["area"] == area) & (pend["endereco"] == end)]
    if st.button("← Endereços", key="rapp_volta_e"):
        _ir(area)
        st.rerun()
    st.markdown(f"#### 🔲 {d['area_nome'].iloc[0]} · endereço **{end or '(sem endereço)'}**")
    st.caption("Toque no produto para contar. Contado fica ✅ — dá para abrir de novo e editar até a descarga.")
    for r in d.itertuples():
        feito = r.status == "contado"
        rot = (f"{'✅' if feito else '🔲'}  {r.produto} · {str(r.descricao or '')[:38]}"
               + (f"  ·  {_como(r)}  ✏️" if feito else ""))
        if st.button(rot, key=f"rapp_p_{r.id}", **ui.LARGURA):
            _ir(area, end, int(r.id))
            st.rerun()


def _produto(pend: pd.DataFrame, area: str, end: str, rid: int, usuario: dict) -> None:
    r = next(x for x in pend.itertuples() if int(x.id) == rid)
    if st.button("← Produtos do endereço", key="rapp_volta_p"):
        _ir(area, end)
        st.rerun()
    fator = float(r.fator or 1)
    cxp = float(r.cx_pallet) if pd.notna(getattr(r, "cx_pallet", None)) and r.cx_pallet else 0.0
    contado = r.status == "contado"

    def ini(v):
        return int(v) if contado and v is not None and pd.notna(v) else 0
    pl0, cx0, un0 = ini(getattr(r, "pl", None)), ini(getattr(r, "cx", None)), ini(getattr(r, "un_s", None))
    if contado and pl0 == cx0 == un0 == 0 and pd.notna(r.qtd_un) and r.qtd_un:
        cx0, un0 = int(r.qtd_un // fator), int(round(r.qtd_un - (r.qtd_un // fator) * fator))
    info = ("caixa com " + str(int(fator)) + " un" if fator > 1 else "unidade de venda") + \
        (f" · palete com {int(cxp)} cx" if cxp else "")
    st.markdown(f'<div class="rapp-prod"><b>{tema._e(r.produto)} · {tema._e(r.descricao or "")}</b><br>'
                f'<span>📍 {tema._e(r.area_nome)} · {tema._e(end or "")} · {info}'
                f'{" · ✏️ já contado — pode editar" if contado else ""}</span></div>', unsafe_allow_html=True)
    with st.form(f"rapp_fp_{rid}"):
        pl = st.number_input("Paletes", min_value=0, step=1, value=pl0, key=f"rapp_pl_{rid}", disabled=not cxp,
                             help=None if cxp else "Sem caixas por palete na 01.11")
        cx = st.number_input("Caixas", min_value=0, step=1, value=cx0, key=f"rapp_cx_{rid}")
        un = st.number_input("Unidades soltas", min_value=0, step=1, value=un0, key=f"rapp_un_{rid}",
                             disabled=fator <= 1)
        if st.form_submit_button("💾 Salvar contagem", type="primary", **ui.LARGURA):
            try:
                inv.registrar_app(rid, cx, un, usuario.get("nome", ""), paletes=pl)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                _ir(area, end)
                ui.avisar(f"{r.produto} contado ✅")
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
    login = st.text_input("CPF", key="rapp_login", placeholder="000.000.000-00")
    if not login.strip():
        return
    sit = inv.situacao_conferente(op, login)
    if sit == "sem_cadastro":
        st.error("CPF não cadastrado nesta revenda. Peça à gestão do armazém.")
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
        st.caption("Esqueceu a senha? Peça à gestão do armazém para trocar.")


def _logar(conf: dict, manter: bool = True) -> None:
    st.session_state["rapp_conf"] = conf
    if manter:
        tok = inv.token_conferente(conf)
        if tok:
            st.query_params["c"] = tok
    st.rerun()
