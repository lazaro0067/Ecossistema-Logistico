"""Configurações centrais do Ecossistema Logístico.

Tudo que é constante (caminhos, nomes de módulos, listas de opções)
fica aqui para não se espalhar pelo código.
"""
from pathlib import Path

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

# --- Módulos do sistema ---------------------------------------------------
# chave interna -> (rótulo no menu, ícone)
MODULOS = {
    "puxada": ("Puxada", "🚚"),
    "ressuprimento": ("Ressuprimento", "🔄"),
    "armazem": ("Armazém", "📦"),
    "distribuicao": ("Distribuição", "🚛"),
    "frota": ("Segurança & Frota", "🛡️"),
    "gente": ("Gente & Gestão", "👥"),
    "vendas": ("Vendas", "📈"),
    "financeiro": ("Financeiro", "💰"),
    "compras": ("Compras", "🛒"),
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
