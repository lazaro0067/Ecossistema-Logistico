"""Configurações centrais do Ecossistema Logístico.

Tudo que é constante (caminhos, nomes de módulos, listas de opções)
fica aqui para não se espalhar pelo código.
"""
from pathlib import Path

# --- Fuso horário (o servidor na nuvem roda em UTC) ----------------------
FUSO = "America/Sao_Paulo"

# --- Caminhos -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ANEXOS_DIR = DATA_DIR / "anexos"
DB_PATH = DATA_DIR / "ecossistema.db"

DATA_DIR.mkdir(exist_ok=True)
ANEXOS_DIR.mkdir(exist_ok=True)

# --- Identidade -----------------------------------------------------------
APP_TITULO = "Ecossistema Logístico"
APP_SUBTITULO = "Revenda Ambev"
APP_ICONE = "🌐"
APP_EMPRESA = "Grupo Lima"

# --- Módulos (pastas) e abas (subpastas) ---------------------------------
# A permissão de cada usuário é dada por pasta inteira ("puxada") ou por aba
# ("puxada.aprovacoes"). O Master enxerga tudo.
_ABAS_REGISTRO = {"painel": "📊 Painel", "lancamentos": "➕ Lançamentos"}

MODULOS = {
    "puxada": {"rotulo": "Puxada", "icone": "🚚", "abas": {
        "cotacao": "📝 Solicitar Frete",
        "aprovacoes": "✅ Aprovações",
        "encerramento": "🏁 Finalizar (CT-e/NFs)",
        "painel": "📋 Painel & Histórico",
        "obz": "📊 OBZ Frete",
        "descarga": "🅿️ Descarga (Pátio)",
        "vinculos": "🔗 Vincular Pedido & NFs",
        "viagens": "📅 Viagens do Mês",
        "pedidos": "📦 Pedidos Marcados",
        "cadastros": "⚙️ Cadastros",
    }},
    "ressuprimento": {"rotulo": "Ressuprimento", "icone": "🔄", "abas": {
        "bases": "📁 Atualização de Bases",
        "estoque": "📊 Gestão de Estoque",
        "sugestao": "🛒 Sugestão & Marcação por Dia",
        "cestas": "📈 Acompanhamento (Cestas)",
        "diario": "📅 Carregamento Dia a Dia",
        "politica": "📦 Política de Estoque",
        "metas": "🎯 Metas Mensais",
    }},
    "vendas": {"rotulo": "Vendas", "icone": "📈", "abas": {
        "comercial": "🛍️ Estoque do Dia (Portal RN)",
        "metas": "🎯 Metas de Vendas",
        "abc": "🔤 Curva ABC",
        "importar": "📥 Importar Vendas",
    }},
    "armazem": {"rotulo": "Armazém & Estoque", "icone": "📦", "abas": {
        "saude": "🏥 Saúde & Ocupação",
        "fundamentos": "📘 Fundamentos (DPO)",
        "manter": "🔄 Gerenciar para Manter",
        "melhorar": "🚀 Gerenciar para Melhorar",
        "patio": "🅿️ Pátio / Descarga",
        "estrutura": "🏗️ Capacidade & Áreas",
        "produtos": "🔎 Catálogo de Produtos",
    }},
    "distribuicao": {"rotulo": "Distribuição (Entrega)", "icone": "🚛", "abas": {
        "book": "📘 Book DPO Entrega",
        **_ABAS_REGISTRO,
    }},
    "frota": {"rotulo": "Frota & Manutenção", "icone": "🔧", "abas": dict(_ABAS_REGISTRO)},
    "financeiro": {"rotulo": "Financeiro & OBZ", "icone": "💰", "abas": {
        "diario": "📂 Relatório Diário",
        "contas": "💳 Contas a Pagar",
        "vencimentos": "⏳ Vencimentos",
        "fluxo": "📊 Fluxo de Caixa",
        "analise": "🩺 Saúde Financeira",
        "painel": "📒 OBZ por Pacote",
        "lancamentos": "➕ Lançar OBZ",
    }},
    "compras": {"rotulo": "Compras & Insumos", "icone": "🛒", "abas": dict(_ABAS_REGISTRO)},
    "gente": {"rotulo": "Gente & SSMA", "icone": "👥", "abas": dict(_ABAS_REGISTRO)},
    "relatorios": {"rotulo": "Relatórios & Bases", "icone": "📁", "abas": {
        "tabelas": "🗃️ Bases para Download",
        "historico": "🕒 Histórico de Atualizações",
    }},
}
MODULO_ADMIN = "admin"

