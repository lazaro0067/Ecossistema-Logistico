"""Configurações centrais do Ecossistema Logístico.

Tudo que é constante (caminhos, nomes de módulos, listas de opções)
fica aqui para não se espalhar pelo código.
"""
from pathlib import Path

# --- Fuso horário (o servidor na nuvem roda em UTC) ----------------------
FUSO = "America/Sao_Paulo"

# --- Caminhos -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
import os  # noqa: E402

# ECO_DATA_DIR: o app.py da raiz aponta para uma pasta fixa (o sistema pode rodar de uma cópia temporária)
DATA_DIR = Path(os.environ.get("ECO_DATA_DIR") or BASE_DIR / "data")
ANEXOS_DIR = DATA_DIR / "anexos"
DB_PATH = DATA_DIR / "ecossistema.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
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
        "carreteiro": "🚛 App Carreteiro",
        "tmv_tma": "⏱️ TMV / TMA & Viagens",
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

# Navegação: as abas de cada pasta ficam agrupadas por estrutura (clica no grupo e depois na tela).
# Pasta sem grupo definido (ou com poucas abas) mostra as telas direto.
GRUPOS_ABAS = {
    "puxada": {
        "🚚 Fretes": ["cotacao", "aprovacoes", "encerramento", "painel", "obz"],
        "🚛 Operação": ["carreteiro", "descarga", "vinculos", "pedidos"],
        "📊 Indicadores": ["tmv_tma", "viagens"],
        "⚙️ Cadastros": ["cadastros"],
    },
    "ressuprimento": {
        "📁 Bases": ["bases"],
        "📦 Estoque": ["estoque", "politica"],
        "🛒 Marcação": ["sugestao", "diario"],
        "📈 Acompanhamento": ["cestas", "metas"],
    },
    "vendas": {
        "🛍️ Comercial": ["comercial"],
        "🎯 Metas & ABC": ["metas", "abc"],
        "📥 Importar": ["importar"],
    },
    "armazem": {
        "🏥 Saúde & Estoque": ["saude", "produtos"],
        "📘 Book DPO": ["fundamentos", "manter", "melhorar"],
        "🏗️ Estrutura & Pátio": ["estrutura", "patio"],
    },
    "financeiro": {
        "💳 Contas": ["diario", "contas", "vencimentos"],
        "📊 Caixa & Saúde": ["fluxo", "analise"],
        "📒 OBZ": ["painel", "lancamentos"],
    },
}

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
PERFIL_MOTORISTA = "Motorista"  # entra direto no App Carreteiro (celular)
PERFIS = [PERFIL_MASTER, "Gestor", "Operacional", PERFIL_MOTORISTA]

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


# --- App Carreteiro (motorista aponta cada passo da viagem) -------------
# (chave, botão para o motorista, coluna com a data/hora, ícone, nome curto)
ETAPAS_VIAGEM = [
    ("inicio", "Iniciar viagem", "ts_inicio", "🟢", "Início da viagem"),
    ("apresentado", "Registre sua apresentação", "ts_apresentado", "🙋", "Apresentado"),
    ("chamado", "Chamado para carregar", "ts_chamado", "📣", "Chamado p/ carregar"),
    ("carregado", "Pedido carregado", "ts_carregado", "📦", "Pedido carregado"),
    ("saida", "Saída da cervejaria", "ts_saida_cervejaria", "🏭", "Saída cervejaria"),
    ("chegada", "Chegada na revenda", "ts_chegada_revenda", "🏁", "Chegada revenda"),
    ("fim", "Finalizar viagem", "ts_fim", "✅", "Viagem finalizada"),
]
TOLERANCIA_APRESENTACAO_MIN = 0   # minutos de tolerância após o horário agendado
# endereço publicado do sistema (usado se APP_URL não estiver nos Secrets)
APP_URL_PADRAO = "https://ecossistema-logistico-brlwuspuzz9lxealyzculu.streamlit.app"
RAIO_REVENDA_PADRAO_M = 300       # raio (m) da revenda para validar chegada/saída por GPS
DESFAZER_ETAPA_MIN = 15           # motorista pode desfazer a última etapa até X minutos depois


# --- Armazém / Estoque ----------------------------------------------------
DOI_META_PADRAO = 7.0  # dias
CURVA_ABC_LIMITES = {"A": 80.0, "B": 95.0}  # % acumulado; acima de B = C

# --- Senha padrão do primeiro acesso -------------------------------------
ADMIN_LOGIN = "admin"            # login antigo (o acesso agora é por e-mail)
ADMIN_EMAIL_PADRAO = "admin@grupolima.com.br"  # troque pelo segredo ADMIN_EMAIL
ADMIN_SENHA_INICIAL = "admin123"
