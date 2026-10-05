"""Relatórios & Bases — download de qualquer base do sistema e histórico de atualizações."""
import streamlit as st

from core import tema, ui
from core.auth import e_master
from database.connection import query_df
from repositories import operacoes_repo

TABELAS = {
    "produtos": "Produtos (01.11)", "estoque": "Estoque (02.03.04)", "linear_vendas": "Linear de vendas",
    "metas_doi": "Metas de DOI", "pedidos_marcados": "Pedidos marcados", "ressuprimento_diario": "Ressuprimento diário",
    "metas_ressuprimento": "Metas de ressuprimento", "politica_estoque": "Política de estoque",
    "curva_abc": "Curva ABC", "cotacoes_frete": "Fretes (cotações)", "trechos": "Trechos de frete",
    "transportadoras": "Transportadoras", "carretas": "Carretas", "fabricas": "Fábricas", "motoristas": "Motoristas",
    "agendamentos_descarga": "Agendamentos de descarga", "vinculos_pedidos": "Pedidos vinculados & NFs",
    "metas_obz": "Metas OBZ frete", "contas_pagar": "Contas a pagar", "fluxo_caixa": "Fluxo de caixa (lançamentos)",
    "financeiro_obz": "OBZ por pacote", "metas_vendas": "Metas de vendas", "padroes_dpo": "Padrões DPO",
    "distribuicao_rotas": "Rotas", "frota_manutencao": "Manutenção da frota", "gente_ssma": "Gente & SSMA",
    "compras_pedidos": "Pedidos de compra", "armazens": "Armazéns", "operacoes": "Operações",
}
SEM_OPERACAO = {"produtos", "transportadoras", "fabricas", "operacoes"}


def aba_tabelas(usuario: dict, operacao_id: int) -> None:
    c1, c2 = st.columns([2, 1])
    tabela = c1.selectbox("Base", list(TABELAS), format_func=TABELAS.get, key="rel_tab")
    todas = c2.toggle("Todas as filiais", value=False, key="rel_todas", disabled=not e_master(usuario)
                      or tabela in SEM_OPERACAO)
    if tabela in SEM_OPERACAO or todas:
        df = query_df(f"SELECT * FROM {tabela} ORDER BY 1 DESC LIMIT 50000")
    else:
        f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
        df = query_df(f"SELECT * FROM {tabela} WHERE {f_sql} ORDER BY 1 DESC LIMIT 50000", ids)
    st.caption(f"{len(df)} linha(s)" + (" (limite de 50 mil)" if len(df) == 50000 else ""))
    ui.tabela(df.head(1000))
    ui.downloads(df, f"base_{tabela}", key=f"dl_rel_{tabela}")


def aba_historico(usuario: dict, operacao_id: int) -> None:
    tema.secao("Histórico de atualizações de bases", "Quem enviou cada arquivo e quando.")
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT dt, base, linhas, arquivo, usuario FROM bases_log WHERE {f_sql} OR operacao_id IS NULL "
                  "ORDER BY dt DESC LIMIT 500", ids)
    ui.tabela(df, vazio="Nenhuma atualização registrada ainda.")
    ui.downloads(df, "historico_bases", key="dl_hist")


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("relatorios")
    ui.abas_modulo(usuario, "relatorios", {"tabelas": aba_tabelas, "historico": aba_historico}, usuario, operacao_id)
