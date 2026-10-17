"""📱 App de Recontagem do inventário (tela de celular).

Início: separado em 📦 Inventário mensal e 🔄 Inventário diário (com o dia da contagem); as áreas com recontagem →
clicando na área, os endereços → clicando no endereço, os produtos para contar
(contagem cega: o conferente não vê a 1ª nem a 2ª contagem). Endereço contado fica ✅; com todos contados aparece
📤 Descarga, que manda para a gestão conciliar e avisa os responsáveis.
Abre pela aba do Armazém ou direto pelo link ...?app=recontagem (entra com o login do sistema).
"""
import ast
import operator
import re

import pandas as pd
import streamlit as st

from core import tema, ui
from services import inventario_service as inv
from services.erros import RegraNegocioError

_CSS = """
<style>
.st-key-rapp {max-width: 560px; margin: 0 auto;}
.st-key-rapp div.stButton > button {min-height: 3.4rem; font-size: 1.05rem; text-align: left; justify-content: flex-start;}
.rapp-prod {border: 1px solid #e3e7ee; border-radius: 12px; padding: .6rem .8rem; margin: .4rem 0 .2rem 0;
            background: #fff;}
.rapp-prod b {font-size: 1.05rem;}
.rapp-prod span {color: #5b6575; font-size: .85rem;}
.rapp-inv {border-left: 5px solid #1f6feb; background: #f2f6fc; border-radius: 10px; padding: .55rem .8rem;
           margin: .8rem 0 .3rem 0; font-weight: 700; font-size: 1.05rem; color: #1b2a41;}
.rapp-inv span {display: block; font-weight: 400; font-size: .85rem; color: #5b6575;}
.st-key-rapp [data-testid="stNumberInput"] input {font-size: 2rem; font-weight: 700; height: 3.6rem;
                                                  text-align: center;}
.st-key-rapp [data-testid="stNumberInput"] button {min-width: 3.2rem; height: 3.6rem;}
.st-key-rapp [data-testid="stNumberInput"] label p, .st-key-rapp [data-testid="stTextInput"] label p
    {font-size: 1.1rem; font-weight: 600;}
.st-key-rapp [data-testid="stTextInput"] input {font-size: 1.4rem; height: 3.2rem;}
.rapp-res {font-size: 2.2rem; font-weight: 800; text-align: center; color: #1b2a41; padding: .2rem 0;}
.rapp-res small {display: block; font-size: .85rem; font-weight: 400; color: #5b6575;}
@media (prefers-color-scheme: dark) {
  .rapp-prod {background: #1c2230; border-color: #2c3445;}
  .rapp-inv {background: #1c2a40; color: #e6edf6;}
  .rapp-res {color: #e6edf6;}
}
</style>
"""
_TIPOS = {"mensal": "📦 Inventário mensal", "diario": "🔄 Inventário diário"}


def _ir(inv_id=None, area=None, end=None, prod=None) -> None:
    st.session_state["rapp_inv"] = inv_id
    st.session_state["rapp_area"] = area
    st.session_state["rapp_end"] = end
    st.session_state["rapp_prod"] = prod


def _dia(v) -> str:
    try:
        return pd.to_datetime(v).strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        return str(v or "")


def _titulo_inv(d: pd.DataFrame) -> tuple[str, str]:
    """Cabeçalho do inventário: dia da conciliação (diário) ou mês (mensal)."""
    r = d.iloc[0]
    if r["tipo"] == "diario":
        return f"📅 Contagem de {_dia(r['data'])}", "Inventário diário · conciliação com o estoque do dia"
    return f"📦 Inventário {ui.nome_mes(r['mes'])}", f"Inventário mensal · {r['inventario'] or ''}"


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
        tema.cabecalho("Recontagem", f"Olá, {str(usuario.get('nome') or '').split(' ')[0]}! Escolha o inventário, "
                                     "a área, o endereço e o produto.", "📱")
    pend = inv.app_pendentes(operacao_id)
    with st.container(key="rapp"):
        if pend.empty:
            _ir()
            st.success("Nada para recontar agora. 👏")
            if st.button("🔄 Atualizar", key="rapp_atual", **ui.LARGURA):
                st.rerun()
            return
        pend["inv_id"] = pend["inv_id"].astype(int)
        iv, area, end, prod = (st.session_state.get("rapp_inv"), st.session_state.get("rapp_area"),
                               st.session_state.get("rapp_end"), st.session_state.get("rapp_prod"))
        d = pend[(pend["inv_id"] == iv) & (pend["area"] == area)] if iv is not None else pend.iloc[0:0]
        if d.empty:
            _ir()
            _inicio(pend)
        elif end is None or end not in set(d["endereco"]):
            _area(d, usuario, operacao_id)
        elif prod is None or int(prod) not in set(d["id"].astype(int)):
            _endereco(d, end)
        else:
            _produto(d, end, int(prod), usuario)


