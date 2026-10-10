"""Módulo Frota & Manutenção.

• 📊 Gestão da Frota: aberta por revenda (clique na revenda e abre a gestão completa) e Grupo Lima.
• ⚙️ Cadastros: placas (revenda, proprietário, aluguel/locadora, área, motorista), motoristas,
  transportadoras e locadoras.
• 🔧 Manutenção: painel e lançamentos de serviços (como antes).
"""
import pandas as pd
import streamlit as st

from config.settings import CATEGORIAS_CNH, STATUS_PLACA, TIPOS_VEICULO
from core import graficos, tema, ui
from core.auth import operacoes_permitidas
from modules.componentes.cadastro import Campo as CampoCad
from modules.componentes.cadastro import tela
from modules.componentes.registro_generico import Campo, Grafico, Indicador, tela_registros
from repositories import frota_repo as repo
from repositories import motoristas_repo, operacoes_repo
from services import frota_service as svc

CAMPOS = [
    Campo("data", "Data", "data"),
    Campo("placa", "Placa", obrigatorio=True),
    Campo("tipo_servico", "Tipo de serviço", "opcao",
          ["Preventiva", "Corretiva", "Pneus", "Elétrica", "Funilaria", "Outros"]),
    Campo("valor", "Valor (R$)", "numero"),
    Campo("km_atual", "KM atual", "inteiro"),
    Campo("status", "Status", "opcao", ["Finalizado", "Em andamento", "Agendado"]),
]

INDICADORES = [
    Indicador("Serviços", len, icone="🔧"),
    Indicador("Custo total", lambda d: d["valor"].sum(), ui.moeda, "💸"),
    Indicador("Veículos atendidos", lambda d: d["placa"].nunique(), icone="🚛"),
    Indicador("Corretivas", lambda d: (d["tipo_servico"] == "Corretiva").sum(), icone="⚠️",
              status=lambda v: "bom" if v == 0 else "atencao" if v < 5 else "critico"),
]

GRAFICOS = [
    Grafico("Custo por placa (R$)", "placa", "valor"),
    Grafico("Custo por tipo de serviço (R$)", "tipo_servico", "valor"),
]


def _revendas(usuario: dict) -> dict[int, str]:
    permitidas = [o["id"] for o in operacoes_permitidas(usuario)]
    ids = set()
    for i in permitidas:
        ids |= set(operacoes_repo.ids_efetivos(i))
    return svc.revendas(sorted(ids))


# --- Gestão -----------------------------------------------------------------------------------
def _gestao(usuario: dict) -> None:
    revs = _revendas(usuario)
    todas = repo.placas_df(list(revs))
    sel_k = "frota_rev_sel"
    cards = []
    for rid, nome in revs.items():
        r = svc.resumo(todas[todas["operacao_id"] == rid] if not todas.empty else todas)
        cards.append({"titulo": nome, "valor": f"{r['total']} placa(s)", "icone": "🏢",
                      "detalhe": f"✅ {r['ativas']} ativas · 🔧 {r['manut']} manut. · 🔑 {r['alugadas']} alugadas",
                      "status": "critico" if r["cnh"] or r["sem_motorista"] > r["total"] / 2 and r["total"] else "info",
                      "selo": "aberta" if st.session_state.get(sel_k) == rid else None, "ver": "abrir gestão",
                      "ao_clicar": (lambda rid=rid: _abrir(sel_k, rid))})
    if len(revs) > 1:
        r = svc.resumo(todas)
        cards.append({"titulo": "🌐 Grupo Lima", "valor": f"{r['total']} placa(s)", "icone": "",
                      "detalhe": f"{len(revs)} revendas · 🔑 {r['alugadas']} alugadas · {r['proprias']} sem aluguel",
                      "status": "info", "selo": "aberta" if st.session_state.get(sel_k) == "todas" else None,
                      "ver": "abrir gestão", "ao_clicar": lambda: _abrir(sel_k, "todas")})
    tema.secao("Frota por revenda", "Clique na revenda para abrir a gestão completa.")
    tema.kpis(cards, key="kp_frota_rev")
    sel = st.session_state.get(sel_k)
    if sel is None:
        if todas.empty:
            st.info("Cadastre as placas em **⚙️ Cadastros › 🚚 Cadastro de Placas**.")
        return
    df = todas if sel == "todas" else todas[todas["operacao_id"] == sel]
    nome = "Grupo Lima" if sel == "todas" else revs.get(sel, "")
    _abertura(nome, df)


