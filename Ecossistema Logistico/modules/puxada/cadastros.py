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


def _centros_custo(operacao_id: int) -> None:
    import pandas as pd

    from core import tema
    from modules.componentes.autosave import editor_autosave

    mes_atual = ui.mes_atual()

    def salvar(cid, d):
        if cid:
            svc.atualizar_centro_custo(cid, d["nome"])
        else:
            svc.criar_centro_custo(d["nome"])
            cid = next(c["id"] for c in cadastros_repo.listar_centros_custo() if c["nome"] == d["nome"].strip())
        if d.get("meta") is not None:
            cadastros_repo.salvar_meta_centro_custo(operacao_id, int(cid), mes_atual, float(d["meta"] or 0))

    df = cadastros_repo.metas_centro_custo_df(operacao_id, mes_atual)
    tela(chave="cc", titulo="Centros de custo", icone="🏷️", df=df, por_linha=2,
         descricao=f"A coluna Meta é a de {ui.nome_mes(mes_atual)}. Os outros meses ficam em 🎯 Metas por mês, abaixo.",
         campos=[Campo("nome", "Nome do centro de custo", obrigatorio=True),
                 Campo("meta", f"Meta de {ui.nome_mes(mes_atual)} (R$)", "moeda", passo=500),
                 Campo("realizado", "Realizado no mês (R$)", "moeda", no_form=False)],
         salvar=salvar, excluir=svc.excluir_centro_custo)

    tema.secao("🎯 Metas por mês", "Meta de gasto de frete spot por centro de custo. Realizado = fretes aprovados e "
               "finalizados do mês com esse centro de custo. Edite a meta direto na tabela — salva sozinho.")
    meses = sorted({mes_atual} | {f"{int(mes_atual[:4]) + (int(mes_atual[5:]) + i - 1) // 12}-"
                                  f"{(int(mes_atual[5:]) + i - 1) % 12 + 1:02d}" for i in range(-6, 7)}, reverse=True)
    c1, c2 = st.columns([1, 2])
    mes = c1.selectbox("Mês", meses, index=meses.index(mes_atual), format_func=ui.nome_mes, key="cc_meta_mes")
    tab = cadastros_repo.metas_centro_custo_df(operacao_id, mes)
    if tab.empty:
        st.info("Cadastre um centro de custo acima para lançar as metas.")
        return
    ano, m = int(mes[:4]), int(mes[5:])
    anterior = f"{ano - 1}-12" if m == 1 else f"{ano}-{m - 1:02d}"
    if c2.button(f"📋 Copiar as metas de {ui.nome_mes(anterior)}", key="cc_copiar"):
        for r in cadastros_repo.metas_centro_custo_df(operacao_id, anterior).to_dict("records"):
            if r["meta"]:
                cadastros_repo.salvar_meta_centro_custo(operacao_id, int(r["id"]), mes, float(r["meta"]))
        ui.avisar("Metas copiadas.")
        st.rerun()
    meta, real = float(tab["meta"].sum()), float(tab["realizado"].sum())
    tab["ating"] = (tab["realizado"] / tab["meta"].where(tab["meta"] > 0) * 100).round(1)
    tab["saldo"] = tab["meta"] - tab["realizado"]
    acima = tab[tab["realizado"] > tab["meta"].where(tab["meta"] > 0)]
    tema.kpis([
        {"titulo": f"Meta de {ui.nome_mes(mes)}", "valor": ui.moeda(meta), "icone": "🎯", "status": "info"},
        {"titulo": "Realizado", "valor": ui.moeda(real), "icone": "💸",
         "status": tema.status_atingimento(real / meta * 100, invertido=True) if meta else "neutro",
         "detalhe": f"{ui.pct(real / meta * 100)} da meta" if meta else "sem meta"},
        {"titulo": "Saldo", "valor": ui.moeda(meta - real), "icone": "💰",
         "status": ("bom" if meta >= real else "critico") if meta else "neutro"},
        {"titulo": "Centros acima da meta", "valor": len(acima), "icone": "🔺",
         "status": "critico" if len(acima) else "bom", "dados": acima[["nome", "meta", "realizado", "saldo"]]},
    ], key=f"kp_cc_{mes}")

    def alterar(linha, alt):
        if "meta" in alt:
            cadastros_repo.salvar_meta_centro_custo(operacao_id, int(linha["id"]), mes, float(alt["meta"] or 0))

    editor_autosave(tab, f"ed_cc_meta_{operacao_id}_{mes}", ["meta"], alterar, column_config={
        "id": None, "nome": "Centro de custo",
        "meta": st.column_config.NumberColumn("Meta ✏️", format="R$ %.2f", min_value=0),
        "realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
        "ating": st.column_config.ProgressColumn("Atingido", format="%.0f%%", min_value=0, max_value=120),
        "saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f")})


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
        _centros_custo(operacao_id)