def _inicio(pend: pd.DataFrame) -> None:
    conta = {t: int((pend.loc[pend["tipo"] == t, "status"] == "pendente").sum()) for t in _TIPOS}
    tem = [t for t in _TIPOS if (pend["tipo"] == t).any()]
    padrao = next((t for t in tem if conta[t]), tem[0])
    tipo = ui._escolha("rapp_tipo", list(_TIPOS), padrao,
                       formatar=lambda t: f"{_TIPOS[t]} ({conta[t]})")
    d = pend[pend["tipo"] == tipo]
    if d.empty:
        st.success(f"Nada para recontar no {_TIPOS[tipo].split(' ', 1)[1].lower()}. 👏")
        return
    for iv, di in d.groupby("inv_id", sort=False):
        tit, sub = _titulo_inv(di)
        falta_i = int((di["status"] == "pendente").sum())
        st.markdown(f'<div class="rapp-inv">{tema._e(tit)}<span>{tema._e(sub)} · {falta_i} item(ns) para recontar'
                    f'</span></div>', unsafe_allow_html=True)
        for (area, nome), da in di.groupby(["area", "area_nome"], sort=False):
            falta = int((da["status"] == "pendente").sum())
            icone = "✅" if not falta else "📍"
            rot = f"{icone}  {nome}  ·  {falta} para recontar" + (f" · {len(da) - falta} feito(s)" if len(da) > falta
                                                                     else "")
            if st.button(rot, key=f"rapp_a_{iv}_{area}", **ui.LARGURA):
                _ir(int(iv), area)
                st.rerun()


def _area(d: pd.DataFrame, usuario: dict, op: int) -> None:
    iv, area = int(d["inv_id"].iloc[0]), d["area"].iloc[0]
    if st.button("← Início", key="rapp_volta_a"):
        _ir()
        st.rerun()
    tit, _ = _titulo_inv(d)
    st.markdown(f'<div class="rapp-inv">{tema._e(tit)}<span>📍 {tema._e(d["area_nome"].iloc[0])} — endereços para '
                f'recontar</span></div>', unsafe_allow_html=True)
    ends = d.groupby("endereco", sort=True).agg(itens=("id", "size"),
                                                feitos=("status", lambda s: int((s == "contado").sum())))
    for e, r in ends.iterrows():
        feito = r.feitos == r.itens
        rot = f"{'✅' if feito else '🔲'}  {e or '(sem endereço)'}  ·  {int(r.feitos)}/{int(r.itens)} produto(s)"
        if st.button(rot, key=f"rapp_e_{iv}_{area}_{e}", **ui.LARGURA):
            _ir(iv, area, e)
            st.rerun()
    if (ends["feitos"] == ends["itens"]).all():
        st.success("Tudo desta área foi contado. Confira e faça a descarga — depois dela não dá mais para editar.")
        if st.button("📤 Descarga — enviar a recontagem", type="primary", key=f"rapp_desc_{iv}_{area}", **ui.LARGURA):
            try:
                n = inv.descarga(op, area, usuario, iv)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                _ir()
                ui.avisar(f"Descarga feita: {n} item(ns) enviados para a gestão. Obrigado!")
                st.rerun()
    else:
        st.caption(f"Faltam {int((ends['itens'] - ends['feitos']).sum())} produto(s). Depois de contar tudo aparece "
                   "a 📤 Descarga.")


def _endereco(d: pd.DataFrame, end: str) -> None:
    iv, area = int(d["inv_id"].iloc[0]), d["area"].iloc[0]
    d = d[d["endereco"] == end]
    if st.button("← Endereços", key="rapp_volta_e"):
        _ir(iv, area)
        st.rerun()
    tit, _ = _titulo_inv(d)
    st.markdown(f'<div class="rapp-inv">{tema._e(tit)}<span>📍 {tema._e(d["area_nome"].iloc[0])} · endereço '
                f'<b>{tema._e(end or "(sem endereço)")}</b></span></div>', unsafe_allow_html=True)
    st.caption("Toque no produto para contar. Contado fica ✅ — dá para abrir de novo e editar até a descarga.")
    for r in d.itertuples():
        feito = r.status == "contado"
        rot = (f"{'✅' if feito else '🔲'}  {r.produto} · {str(r.descricao or '')[:38]}"
               + (f"  ·  {_como(r)}  ✏️" if feito else ""))
        if st.button(rot, key=f"rapp_p_{r.id}", **ui.LARGURA):
            _ir(iv, area, end, int(r.id))
            st.rerun()