def _abrir(chave: str, valor) -> None:
    st.session_state[chave] = None if st.session_state.get(chave) == valor else valor
    st.rerun()


def _abertura(nome: str, df: pd.DataFrame) -> None:
    tema.secao(f"📊 Gestão completa · {nome}")
    if df.empty:
        st.info("Nenhuma placa cadastrada nesta revenda.")
        return
    r = svc.resumo(df)
    vis = svc.tabela(df)
    alug = pd.to_numeric(df["aluguel"], errors="coerce").fillna(0) == 1
    cnh = df["motorista_cnh_validade"].map(svc._cnh_dias)
    tema.kpis([
        {"titulo": "Placas", "valor": r["total"], "icone": "🚚", "status": "info", "dados": vis},
        {"titulo": "Ativas", "valor": r["ativas"], "icone": "✅", "status": "bom",
         "dados": vis[df["status"].fillna("Ativo").values == "Ativo"]},
        {"titulo": "Em manutenção", "valor": r["manut"], "icone": "🔧",
         "status": "atencao" if r["manut"] else "bom", "dados": vis[df["status"].values == "Em manutenção"]},
        {"titulo": "Alugadas", "valor": r["alugadas"], "icone": "🔑", "status": "info",
         "detalhe": f"{r['proprias']} sem aluguel", "dados": vis[alug.values]},
        {"titulo": "Sem motorista", "valor": r["sem_motorista"], "icone": "👤",
         "status": "atencao" if r["sem_motorista"] else "bom", "dados": vis[df["motorista_id"].isna().values]},
        {"titulo": "CNH vence em 30 dias", "valor": r["cnh"], "icone": "🪪",
         "status": "critico" if r["cnh"] else "bom",
         "dados": vis[[d is not None and d <= 30 for d in cnh]]},
    ], key=f"kp_frota_ab_{nome}")
    g1, g2 = st.columns(2)
    for col, campo, titulo in ((g1, "area", "Placas por área"), (g2, "tipo", "Placas por tipo")):
        cont = df[campo].fillna("—").value_counts()
        with col:
            graficos.mostrar(graficos.barras_h(cont.index, cont.values, titulo=titulo), key=f"g_fr_{campo}_{nome}",
                             detalhe=(vis.assign(_g=df[campo].fillna("—").values), "_g"), titulo=titulo)
    g3, g4 = st.columns(2)
    dono = df["proprietario"].fillna("—").value_counts()
    loc = df[alug]["locadora"].fillna("—").value_counts()
    with g3:
        st.markdown("**🏢 Por proprietário**")
        ui.tabela(pd.DataFrame({"Proprietário": dono.index, "Placas": dono.values}), baixar=False)
    with g4:
        st.markdown("**🔑 Alugadas por locadora**")
        ui.tabela(pd.DataFrame({"Locadora": loc.index, "Placas": loc.values}), baixar=False,
                  vazio="Nenhuma placa alugada.")
    st.markdown("**📋 Todas as placas**")
    ui.tabela(vis, baixar=f"frota_{nome}")


