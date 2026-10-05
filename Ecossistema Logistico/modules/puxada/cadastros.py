"""Puxada › Cadastros — todos no mesmo padrão: ➕ novo no topo, tabela legível e ✏️ alterar/excluir no final.

Trechos separados em dois:
  • 🛣️ Frota própria — fábrica → revenda: valor da viagem do motorista, km e tempo padrão
    (alimenta a 💵 Remuneração e a produtividade dos motoristas).
  • 🚚 Spot (frete) — trechos contratados com transportadora: valor do frete, pedágio e aprovador
    (alimenta o 📝 Solicitar Frete).
"""
import streamlit as st

from config.settings import TIPOS_OD
from core import ui
from modules.componentes.cadastro import Campo, tela
from repositories import cadastros_repo, logistica_repo, motoristas_repo, usuarios_repo
from services import cadastros_service as svc
from services.erros import RegraNegocioError

STATUS_CARRETA = ["Disponível", "Em Trânsito", "Manutenção", "Inativa"]
PARTES = {
    "proprio": "🛣️ Trechos frota própria",
    "spot": "🚚 Trechos spot (frete)",
    "fabricas": "🏭 Fábricas",
    "carretas": "🚛 Carretas",
    "motoristas": "👤 Motoristas",
    "transp": "🏢 Transportadoras",
    "od": "📍 Origens/Destinos",
    "cc": "🏷️ Centros de custo",
}


def _txt(v, nome):
    v = (v or "").strip() if isinstance(v, str) or v is None else str(v)
    if not v:
        raise RegraNegocioError(f"Informe {nome}.")
    return v


# --- Trechos da frota própria ----------------------------------------------------
def _trechos_proprios(operacao_id: int) -> None:
    fabs = logistica_repo.fabricas_df()
    if fabs.empty:
        st.info("Cadastre primeiro as **🏭 Fábricas**.")
        return
    nomes = {int(r.id): r.nome for r in fabs.itertuples()}
    df = motoristas_repo.trechos_proprios_df(operacao_id)

    def salvar(tid, d):
        fid = int(d["fabrica_id"])
        args = (float(d["valor_viagem"] or 0), float(d["km"] or 0), float(d["tempo_padrao_h"] or 0))
        if tid:
            motoristas_repo.atualizar_trecho_proprio(tid, fid, *args)
        else:
            motoristas_repo.salvar_trecho_proprio(operacao_id, fid, *args)

    tela(chave=f"tp_{operacao_id}", titulo="Trechos da frota própria", icone="🛣️", df=df,
         descricao="Fábrica → revenda com carreta própria. O valor da viagem é a remuneração variável do motorista; "
                   "km e tempo padrão medem a produtividade.",
         campos=[Campo("fabrica_id", "Fábrica (origem)", "opcoes", True, nomes),
                 Campo("valor_viagem", "Valor da viagem p/ motorista (R$)", "moeda", True, passo=10),
                 Campo("km", "Distância (km)", "numero", passo=10),
                 Campo("tempo_padrao_h", "Tempo padrão da viagem (h)", "numero", passo=0.5,
                       ajuda="Ida e volta, para comparar com o TMV real.")],
         salvar=salvar, excluir=motoristas_repo.excluir_trecho_proprio,
         rotulo_registro=lambda r: f"{r['fabrica']} → revenda")


# --- Trechos spot -------------------------------------------------------------------
def _trechos_spot(operacao_id: int) -> None:
    origens = {o["id"]: o["nome"] for o in cadastros_repo.listar_od(operacao_id, "origem")}
    destinos = {o["id"]: o["nome"] for o in cadastros_repo.listar_od(operacao_id, "destino")}
    transps = {t["id"]: t["nome"] for t in cadastros_repo.listar_transportadoras()}
    aprovs = {a["id"]: a["nome"] for a in usuarios_repo.listar_aprovadores()}
    df = cadastros_repo.listar_trechos_df(operacao_id)

    def salvar(tid, d):
        if float(d["valor_frete"] or 0) <= 0:
            raise RegraNegocioError("Informe o valor do frete do trecho.")
        if d["origem_id"] == d["destino_id"]:
            raise RegraNegocioError("Origem e destino não podem ser iguais.")
        atual = df[df["id"] == tid].iloc[0].to_dict() if tid else {}
        if tid and (atual["origem_id"], atual["destino_id"]) != (d["origem_id"], d["destino_id"]):
            svc.excluir_trecho(tid)
        svc.salvar_trecho(operacao_id, d["origem_id"], d["destino_id"], float(d["distancia_km"] or 0),
                          float(d["pedagio"] or 0), float(atual.get("valor_remunerado") or 0),
                          float(d["valor_frete"] or 0), d.get("transportadora_id"), d.get("aprovador_id"))

    tela(chave=f"ts_{operacao_id}", titulo="Trechos spot (frete contratado)", icone="🚚", df=df,
         descricao="Trechos com transportadora — já trazem valor, pedágio e aprovador para o 📝 Solicitar Frete.",
         campos=[Campo("origem_id", "Origem", "opcoes", True, origens),
                 Campo("destino_id", "Destino", "opcoes", True, destinos),
                 Campo("transportadora_id", "Transportadora", "opcoes", False, transps),
                 Campo("valor_frete", "Valor do frete (R$)", "moeda", True, passo=100),
                 Campo("pedagio", "Pedágio (R$)", "moeda", passo=10),
                 Campo("distancia_km", "Distância (km)", "numero", passo=10),
                 Campo("aprovador_id", "Aprovador", "opcoes", False, aprovs)],
         salvar=salvar, excluir=svc.excluir_trecho,
         rotulo_registro=lambda r: f"{r['origem']} ➔ {r['destino']} · {r.get('transportadora') or 'sem transportadora'}")