# --- 🧮 calculadora ---------------------------------------------------------------------------------------------------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def calcular(expr: str) -> float | None:
    """Conta simples do conferente: 12+8+15, 3x12, 10 15 20 (espaço soma). Só números e + - x * / ( )."""
    t = str(expr or "").strip().lower().replace("×", "*").replace("x", "*").replace(",", ".")
    if not t:
        return None
    t = re.sub(r"(?<=[\d)])\s+(?=[\d(])", "+", t)
    if not re.fullmatch(r"[\d.+\-*/() ]+", t):
        return None

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise ValueError
    try:
        return ev(ast.parse(t, mode="eval"))
    except Exception:  # noqa: BLE001 — conta incompleta/errada: só não mostra resultado
        return None


def _usar(chave: str, valor: float) -> None:
    st.session_state[chave] = max(int(round(valor)), 0)


def _calculadora(rid: int, chaves: dict) -> None:
    with st.expander("🧮 Calculadora — somar antes de lançar"):
        conta = st.text_input("Conta", key=f"rapp_calc_{rid}", placeholder="ex.: 12+8+15  ou  3x12  ou  10 15 20")
        v = calcular(conta)
        if conta.strip() and v is None:
            st.caption("Use só números e + − x ÷ (ex.: 12+8+15).")
        if v is not None:
            st.markdown(f'<div class="rapp-res">= {ui.numero(v, 0 if float(v).is_integer() else 2)}'
                        f'<small>toque para usar o resultado</small></div>', unsafe_allow_html=True)
            for rot, ch in chaves.items():
                st.button(f"➡️ Usar em {rot}", key=f"rapp_usar_{ch}", on_click=_usar, args=(ch, v), **ui.LARGURA)


def _produto(d: pd.DataFrame, end: str, rid: int, usuario: dict) -> None:
    iv, area = int(d["inv_id"].iloc[0]), d["area"].iloc[0]
    r = next(x for x in d.itertuples() if int(x.id) == rid)
    if st.button("← Produtos do endereço", key="rapp_volta_p"):
        _ir(iv, area, end)
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
    tit, _ = _titulo_inv(d)
    st.markdown(f'<div class="rapp-prod"><b>{tema._e(r.produto)} · {tema._e(r.descricao or "")}</b><br>'
                f'<span>{tema._e(tit)} · 📍 {tema._e(r.area_nome)} · {tema._e(end or "")} · {info}'
                f'{" · ✏️ já contado — pode editar" if contado else ""}</span></div>', unsafe_allow_html=True)
    k_pl, k_cx, k_un = f"rapp_pl_{rid}", f"rapp_cx_{rid}", f"rapp_un_{rid}"
    for k, v0 in ((k_pl, pl0), (k_cx, cx0), (k_un, un0)):
        if k not in st.session_state:
            st.session_state[k] = v0
    chaves = {"Caixas": k_cx}
    if cxp:
        chaves = {"Paletes": k_pl, **chaves}
    if fator > 1:
        chaves["Unidades"] = k_un
    _calculadora(rid, chaves)
    with st.form(f"rapp_fp_{rid}"):
        pl = st.number_input("Paletes", min_value=0, step=1, key=k_pl, disabled=not cxp,
                             help=None if cxp else "Sem caixas por palete na 01.11")
        cx = st.number_input("Caixas", min_value=0, step=1, key=k_cx)
        un = st.number_input("Unidades soltas", min_value=0, step=1, key=k_un, disabled=fator <= 1)
        if st.form_submit_button("💾 Salvar contagem", type="primary", **ui.LARGURA):
            try:
                inv.registrar_app(rid, cx, un, usuario.get("nome", ""), paletes=pl)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                for k in (k_pl, k_cx, k_un, f"rapp_calc_{rid}"):
                    st.session_state.pop(k, None)
                _ir(iv, area, end)
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