# --- Cadastros --------------------------------------------------------------------------------
def _placas(usuario: dict) -> None:
    revs = _revendas(usuario)
    if not revs:
        st.info("Nenhuma revenda disponível.")
        return
    filtro = st.pills("Revenda", ["Todas"] + list(revs), key="fr_pl_rev", selection_mode="single", default="Todas",
                      format_func=lambda i: "Todas" if i == "Todas" else revs[i]) or "Todas"
    df = repo.placas_df(list(revs) if filtro == "Todas" else [filtro])
    transp = {int(r["id"]): r["nome"] for r in repo.transportadoras_df().to_dict("records")}
    locs = {int(r["id"]): r["nome"] for r in repo.locadoras_df().to_dict("records")}
    mots_df = repo.motoristas_df(list(revs))
    mots = {int(r["id"]): f"{r['nome']} · {r['revenda']}" for r in mots_df.to_dict("records")} if not mots_df.empty else {}
    if not transp:
        st.warning("Cadastre os proprietários em **🏢 Transportadoras** antes (o proprietário vem de lá).")
    if not df.empty:
        df["aluguel_txt"] = ["Sim" if a == a and a and int(a) == 1 else "Não" for a in df["aluguel"]]
    tela(chave="fr_placas", titulo="Placas", icone="🚚", df=df, por_linha=3,
         descricao="Proprietário vem das transportadoras · aluguel Sim/Não (escolha a locadora) · revenda · "
                   "área onde a placa trabalha · motorista do cadastro.",
         campos=[CampoCad("placa", "Placa", obrigatorio=True),
                 CampoCad("operacao_id", "Revenda", "opcoes", True, revs),
                 CampoCad("tipo", "Tipo de veículo", "opcoes", True, TIPOS_VEICULO),
                 CampoCad("marca_modelo", "Marca / modelo"),
                 CampoCad("ano", "Ano", "inteiro", na_tabela=False),
                 CampoCad("proprietario_id", "Proprietário (transportadora)", "opcoes", False, transp),
                 CampoCad("aluguel", "Aluguel?", "opcoes", True, {0: "Não", 1: "Sim"}, padrao=0, na_tabela=False),
                 CampoCad("locadora_id", "Locadora (se alugada)", "opcoes", False, locs),
                 CampoCad("area", "Área alocada", "opcoes", False, svc.AREAS),
                 CampoCad("motorista_id", "Motorista", "opcoes", False, mots),
                 CampoCad("status", "Status", "opcoes", True, STATUS_PLACA, padrao="Ativo"),
                 CampoCad("observacao", "Observação", na_tabela=False)],
         colunas_extras=[("aluguel_txt", "Alugada")],
         rotulo_registro=lambda r: f"{r['placa']} · {revs.get(int(r['operacao_id']), '') if r.get('operacao_id') == r.get('operacao_id') and r.get('operacao_id') else ''}",
         salvar=lambda pid, d: svc.salvar_placa(pid, d, usuario.get("nome") or ""),
         excluir=repo.excluir_placa, aviso_vazio="Nenhuma placa cadastrada.")


def _motoristas(usuario: dict) -> None:
    revs = _revendas(usuario)
    df = repo.motoristas_df(list(revs))
    sup = {int(g["id"]): g["nome"] for g in motoristas_repo.gestores()}
    tela(chave="fr_mot", titulo="Motoristas", icone="👤", df=df, por_linha=3,
         descricao="Nome, CPF, CNH (número, categoria e validade), supervisor e revenda. O mesmo cadastro da Puxada.",
         campos=[CampoCad("nome", "Nome", obrigatorio=True), CampoCad("cpf", "CPF"),
                 CampoCad("cnh", "Nº CNH"), CampoCad("categoria_cnh", "Categoria CNH", "opcoes", False, CATEGORIAS_CNH),
                 CampoCad("cnh_validade", "Validade CNH", "data"), CampoCad("telefone", "Celular", na_tabela=False),
                 CampoCad("gestor_id", "Supervisor", "opcoes", False, sup),
                 CampoCad("operacao_id", "Revenda", "opcoes", True, revs)],
         colunas_extras=[("placas", "Placas")],
         rotulo_registro=lambda r: f"{r['nome']} · {r.get('revenda') or ''}",
         salvar=svc.salvar_motorista, aviso_vazio="Nenhum motorista cadastrado.")


def _empresas(tipo: str) -> None:
    df = repo.locadoras_df() if tipo == "locadora" else repo.transportadoras_df()
    titulo = "Locadoras" if tipo == "locadora" else "Transportadoras / proprietários"
    tela(chave=f"fr_{tipo}", titulo=titulo, icone="🔑" if tipo == "locadora" else "🏢", df=df, por_linha=4,
         descricao=("Empresas de aluguel das placas." if tipo == "locadora"
                    else "Proprietários das placas e transportadoras do frete spot (o mesmo cadastro)."),
         campos=[CampoCad("nome", "Nome", obrigatorio=True), CampoCad("cnpj", "CNPJ"), CampoCad("contato", "Contato"),
                 CampoCad("telefone", "Telefone")],
         colunas_extras=[("placas", "Placas")], rotulo_registro=lambda r: r["nome"],
         salvar=lambda eid, d: svc.salvar_empresa(tipo, eid, d),
         excluir=repo.excluir_locadora if tipo == "locadora" else svc.excluir_transportadora)


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("frota")
    tela_registros(modulo="frota", usuario=usuario, tabela="frota_manutencao", operacao_id=operacao_id,
                   campos=CAMPOS, indicadores=INDICADORES, graficos_=GRAFICOS,
                   extras={"gestao": lambda *_: _gestao(usuario), "placas": lambda *_: _placas(usuario),
                           "motoristas": lambda *_: _motoristas(usuario),
                           "transportadoras": lambda *_: _empresas("transportadora"),
                           "locadoras": lambda *_: _empresas("locadora")})
