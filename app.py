from datetime import datetime, timedelta
import io
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import pandas as pd
import streamlit as st

# Importação condicional do docx para evitar falhas no Streamlit Cloud
try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# Configuração Inicial da Página & Design System Sênior CSS
st.set_page_config(
    page_title="Gestão DPO & Distribuição - Grupo Lima",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
        .main {
            background-color: #f4f6f9;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        section[data-testid="stSidebar"] {
            background-color: #0d2149;
            color: #ffffff;
        }
        section[data-testid="stSidebar"] p, 
        section[data-testid="stSidebar"] span {
            color: #ffffff !important;
        }
        section[data-testid="stSidebar"] button {
            background-color: #ffffff !important;
            color: #0d2149 !important;
            font-weight: 600 !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 8px !important;
        }
        section[data-testid="stSidebar"] button:hover {
            background-color: #e2e8f0 !important;
            color: #000000 !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"] {
            background-color: #3b82f6 !important;
            color: #ffffff !important;
            border: 1px solid #2563eb !important;
        }
        .senior-card {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            margin-bottom: 16px;
        }
    </style>
""", unsafe_allow_html=True)

DEPARTAMENTOS_DISPONIVEIS = [
    "Visão Geral (Dashboard)",
    "Puxada",
    "Ressuprimento",
    "Vendas",
    "Armazém & Estoque",
    "Distribuição (Entrega)",
    "Frota & Manutenção",
    "Financeiro & OBZ",
    "Compras & Insumos",
    "Gente & SSMA",
    "Relatórios & Bases Globais",
]

OPERACOES_DISPONIVEIS = [
    "Lima Rio Verde",
    "Lima Barreiras",
    "Lima São Félix",
    "Bahia",
]

# Inicialização do Banco de Dados SQLite com Correção de Erros (Safe Columns)
def init_db():
    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS base_01_11 (
        cod_clean INTEGER PRIMARY KEY,
        descricao TEXT,
        fator_hl REAL,
        cx_pallet REAL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS base_linear (
        cod_clean INTEGER PRIMARY KEY,
        tipo TEXT,
        categoria TEXT,
        linear_vendas REAL,
        dt_atualizacao TEXT
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS base_estoque_02 (
        operacao TEXT,
        cod_clean INTEGER,
        descricao TEXT,
        inicial REAL,
        entrada REAL,
        saida REAL,
        disponivel REAL,
        dt_atualizacao TEXT,
        PRIMARY KEY (operacao, cod_clean)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos_marcados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        data_puxada TEXT,
        cod_clean INTEGER,
        descricao TEXT,
        cx_solicitadas REAL,
        cx_marcadas REAL,
        hl_marcado REAL,
        status_item TEXT,
        numero_pedido TEXT,
        dt_atualizacao TEXT
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        email TEXT, 
        cargo TEXT, 
        perfil TEXT CHECK(perfil IN ('Master', 'Operacional')),
        e_aprovador TEXT DEFAULT 'Não', 
        alcada_reais REAL DEFAULT 0.0,
        permissoes_operacoes TEXT DEFAULT 'TODAS',
        permissoes_deptos TEXT DEFAULT 'TODOS',
        status TEXT DEFAULT 'Ativo'
    )""")

    cursor.execute("SELECT count(*) FROM usuarios WHERE nome = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO usuarios (nome, senha, email, cargo, perfil, e_aprovador, alcada_reais, permissoes_operacoes, permissoes_deptos, status)
        VALUES ('admin', 'admin123', 'admin@grupolima.com.br', 'Administrador Master', 'Master', 'Sim', 9999999.0, 'TODAS', 'TODOS', 'Ativo')
        """)

    conn.commit()
    conn.close()

init_db()

# Funções Auxiliares Robustas de Leitura e Formatação
def robust_read_file(file_obj):
    filename = str(file_obj.name).lower()
    if filename.endswith((".xlsx", ".xls")):
        for h in [0, 1, 2, 3, 4, 5]:
            try:
                file_obj.seek(0)
                df = pd.read_excel(file_obj, header=h, engine="openpyxl")
                if df is not None and not df.empty and len(df.columns) > 1:
                    return df.dropna(how="all", axis=1)
            except Exception:
                continue
    file_obj.seek(0)
    return pd.read_excel(file_obj)

def parse_br_float(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).strip()
    if not s: return 0.0
    s = re.sub(r"[R\$\s]", "", s)
    if "." in s and "," in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s: s = s.replace(",", ".")
    try: return float(s)
    except Exception: return 0.0

def formatar_br(val):
    try:
        if pd.isna(val): return "0,00"
        val_float = float(val)
        s_base = f"{val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if s_base.endswith(",00"): s_base = s_base[:-3]
        return s_base
    except Exception:
        return str(val)

def carregar_estoque_consolidado(operacao):
    conn = sqlite3.connect("puxada_ambev.db")
    ops_filtro = [operacao]
    if operacao == "Bahia":
        ops_filtro = ["Lima Barreiras", "Lima São Félix"]

    placeholders = ",".join(["?"] * len(ops_filtro))
    query = f"""
    SELECT 
        e.cod_clean AS cod_clean,
        COALESCE(e.descricao, b_01.descricao, 'PRODUTO') AS descricao,
        COALESCE(l.tipo, 'OUTROS') AS tipo,
        COALESCE(l.categoria, 'OUTROS') AS categoria,
        CAST(COALESCE(e.inicial, 0) AS INTEGER) AS inicial,
        CAST(COALESCE(e.entrada, 0) AS INTEGER) AS entrada,
        CAST(COALESCE(e.saida, 0) AS INTEGER) AS saida,
        CAST(COALESCE(e.disponivel, 0) AS INTEGER) AS disp,
        CAST(COALESCE(l.linear_vendas, 0) AS INTEGER) AS linear_vendas,
        COALESCE(b_01.fator_hl, 0.0) AS fator_hl,
        COALESCE(b_01.cx_pallet, 1.0) AS cx_pallet,
        e.dt_atualizacao AS dt_atualizacao
    FROM base_estoque_02 e
    LEFT JOIN base_01_11 b_01 ON e.cod_clean = b_01.cod_clean
    LEFT JOIN base_linear l ON e.cod_clean = l.cod_clean
    WHERE e.operacao IN ({placeholders})
    """
    df = pd.read_sql_query(query, conn, params=ops_filtro)
    
    query_marc = f"""
    SELECT cod_clean, data_puxada, SUM(cx_marcadas) as cx_marcadas
    FROM pedidos_marcados
    WHERE operacao IN ({placeholders})
    GROUP BY cod_clean, data_puxada
    """
    df_marc = pd.read_sql_query(query_marc, conn, params=ops_filtro)
    conn.close()

    if df.empty: return None
    df.columns = [str(c).lower() for c in df.columns]

    # Correção do erro KeyError garantindo a criação das colunas d0, d1 e d2 com segurança
    df["d0"] = 0.0
    df["d1"] = 0.0
    df["d2"] = 0.0

    if not df_marc.empty and "data_puxada" in df_marc.columns:
        datas_pux = sorted(df_marc["data_puxada"].dropna().unique())
        for idx_d, d_val in enumerate(datas_pux[:3]):
            col_nome = f"d{idx_d}"
            df_d = df_marc[df_marc["data_puxada"] == d_val].groupby("cod_clean")["cx_marcadas"].sum().reset_index()
            df = pd.merge(df, df_d.rename(columns={"cx_marcadas": col_nome}), on="cod_clean", how="left")
            df[col_nome] = df[col_nome].fillna(0)

    df["total_puxada"] = df["d0"] + df["d1"] + df["d2"]
    df["estoque_projetado"] = df["disp"] + df["total_puxada"]
    df["doi_atual"] = df.apply(lambda r: round(r["disp"] / r["linear_vendas"], 1) if r["linear_vendas"] > 0 else (999.0 if r["disp"] > 0 else 0.0), axis=1)
    return df