# --- Demais cadastros ------------------------------------------------------------------
def _fabricas() -> None:
    df = logistica_repo.fabricas_df()
    tela(chave="fab", titulo="Fábricas (cervejarias)", icone="🏭", df=df,
         descricao="Origem das viagens da frota própria, do App Carreteiro e do frete spot.",
         campos=[Campo("nome", "Fábrica", obrigatorio=True), Campo("cidade", "Cidade"), Campo("uf", "UF")],
         salvar=lambda fid, d: logistica_repo.salvar_fabrica(fid, _txt(d["nome"], "o nome"), d.get("cidade") or "",
                                                             (d.get("uf") or "").upper()[:2]),
         excluir=lambda fid: logistica_repo.excluir("fabricas", fid))


def _carretas(operacao_id: int) -> None:
    df = logistica_repo.carretas_df(operacao_id)
    tela(chave=f"car_{operacao_id}", titulo="Carretas / placas da frota própria", icone="🚛", df=df,
         campos=[Campo("placa", "Placa", obrigatorio=True), Campo("modelo", "Modelo"),
                 Campo("capacidade_hl", "Capacidade (HL)", "numero", passo=10),
                 Campo("status", "Status", "opcoes", True, STATUS_CARRETA, padrao=STATUS_CARRETA[0])],
         salvar=lambda cid, d: logistica_repo.salvar_carreta(operacao_id, cid, _txt(d["placa"], "a placa").upper(),
                                                             d.get("modelo") or "", float(d.get("capacidade_hl") or 0),
                                                             d.get("status") or STATUS_CARRETA[0]),
         excluir=lambda cid: logistica_repo.excluir("carretas", cid))


def _transportadoras() -> None:
    import pandas as pd

    df = pd.DataFrame(cadastros_repo.listar_transportadoras())
    tela(chave="transp", titulo="Transportadoras (frete spot)", icone="🏢", df=df,
         campos=[Campo("nome", "Nome", obrigatorio=True), Campo("cnpj", "CNPJ"),
                 Campo("contato", "Contato / e-mail / telefone")],
         salvar=lambda tid, d: (svc.atualizar_transportadora(tid, d["nome"], d.get("cnpj"), d.get("contato")) if tid
                                else svc.criar_transportadora(d["nome"], d.get("cnpj") or "", d.get("contato") or "")),
         excluir=svc.excluir_transportadora)


def _od(operacao_id: int) -> None:
    import pandas as pd

    df = pd.DataFrame(cadastros_repo.listar_od(operacao_id))
    tela(chave=f"od_{operacao_id}", titulo="Origens e destinos (frete spot)", icone="📍", df=df,
         descricao="As fábricas entram sozinhas como origem e a revenda como destino.",
         campos=[Campo("nome", "Nome", obrigatorio=True), Campo("cidade", "Cidade"), Campo("uf", "UF"),
                 Campo("tipo", "Tipo", "opcoes", True, TIPOS_OD, padrao=TIPOS_OD[0])],
         salvar=lambda oid, d: (svc.atualizar_od(oid, d["nome"], d.get("cidade"), d.get("uf"), d["tipo"]) if oid
                                else svc.criar_od(operacao_id, d["nome"], d.get("cidade") or "", d.get("uf") or "",
                                                  d["tipo"])),
         excluir=svc.excluir_od)


def _centros_custo() -> None:
    import pandas as pd

    df = pd.DataFrame(cadastros_repo.listar_centros_custo())
    tela(chave="cc", titulo="Centros de custo", icone="🏷️", df=df, por_linha=1,
         campos=[Campo("nome", "Nome do centro de custo", obrigatorio=True)],
         salvar=lambda cid, d: (svc.atualizar_centro_custo(cid, d["nome"]) if cid
                                else svc.criar_centro_custo(d["nome"])),
         excluir=svc.excluir_centro_custo)


def render(usuario: dict, operacao_id: int) -> None:
    try:
        svc.garantir_od_padrao(operacao_id)
    except Exception:
        pass
    with st.container(key="nav_cad_partes"):
        chave = ui._escolha("cad_parte", list(PARTES), "proprio", formatar=PARTES.get, pills=True)
    if chave == "proprio":
        _trechos_proprios(operacao_id)
    elif chave == "spot":
        _trechos_spot(operacao_id)
    elif chave == "fabricas":
        _fabricas()
    elif chave == "carretas":
        _carretas(operacao_id)
    elif chave == "motoristas":
        from modules.puxada import motoristas

        motoristas.render(operacao_id)
    elif chave == "transp":
        _transportadoras()
    elif chave == "od":
        _od(operacao_id)
    else:
        _centros_custo()
