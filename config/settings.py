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
        "cotacao": "📝 Nova Cotação",
        "aprovacoes": "✅ Aprovações",
        "painel": "📋 Painel de Fretes",
        "encerramento": "📄 Encerramento (NF/CT-e)",
        "obz": "📊 OBZ (Real x Meta)",
        "pedidos": "📦 Pedidos Marcados",
        "cadastros": "⚙️ Cadastros",
    }},
    "ressuprimento": {"rotulo": "Ressuprimento", "icone": "🔄", "abas": {
        "bases": "📁 Cadastros & Atualização de Bases",
        "estoque": "📊 Gestão de Estoque",
        "sugestao": "🛒 Sugestão de Compra & Marcação por Dia",
        "cestas": "📈 Gestão Ressuprimento (Cestas & Metas)",
    }},
    "armazem": {"rotulo": "Armazém", "icone": "📦", "abas": {
        "ocupacao": "📊 Ocupação & Capacidade",
        "estrutura": "🏗️ Estrutura Física",
        "produtos": "🔎 Catálogo de Produtos",
    }},
    "distribuicao": {"rotulo": "Distribuição", "icone": "🚛", "abas": dict(_ABAS_REGISTRO)},
    "frota": {"rotulo": "Segurança & Frota", "icone": "🛡️", "abas": dict(_ABAS_REGISTRO)},
    "gente": {"rotulo": "Gente & Gestão", "icone": "👥", "abas": dict(_ABAS_REGISTRO)},
    "vendas": {"rotulo": "Vendas", "icone": "📈", "abas": {
        "abc": "🔤 Curva ABC",
        "importar": "📥 Importar Vendas",
    }},
    "financeiro": {"rotulo": "Financeiro", "icone": "💰", "abas": dict(_ABAS_REGISTRO)},
    "compras": {"rotulo": "Compras", "icone": "🛒", "abas": dict(_ABAS_REGISTRO)},
}
MODULO_ADMIN = "admin"

# --- Perfis ---------------------------------------------------------------
PERFIL_MASTER = "Master"
PERFIS = [PERFIL_MASTER, "Gestor", "Operacional"]

# --- Puxada / Fretes ------------------------------------------------------
TIPOS_OD = ["Origem e destino", "Apenas Origem", "Apenas Destino"]
MOTIVOS_FRETE = ["Pedido Descartável", "Vasilhame", "Emergência", "Transferência", "Outros"]


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
ADMIN_LOGIN = "admin"
ADMIN_SENHA_INICIAL = "admin123"