# --- Operações (filiais) criadas no primeiro acesso ----------------------
OPERACOES_PADRAO = [
    ("Lima Rio Verde", "12.345.678/0001-90", "Rio Verde", "GO"),
    ("Lima Barreiras", "98.765.432/0001-10", "Barreiras", "BA"),
    ("Lima São Félix", "45.678.912/0001-33", "São Félix do Coribe", "BA"),
]
# Visões consolidadas (somente leitura): nome -> filiais que somam
OPERACOES_CONSOLIDADAS = {"Bahia (Barreiras + São Félix)": ["Lima Barreiras", "Lima São Félix"]}
# Como cada filial aparece escrita nos relatórios Ambev (para importar arquivos com várias filiais)
APELIDOS_OPERACAO = {
    "Lima Rio Verde": ["rio verde"],
    "Lima Barreiras": ["barreiras", "lima bahia"],
    "Lima São Félix": ["lima bahia samavi", "samavi", "sao felix", "são félix"],
}

# --- Ressuprimento: nomes amigáveis das cestas (ordem de exibição) --------
CESTAS = {
    "CATEGORIA_AGRUPADO - CERVEJA": "Cerveja",
    "CATEGORIA_AGRUPADO - NAB": "Nab",
    "CATEGORIA - MATCH": "Match",
    "CATEGORIA_RETORNAVEL - CERVEJA RGB": "Cerveja RGB",
    "REFRIGERANTE_REGULAR_NAB - ZERO": "Nab Zero",
    "CERV_2 - Zero Alcool": "Cerveja Zero Álcool",
    "SEGMENTO - HIGH END": "High End",
}
CESTAS_TOTAL = ["CATEGORIA_AGRUPADO - CERVEJA", "CATEGORIA_AGRUPADO - NAB"]  # linha "Total (Cerveja + Nab)"

# --- Perfis ---------------------------------------------------------------
PERFIL_MASTER = "Master"
PERFIS = [PERFIL_MASTER, "Gestor", "Operacional"]

# --- Puxada / Fretes ------------------------------------------------------
TIPOS_OD = ["Origem e destino", "Apenas Origem", "Apenas Destino"]
MOTIVOS_FRETE = ["Regular", "Aumento de Demanda", "Emergencial", "Pedido Descartável", "Vasilhame", "Transferência", "Outros"]


class StatusFrete:
    PENDENTE = "Pendente Aprovação"
    APROVADO = "Aprovado"
    REJEITADO = "Rejeitado"
    FINALIZADO = "Finalizado"
    CANCELADO = "Cancelado"

    TODOS = [PENDENTE, APROVADO, REJEITADO, FINALIZADO, CANCELADO]
    COMPROMETIDOS = [APROVADO, FINALIZADO]  # entram no realizado do OBZ


# --- Armazém / Estoque ----------------------------------------------------
DOI_META_PADRAO = 7.0  # dias
CURVA_ABC_LIMITES = {"A": 80.0, "B": 95.0}  # % acumulado; acima de B = C

# --- Senha padrão do primeiro acesso -------------------------------------
ADMIN_LOGIN = "admin"            # login antigo (o acesso agora é por e-mail)
ADMIN_EMAIL_PADRAO = "admin@grupolima.com.br"  # troque pelo segredo ADMIN_EMAIL
ADMIN_SENHA_INICIAL = "admin123"
