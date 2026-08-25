from datetime import datetime, timedelta
import io
import re
import sqlite3
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import pandas as pd
import streamlit as st

# Importação condicional do docx para evitar falha no Streamlit Cloud caso falte a biblioteca
try:
    import docx

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# 1. Configuração Inicial da Página
st.set_page_config(
    page_title="Gestão DPO & Distribuição - Grupo Lima",
    layout="wide",
    initial_sidebar_state="expanded",
)

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


# 2. Inicialização do Banco de Dados SQLite
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
    CREATE TABLE IF NOT EXISTS agendamentos_descarga (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        placa TEXT,
        slot TEXT,
        data_descarga TEXT,
        tipo_carga TEXT,
        observacao TEXT,
        dt_atualizacao TEXT
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        cnpj TEXT, cidade TEXT, uf TEXT
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
        permissoes_deptos TEXT DEFAULT 'TODOS'
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS padroes_dpo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        modulo TEXT,
        subbloco TEXT,
        titulo_padrao TEXT,
        conteudo_padrao TEXT,
        sugestoes_ia TEXT,
        dt_atualizacao TEXT,
        UNIQUE(operacao, modulo, subbloco)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metas_doi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT, cod_prod INTEGER, doi_meta REAL DEFAULT 7.0,
        UNIQUE(operacao, cod_prod)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cotacoes_frete (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT, origem TEXT, destino TEXT, data_requisicao TEXT,
        data_frete TEXT, motivo TEXT, transportadora TEXT, valor_negociado REAL,
        centro_custo TEXT, solicitante TEXT, aprovador TEXT, observacao TEXT,
        status TEXT DEFAULT 'Pendente Aprovação'
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historico_curva_abc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        mes_ano TEXT,
        cod_clean INTEGER,
        descricao TEXT,
        total_qtde REAL,
        pct_acumulado REAL,
        classe_abc TEXT,
        dt_atualizacao TEXT,
        UNIQUE(operacao, mes_ano, cod_clean)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS layout_armazem (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        nome_area TEXT,
        nome_arquivo TEXT,
        tipo_arquivo TEXT,
        dados_blob BLOB,
        dt_atualizacao TEXT
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gestao_ressuprimento_diario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        data_registro TEXT,
        mes_ano TEXT,
        cesta TEXT,
        volume_sellin_hl REAL DEFAULT 0.0,
        volume_real_hl REAL DEFAULT 0.0,
        dt_atualizacao TEXT,
        UNIQUE(operacao, data_registro, cesta)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metas_ressuprimento_mensal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        ano INTEGER,
        mes INTEGER,
        mes_ano TEXT,
        cesta TEXT,
        meta_volume_hl REAL DEFAULT 0.0,
        dt_atualizacao TEXT,
        UNIQUE(operacao, ano, mes, cesta)
    )""")

    empresas = [
        ("Lima Rio Verde", "12.345.678/0001-90", "Rio Verde", "GO"),
        ("Lima Barreiras", "98.765.432/0001-10", "Barreiras", "BA"),
        ("Lima São Félix", "45.678.912/0001-33", "São Félix do Coribe", "BA"),
    ]
    for emp in empresas:
        cursor.execute(
            "INSERT OR IGNORE INTO operacoes (nome, cnpj, cidade, uf) VALUES (?,?,?,?)",
            emp,
        )

    cursor.execute("SELECT count(*) FROM usuarios WHERE nome = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO usuarios (nome, senha, email, cargo, perfil, e_aprovador, alcada_reais, permissoes_operacoes, permissoes_deptos)
        VALUES ('admin', 'admin123', 'admin@grupolima.com.br', 'Administrador Master', 'Master', 'Sim', 9999999.0, 'TODAS', 'TODOS')
        """)

    conn.commit()
    conn.close()


init_db()


# 3. Funções Auxiliares de Leitura e Tratamento Ultra-Robustas
def read_word_file(file_obj):
    if not HAS_DOCX:
        return "A biblioteca 'python-docx' não está instalada no servidor."
    try:
        file_obj.seek(0)
        doc = docx.Document(file_obj)
        full_text = []
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())
        for table in doc.tables:
            for row in table.rows:
                row_text = [
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                ]
                if row_text:
                    full_text.append(" | ".join(row_text))
        return "\n".join(full_text)
    except Exception as e:
        return f"Erro ao ler arquivo do Word: {e}"


def robust_read_file(file_obj):
    filename = str(file_obj.name).lower()

    if filename.endswith(".xls"):
        for h in [0, 1, 2, 3, 4, 5]:
            try:
                file_obj.seek(0)
                df = pd.read_excel(file_obj, header=h, engine="xlrd")
                if df is not None and not df.empty and len(df.columns) > 1:
                    df = df.dropna(how="all", axis=1)
                    return df
            except Exception:
                continue

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        for h in [0, 1, 2, 3, 4, 5]:
            try:
                file_obj.seek(0)
                df = pd.read_excel(file_obj, header=h, engine="openpyxl")
                if df is not None and not df.empty and len(df.columns) > 1:
                    df = df.dropna(how="all", axis=1)
                    return df
            except Exception:
                try:
                    file_obj.seek(0)
                    df = pd.read_excel(file_obj, header=h)
                    if df is not None and not df.empty and len(df.columns) > 1:
                        df = df.dropna(how="all", axis=1)
                        return df
                except Exception:
                    continue

    if filename.endswith(".docx") or filename.endswith(".doc"):
        text = read_word_file(file_obj)
        lines = [line.split("|") for line in text.split("\n") if line.strip()]
        return pd.DataFrame(lines) if lines else pd.DataFrame()

    for sep_char in [";", ",", "\t"]:
        try:
            file_obj.seek(0)
            df = pd.read_csv(
                file_obj,
                sep=sep_char,
                encoding="utf-8-sig",
                engine="python",
                on_bad_lines="skip",
            )
            if df is not None and len(df.columns) > 1:
                return df
        except Exception:
            try:
                file_obj.seek(0)
                df = pd.read_csv(
                    file_obj,
                    sep=sep_char,
                    encoding="latin1",
                    engine="python",
                    on_bad_lines="skip",
                )
                if df is not None and len(df.columns) > 1:
                    return df
            except Exception:
                continue

    file_obj.seek(0)
    return pd.read_excel(file_obj)


def parse_br_float(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s:
        return 0.0

    s = re.sub(r"[R\$\s]", "", s)

    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "." in s:
        if s.count(".") > 1 or re.match(r"^\d{1,3}(\.\d{3})+$", s):
            s = s.replace(".", "")

    try:
        return float(s)
    except Exception:
        s_clean = re.sub(r"[^\d,\.-]", "", s)
        if "." in s_clean and "," in s_clean:
            s_clean = s_clean.replace(".", "").replace(",", ".")
        elif "," in s_clean:
            s_clean = s_clean.replace(",", ".")
        else:
            if s_clean.count(".") > 1 or re.match(
                r"^\d{1,3}(\.\d{3})+$", s_clean
            ):
                s_clean = s_clean.replace(".", "")
        try:
            return float(s_clean)
        except Exception:
            return 0.0


def formatar_br(val):
    try:
        if pd.isna(val):
            return "0,00"
        val_float = float(val)
        s_base = f"{val_float:,.2f}"
        s_base = s_base.replace(",", "X").replace(".", ",").replace("X", ".")
        if s_base.endswith(",00"):
            s_base = s_base[:-3]
        return s_base
    except Exception:
        return str(val)


def extract_ambev_brand(desc):
    d = str(desc).upper().strip()
    if d.startswith("BC ") or "BRAHMA" in d or d.startswith("BR "):
        return "BRAHMA"
    elif d.startswith("SK ") or "SKOL" in d:
        return "SKOL"
    elif d.startswith("ANT ") or "ANTARCTICA" in d:
        return "ANTARCTICA"
    elif d.startswith("ORG ") or "ORIGINAL" in d:
        return "ORIGINAL"
    elif d.startswith("BUD") or "BUDWEISER" in d:
        return "BUDWEISER"
    elif d.startswith("SPAT") or "SPATEN" in d:
        return "SPATEN"
    elif d.startswith("COR ") or "CORONA" in d:
        return "CORONA"
    elif "ARTOIS" in d or d.startswith("SLA ") or "STELLA" in d:
        return "STELLA ARTOIS"
    elif d.startswith("SU ") or d.startswith("SUK") or "SUKITA" in d:
        return "SUKITA"
    elif d.startswith("PC ") or "PEPSI" in d:
        return "PEPSI"
    elif d.startswith("GCA ") or "GUARANA" in d:
        return "GUARANÁ"
    elif d.startswith("CHP BR") or "CHOPP" in d:
        return "CHOPP BRAHMA"
    elif d.startswith("BECK") or "BECKS" in d:
        return "BECKS"
    elif "H2O" in d:
        return "H2OH!"
    else:
        return "OUTROS"


def highlight_curva_abc(val):
    if val == "A":
        return "background-color: #d4edda; color: #155724; font-weight: bold;"
    elif val == "B":
        return "background-color: #fff3cd; color: #856404; font-weight: bold;"
    elif val == "C":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
    return ""


def salvar_base_01_11(f_01):
    df_01 = robust_read_file(f_01)
    col_cod = [
        c for c in df_01.columns if "Código" in str(c) or "Cod" in str(c)
    ][0]
    df_01["cod_clean"] = pd.to_numeric(df_01[col_cod], errors="coerce")

    col_q = df_01.columns[16] if len(df_01.columns) > 16 else df_01.columns[-1]
    df_01["fator_hl"] = (
        df_01[col_q].astype(str).str.replace(",", ".").astype(float)
    )

    col_cx = [
        c
        for c in df_01.columns
        if "Caixas Pallet" in str(c) or "Pallet" in str(c)
    ]
    if col_cx:
        df_01["cx_pallet"] = pd.to_numeric(
            df_01[col_cx[0]], errors="coerce"
        ).fillna(1)
    else:
        df_01["cx_pallet"] = 1.0

    df_01["cx_pallet"] = df_01["cx_pallet"].apply(lambda x: x if x > 0 else 1)

    col_desc = [
        c for c in df_01.columns if "Descrição" in str(c) or "Desc" in str(c)
    ][0]
    df_sub = df_01[["cod_clean", col_desc, "fator_hl", "cx_pallet"]].dropna(
        subset=["cod_clean"]
    )

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    for _, r in df_sub.iterrows():
        cursor.execute(
            """
        INSERT INTO base_01_11 (cod_clean, descricao, fator_hl, cx_pallet)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(cod_clean) DO UPDATE SET
            descricao=excluded.descricao, fator_hl=excluded.fator_hl, cx_pallet=excluded.cx_pallet
        """,
            (
                int(r["cod_clean"]),
                str(r[col_desc]),
                float(r["fator_hl"]),
                float(r["cx_pallet"]),
            ),
        )
    conn.commit()
    conn.close()


def salvar_base_linear(f_lin):
    df_lin = robust_read_file(f_lin)

    cols_str = [str(c).strip().lower() for c in df_lin.columns]
    col_cod = None
    for i, c in enumerate(cols_str):
        if "cód" in c or "cod" in c or "item" in c or "produto" in c:
            col_cod = df_lin.columns[i]
            break
    if col_cod is None:
        col_cod = df_lin.columns[0]

    if len(df_lin.columns) > 4:
        col_vendas = df_lin.columns[4]
    else:
        col_vendas = (
            df_lin.columns[1] if len(df_lin.columns) > 1 else df_lin.columns[0]
        )

    df_lin["cod_clean"] = pd.to_numeric(df_lin[col_cod], errors="coerce")
    df_lin["linear_vendas"] = df_lin[col_vendas].apply(parse_br_float)
    df_lin["Tipo"] = df_lin.get("Tipo", df_lin.get("tipo", pd.Series())).fillna(
        "OUTROS"
    )
    df_lin["Categoria"] = df_lin.get(
        "Categoria", df_lin.get("categoria", pd.Series())
    ).fillna("OUTROS")

    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    for _, r in df_lin.dropna(subset=["cod_clean"]).iterrows():
        cursor.execute(
            """
        INSERT INTO base_linear (cod_clean, tipo, categoria, linear_vendas, dt_atualizacao)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(cod_clean) DO UPDATE SET
            tipo=excluded.tipo, categoria=excluded.categoria,
            linear_vendas=excluded.linear_vendas, dt_atualizacao=excluded.dt_atualizacao
        """,
            (
                int(r["cod_clean"]),
                str(r.get("Tipo", "OUTROS")),
                str(r.get("Categoria", "OUTROS")),
                float(r["linear_vendas"]),
                dt_now,
            ),
        )
    conn.commit()
    conn.close()


def salvar_base_estoque_02(f_02, operacao):
    df_02 = robust_read_file(f_02)

    col_cod = [
        c for c in df_02.columns if "Cod" in str(c) or "COD" in str(c)
    ][0]
    col_desc = [c for c in df_02.columns if "Desc" in str(c)][0]
    col_init = [c for c in df_02.columns if "Inic" in str(c)][0]
    col_ent = [c for c in df_02.columns if "Ent" in str(c)][0]
    col_sai = [
        c for c in df_02.columns if "Saida" in str(c) or "Sai" in str(c)
    ][0]
    col_disp = [c for c in df_02.columns if "Disp" in str(c)][0]

    df_02["cod_clean"] = pd.to_numeric(df_02[col_cod], errors="coerce")
    df_02["Inicial"] = pd.to_numeric(df_02[col_init], errors="coerce").fillna(0)
    df_02["Ent."] = pd.to_numeric(df_02[col_ent], errors="coerce").fillna(0)
    df_02["Saidas"] = pd.to_numeric(df_02[col_sai], errors="coerce").fillna(0)
    df_02["Disp."] = pd.to_numeric(df_02[col_disp], errors="coerce").fillna(0)

    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    for _, r in df_02.dropna(subset=["cod_clean"]).iterrows():
        cursor.execute(
            """
        INSERT INTO base_estoque_02 (operacao, cod_clean, descricao, inicial, entrada, saida, disponivel, dt_atualizacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(operacao, cod_clean) DO UPDATE SET
            descricao=excluded.descricao, inicial=excluded.inicial, entrada=excluded.entrada,
            saida=excluded.saida, disponivel=excluded.disponivel, dt_atualizacao=excluded.dt_atualizacao
        """,
            (
                operacao,
                int(r["cod_clean"]),
                str(r[col_desc]),
                float(r["Inicial"]),
                float(r["Ent."]),
                float(r["Saidas"]),
                float(r["Disp."]),
                dt_now,
            ),
        )
    conn.commit()
    conn.close()


def salvar_pedidos_marcados(f_pedidos, operacao):
    df_pedidos = robust_read_file(f_pedidos)

    col_cod_r = (
        df_pedidos.columns[17]
        if len(df_pedidos.columns) > 17
        else [
            c
            for c in df_pedidos.columns
            if "Código" in str(c) or "Cod" in str(c)
        ][0]
    )
    col_marc_w = (
        df_pedidos.columns[22]
        if len(df_pedidos.columns) > 22
        else [c for c in df_pedidos.columns if "Marcado" in str(c)][0]
    )
    col_desc = [
        c
        for c in df_pedidos.columns
        if "Produto" in str(c) or "Desc" in str(c)
    ][0]
    col_dt = [
        c
        for c in df_pedidos.columns
        if "Data Puxada" in str(c) or "Data" in str(c)
    ][0]
    col_solic = [
        c
        for c in df_pedidos.columns
        if "QtdeSKUs - Item" in str(c) or "Solicitado" in str(c)
    ][0]
    col_hl = [
        c for c in df_pedidos.columns if "HL" in str(c) or "Hecto" in str(c)
    ][0]

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM pedidos_marcados WHERE operacao=?", (operacao,))

    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")
    for _, r in df_pedidos.iterrows():
        cod_raw = str(r.get(col_cod_r, "")).strip()

        if len(cod_raw) > 1:
            cod_clean_str = cod_raw[:-1]
        else:
            cod_clean_str = cod_raw

        cod_clean = pd.to_numeric(cod_clean_str, errors="coerce")
        if pd.isna(cod_clean):
            continue

        cx_marcadas_w = parse_br_float(r.get(col_marc_w))

        cursor.execute(
            """
        INSERT INTO pedidos_marcados (operacao, data_puxada, cod_clean, descricao, cx_solicitadas, cx_marcadas, hl_marcado, status_item, numero_pedido, dt_atualizacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                operacao,
                str(r.get(col_dt)).strip(),
                int(cod_clean),
                str(r.get(col_desc)).strip(),
                parse_br_float(r.get(col_solic)),
                cx_marcadas_w,
                parse_br_float(r.get(col_hl)),
                str(r.get("Status - Item", "")).strip(),
                str(r.get("Nº - Pedido", "")).strip(),
                dt_now,
            ),
        )

    conn.commit()
    conn.close()


def carregar_estoque_consolidado(operacao):
    conn = sqlite3.connect("puxada_ambev.db")

    ops_filtro = [operacao]
    if operacao == "Bahia":
        ops_filtro = [
            "Lima Barreiras",
            "Lima São Félix",
            "Lima Bahia",
            "Lima Bahia Samavi",
        ]

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
    conn.close()

    if df.empty:
        return None

    df.columns = [str(c).lower() for c in df.columns]

    df["classe_abc"] = "C"
    df["total_puxada"] = 0
    df["estoque_projetado"] = df["disp"] + df["total_puxada"]

    df["doi_atual"] = df.apply(
        lambda r: round(r["disp"] / r["linear_vendas"], 1)
        if r["linear_vendas"] > 0
        else (999.0 if r["disp"] > 0 else 0.0),
        axis=1,
    )

    df["estoque_hl"] = (df["fator_hl"] * df["disp"]).round(2)
    df["marca"] = df["descricao"].apply(extract_ambev_brand)
    df["paletes_ocupados"] = (df["disp"] / df["cx_pallet"]).round(1)

    return df


def calcular_saude_estoque_dpo(df):
    if df is None or df.empty:
        return 0.0, 0, 0, 0
    total_skus = len(df)
    saudaveis = len(df[(df["doi_atual"] >= 3.0) & (df["doi_atual"] <= 15.0)])
    ruptura = len(df[df["doi_atual"] < 3.0])
    excesso = len(df[df["doi_atual"] > 15.0])
    pct_saude = (saudaveis / total_skus) * 100.0 if total_skus > 0 else 0.0
    return round(pct_saude, 1), saudaveis, ruptura, excesso


def gerar_excel(df):
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Dados")
    except Exception:
        df.to_csv(output, index=False, sep=";")
    return output.getvalue()


# 4. Auxiliares e IA para Padrões DPO
def carregar_padrao_dpo(operacao, modulo, subbloco):
    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT titulo_padrao, conteudo_padrao, sugestoes_ia, dt_atualizacao FROM padroes_dpo WHERE operacao=? AND modulo=? AND subbloco=?",
        (operacao, modulo, subbloco),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "titulo": row[0],
            "conteudo": row[1],
            "sugestoes": row[2],
            "dt": row[3],
        }
    return None


def salvar_padrao_dpo(
    operacao, modulo, subbloco, titulo, conteudo, sugestoes=""
):
    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")
    cursor.execute(
        """
    INSERT INTO padroes_dpo (operacao, modulo, subbloco, titulo_padrao, conteudo_padrao, sugestoes_ia, dt_atualizacao)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(operacao, modulo, subbloco) DO UPDATE SET
        titulo_padrao=excluded.titulo_padrao,
        conteudo_padrao=excluded.conteudo_padrao,
        sugestoes_ia=excluded.sugestoes_ia,
        dt_atualizacao=excluded.dt_atualizacao
    """,
        (operacao, modulo, subbloco, titulo, conteudo, sugestoes, dt_now),
    )
    conn.commit()
    conn.close()


def gerar_sugestao_ia_dpo(modulo, subbloco, conteudo_atual):
    recomendações = [
        f"📌 **Adequação ao Pilar DPO ({modulo} - {subbloco})**:",
        "- **Matriz RACI**: Explicite os papéis do Executor, Aprovador, Consultado e Informado.",
        "- **Rotina de Audit**: Definir verificação semanal pelo líder de processo.",
        "- **Conexão KPI**: Associar este padrão diretamente aos resultados auditados no DPO.",
        "- **Segurança em Primeiro Lugar**: Incluir checklist de EPIs e análise de riscos operacionais.",
    ]
    if len(conteudo_atual.strip()) < 50:
        recomendações.append(
            "⚠️ **Alerta DPO**: O texto atual está curto. Adicione detalhamento passo a passo para evitar falhas operacionais."
        )
    return "\n".join(recomendações)


def render_gerenciador_padroes_dpo(operacao, modulo, subbloco):
    st.markdown(f"### 📋 Padrão Operacional DPO ({subbloco})")
    padrao = carregar_padrao_dpo(operacao, modulo, subbloco)

    tit_def = padrao["titulo"] if padrao else f"Padrão de Execução DPO - {subbloco}"
    cont_def = (
        padrao["conteudo"]
        if padrao
        else "Descreva aqui o procedimento operacional padrão no formato DPO Ambev..."
    )
    sug_def = padrao["sugestoes"] if padrao else ""

    if padrao and padrao.get("dt"):
        st.caption(f"🕒 **Última Atualização:** {padrao['dt']}")

    tab_p1, tab_p2 = st.tabs(
        ["📝 Visualizar & Editar Padrão", "🤖 Consultoria e Sugestões da IA DPO"]
    )

    with tab_p1:
        with st.form(f"form_padrao_{modulo}_{subbloco}"):
            tit_input = st.text_input("Título do Padrão:", value=tit_def)
            cont_input = st.text_area(
                "Conteúdo do Padrão Operacional (Editável):",
                value=cont_def,
                height=250,
            )

            file_padrao = st.file_uploader(
                "Anexar/Importar Documento do Padrão (.docx, .xlsx, .csv, .txt):",
                type=["docx", "doc", "xlsx", "xls", "txt", "csv"],
            )
            if file_padrao is not None:
                fname = str(file_padrao.name).lower()
                try:
                    if fname.endswith(".docx") or fname.endswith(".doc"):
                        cont_input = read_word_file(file_padrao)
                        st.info(
                            "Conteúdo extraído do documento Word com sucesso!"
                        )
                    elif fname.endswith(".xlsx") or fname.endswith(".xls"):
                        df_imp = pd.read_excel(file_padrao)
                        cont_input = df_imp.to_string(index=False)
                        st.info(
                            "Conteúdo extraído da planilha Excel com sucesso!"
                        )
                    else:
                        cont_input = file_padrao.read().decode("utf-8")
                        st.info(
                            "Conteúdo importado do arquivo de texto com sucesso!"
                        )
                except Exception as ex:
                    st.error(f"Erro ao processar o arquivo: {ex}")

            c_s1, c_s2 = st.columns(2)
            salvar_btn = c_s1.form_submit_button("💾 Salvar Padrão Atualizado")
            pedir_ia = c_s2.form_submit_button(
                "🤖 Analisar e Gerar Sugestões com IA"
            )

            if salvar_btn:
                salvar_padrao_dpo(
                    operacao,
                    modulo,
                    subbloco,
                    tit_input,
                    cont_input,
                    sug_def,
                )
                st.success("Padrão DPO salvo com sucesso!")
                st.rerun()

            if pedir_ia:
                sug_gerada = gerar_sugestao_ia_dpo(
                    modulo, subbloco, cont_input
                )
                salvar_padrao_dpo(
                    operacao,
                    modulo,
                    subbloco,
                    tit_input,
                    cont_input,
                    sug_gerada,
                )
                st.success("Sugestões DPO geradas pela IA!")
                st.rerun()

    with tab_p2:
        if sug_def:
            st.info(sug_def)
        else:
            st.caption(
                "Clique em 'Analisar e Gerar Sugestões com IA' no formulário para obter diagnósticos da norma DPO."
            )


# -----------------------------------------------------------------------------
# AUXILIARES PARA GESTÃO E ANEXO DE IMAGENS DO LAYOUT DO ARMAZÉM
# -----------------------------------------------------------------------------
def salvar_layout_imagem(operacao, nome_area, file_uploader_obj):
    if file_uploader_obj is not None:
        file_bytes = file_uploader_obj.read()
        nome_arq = file_uploader_obj.name
        tipo_arq = file_uploader_obj.type
        dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

        conn = sqlite3.connect("puxada_ambev.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO layout_armazem (operacao, nome_area, nome_arquivo, tipo_arquivo, dados_blob, dt_atualizacao)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (operacao, nome_area, nome_arq, tipo_arq, file_bytes, dt_now),
        )
        conn.commit()
        conn.close()
        return True
    return False


def carregar_layouts_armazem(operacao):
    conn = sqlite3.connect("puxada_ambev.db")
    df = pd.read_sql_query(
        f"SELECT id, nome_area, nome_arquivo, tipo_arquivo, dados_blob, dt_atualizacao FROM layout_armazem WHERE operacao='{operacao}' ORDER BY id DESC",
        conn,
    )
    conn.close()
    return df


def deletar_layout_armazem(layout_id):
    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM layout_armazem WHERE id=?", (layout_id,))
    conn.commit()
    conn.close()


def render_gestao_layouts_armazem(operacao):
    st.markdown("### 🗺️ Cadastro e Anexo de Layouts por Área do Armazém")
    st.caption(
        "Cadastre novas áreas do armazém e anexe múltiplos esquemas/plantas em formato de imagem."
    )

    with st.expander("➕ Cadastrar / Anexar Novo Layout de Área", expanded=True):
        with st.form("form_novo_layout"):
            c_a1, c_a2 = st.columns([1, 1])
            nome_area_input = c_a1.text_input(
                "Nome / Identificação da Área:",
                placeholder="Ex: Área de Picking, Pulmão 01, Vasilhame, Pátio",
            )
            img_layout = c_a2.file_uploader(
                "Selecione a Imagem do Layout:",
                type=["png", "jpg", "jpeg", "webp"],
            )

            btn_salvar_layout = st.form_submit_button(
                "🖼️ Salvar e Anexar Layout"
            )

            if btn_salvar_layout:
                if not nome_area_input.strip():
                    st.error(
                        "Por favor, preencha o nome da área antes de salvar."
                    )
                elif img_layout is None:
                    st.error("Por favor, selecione um arquivo de imagem.")
                else:
                    salvar_layout_imagem(
                        operacao, nome_area_input.strip(), img_layout
                    )
                    st.success(
                        f"Layout da área **{nome_area_input}** anexado com sucesso!"
                    )
                    st.rerun()

    st.divider()
    st.markdown("### 🖼️ Visualização dos Layouts Cadastrados")

    df_layouts = carregar_layouts_armazem(operacao)

    if not df_layouts.empty:
        areas_unicas = sorted(df_layouts["nome_area"].unique().tolist())
        filtro_area = st.selectbox(
            "Filtrar por Área do Armazém:", ["TODAS AS ÁREAS"] + areas_unicas
        )

        df_exibir = (
            df_layouts
            if filtro_area == "TODAS AS ÁREAS"
            else df_layouts[df_layouts["nome_area"] == filtro_area]
        )

        cols_grid = st.columns(2)
        for idx, row in df_exibir.reset_index(drop=True).iterrows():
            col_target = cols_grid[idx % 2]
            with col_target:
                with st.container():
                    st.markdown(f"#### 📍 Área: {row['nome_area']}")
                    st.caption(
                        f"📁 **Arquivo:** {row['nome_arquivo']} | 🕒 {row['dt_atualizacao']}"
                    )

                    try:
                        st.image(
                            row["dados_blob"],
                            caption=f"{row['nome_area']} - {row['nome_arquivo']}",
                            use_column_width=True,
                        )
                    except Exception as e:
                        st.error(
                            f"Não foi possível renderizar a imagem: {e}"
                        )

                    if st.button(
                        f"🗑️ Excluir Layout #{row['id']}",
                        key=f"del_lay_{row['id']}",
                    ):
                        deletar_layout_armazem(row["id"])
                        st.warning("Layout removido com sucesso!")
                        st.rerun()
                st.divider()
    else:
        st.info(
            "ℹ️ Nenhum layout cadastrado para esta unidade. Utilize o formulário acima para anexar as plantas do armazém."
        )


# -----------------------------------------------------------------------------
# GESTÃO DE RESSUPRIMENTO (CESTAS, METAS, TENDÊNCIA & LAYOUT POR OPERAÇÃO)
# -----------------------------------------------------------------------------
def render_gestao_ressuprimento(operacao, modo_estatico=False):
    st.subheader(
        "📈 Gestão de Ressuprimento & Acompanhamento de Cestas (HL do Mês)"
    )

    mapa_op_sistema = {
        "Lima Rio Verde": ["Lima Rio Verde", "Lima - Rio Verde", "Rio Verde"],
        "Lima Barreiras": ["Lima Bahia", "Barreiras", "Lima Barreiras"],
        "Lima São Félix": [
            "Lima Bahia Samavi",
            "Samavi",
            "São Félix",
            "Lima São Félix",
        ],
        "Bahia": [
            "Lima Barreiras",
            "Lima São Félix",
            "Barreiras",
            "Samavi",
            "São Félix",
            "Lima Bahia",
            "Lima Bahia Samavi",
        ],
    }

    nombres_filtro = mapa_op_sistema.get(operacao, [operacao])
    nome_exibicao_op = (
        "Bahia (Barreiras + São Félix)"
        if operacao == "Bahia"
        else operacao.replace("Lima ", "")
    )

    if not modo_estatico:
        st.markdown("##### 🔗 Links de Acesso Direto (Visualização Estática / Sem Atualização)")
        st.caption("Clique nos botões abaixo para abrir a visualização direta e somente leitura de cada operação:")
        
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        
        col_btn1.link_button("🔗 Barreiras", "?visualizacao=ressuprimento&op=Lima+Barreiras", use_container_width=True)
        col_btn2.link_button("🔗 São Félix", "?visualizacao=ressuprimento&op=Lima+S%C3%A3o+F%C3%élix", use_container_width=True)
        col_btn3.link_button("🔗 Bahia (Barreiras + São Félix)", "?visualizacao=ressuprimento&op=Bahia", use_container_width=True)

        st.divider()

        tab_m1, tab_m2, tab_m3, tab_m4 = st.tabs([
            "📊 Acompanhamento Mensal & Volume Total",
            "📅 Carregamento Dia a Dia",
            "⚙️ Configuração de Metas Mensais",
            "📁 Upload & Atualização da Base Diária",
        ])
    else:
        tab_m1 = st.container()
        tab_m2 = st.container()
        tab_m3 = None
        tab_m4 = None

    cestas_map = {
        "CATEGORIA_AGRUPADO - CERVEJA": "Cerveja",
        "CATEGORIA_AGRUPADO - NAB": "Nab",
        "CATEGORIA - MATCH": "Match",
        "CATEGORIA_RETORNAVEL - CERVEJA RGB": "Cerveja RGB",
        "REFRIGERANTE_REGULAR_NAB - ZERO": "Nab Zero",
        "CERV_2 - Zero Alcool": "Cerveja Zero Alcool",
        "SEGMENTO - HIGH END": "High End",
    }

    cestas_ordenadas = list(cestas_map.keys())

    # Bloco Acompanhamento Mensal
    def bloco_acompanhamento():
        c_f1, c_f2 = st.columns(2)
        ano_sel = c_f1.number_input(
            "Ano de Análise:",
            min_value=2024,
            max_value=2030,
            value=datetime.now().year,
            key="ano_acompanhamento",
        )

        meses_nomes = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
        ]
        
        meses_selecionados = c_f2.multiselect(
            "Selecione os Meses de Análise (vazio = Ano Inteiro):",
            options=list(range(1, 13)),
            format_func=lambda x: meses_nomes[x - 1],
            default=[datetime.now().month],
            key="meses_acompanhamento",
        )

        conn = sqlite3.connect("puxada_ambev.db")
        placeholders_op = ",".join(["?"] * len(nombres_filtro))
        df_diario = pd.read_sql_query(
            f"SELECT * FROM gestao_ressuprimento_diario WHERE operacao IN ({placeholders_op}) AND strftime('%Y', data_registro)='{ano_sel}'",
            conn,
            params=nombres_filtro,
        )
        df_metas = pd.read_sql_query(
            f"SELECT * FROM metas_ressuprimento_mensal WHERE operacao IN ({placeholders_op}) AND ano={ano_sel}",
            conn,
            params=nombres_filtro,
        )
        conn.close()

        if not df_diario.empty:
            df_diario["data_dt"] = pd.to_datetime(
                df_diario["data_registro"], errors="coerce"
            )
            
            if not meses_selecionados:
                meses_selecionados = list(range(1, 13))

            df_diario_filtrado = df_diario[
                df_diario["data_dt"].dt.month.isin(meses_selecionados)
            ]

            dias_preenchidos = df_diario_filtrado["data_dt"].dt.date.nunique()

            dias_no_ano_total = 0
            for m_s in meses_selecionados:
                if m_s in [1, 3, 5, 7, 8, 10, 12]:
                    dias_no_ano_total += 31
                elif m_s in [4, 6, 9, 11]:
                    dias_no_ano_total += 30
                else:
                    dias_no_ano_total += (
                        29
                        if (
                            ano_sel % 4 == 0
                            and (ano_sel % 100 != 0 or ano_sel % 400 == 0)
                        )
                        else 28
                    )

            df_res_mes = (
                df_diario_filtrado.groupby("cesta")["volume_sellin_hl"]
                .sum()
                .reset_index()
            )

            df_comp = pd.merge(
                pd.DataFrame({"cesta": cestas_ordenadas}),
                df_res_mes,
                on="cesta",
                how="left",
            ).fillna(0)

            df_metas_filtradas = df_metas[
                df_metas["mes"].isin(meses_selecionados)
            ]
            df_metas_grp = (
                df_metas_filtradas.groupby("cesta")["meta_volume_hl"]
                .sum()
                .reset_index()
            )

            df_comp = pd.merge(
                df_comp, df_metas_grp, on="cesta", how="left"
            ).fillna(0)

            fator_tend = (
                (dias_no_ano_total / dias_preenchidos)
                if dias_preenchidos > 0
                else 1.0
            )

            df_comp["INDICADOR"] = df_comp["cesta"].map(cestas_map)
            df_comp["META"] = df_comp["meta_volume_hl"]
            df_comp["REAL"] = df_comp["volume_sellin_hl"]
            df_comp["TEND."] = df_comp["REAL"] * fator_tend

            df_comp["ATING. REAL"] = df_comp.apply(
                lambda r: (r["REAL"] / r["META"] * 100)
                if r["META"] > 0
                else 0.0,
                axis=1,
            )
            df_comp["ATING. TEND."] = df_comp.apply(
                lambda r: (r["TEND."] / r["META"] * 100)
                if r["META"] > 0
                else 0.0,
                axis=1,
            )
            
            df_comp["PENDÊNCIA PERÍODO"] = df_comp["REAL"] - df_comp["META"]

            df_cerveja_nab = df_comp[df_comp["INDICADOR"].isin(["Cerveja", "Nab"])]
            tot_meta = df_cerveja_nab["META"].sum()
            tot_real = df_cerveja_nab["REAL"].sum()
            tot_tend = df_cerveja_nab["TEND."].sum()
            tot_pend = tot_real - tot_meta
            
            tot_ating_real = (tot_real / tot_meta * 100) if tot_meta > 0 else 0.0
            tot_ating_tend = (tot_tend / tot_meta * 100) if tot_meta > 0 else 0.0

            df_total = pd.DataFrame([{
                "INDICADOR": f"Total {nome_exibicao_op} (Cerveja + Nab)",
                "META": tot_meta,
                "REAL": tot_real,
                "TEND.": tot_tend,
                "ATING. REAL": tot_ating_real,
                "ATING. TEND.": tot_ating_tend,
                "PENDÊNCIA PERÍODO": tot_pend,
            }])

            meses_str = ", ".join([meses_nomes[m - 1] for m in meses_selecionados])
            st.markdown(
                f"""
                <div style="background-color: #0d2149; color: white; padding: 12px 20px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                    <h3 style="margin:0; font-size: 20px; color: white;">🔵 {nome_exibicao_op}</h3>
                    <span style="font-size: 13px; color: #b0c4de;">Somatório de HL do Mês · Meses: {meses_str} · {dias_preenchidos} dia(s) computado(s)</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            df_final = pd.concat([
                df_comp[[
                    "INDICADOR",
                    "META",
                    "REAL",
                    "TEND.",
                    "ATING. REAL",
                    "ATING. TEND.",
                    "PENDÊNCIA PERÍODO",
                ]],
                df_total,
            ], ignore_index=True)

            def format_atingimento_com_condicional(val):
                try:
                    v = float(val)
                    s_val = f"{v:.1f}%".replace(".", ",")
                    if v >= 100.0:
                        return f"🟢 {s_val} (Batendo)"
                    else:
                        return f"🔴 {s_val} (Abaixo)"
                except Exception:
                    return val

            df_view = df_final.copy()
            df_view["META"] = df_view["META"].apply(formatar_br)
            df_view["REAL"] = df_view["REAL"].apply(formatar_br)
            df_view["TEND."] = df_view["TEND."].apply(formatar_br)
            df_view["ATING. REAL"] = df_view["ATING. REAL"].apply(format_atingimento_com_condicional)
            df_view["ATING. TEND."] = df_view["ATING. TEND."].apply(format_atingimento_com_condicional)
            df_view["PENDÊNCIA PERÍODO"] = df_view["PENDÊNCIA PERÍODO"].apply(formatar_br)

            st.dataframe(
                df_view,
                use_container_width=True,
                height=(len(df_view) + 1) * 38 + 5,
            )

        else:
            st.info(
                f"ℹ️ Verifique se há dados diários cadastrados para **{nome_exibicao_op}** no ano de {ano_sel}."
            )

    # Bloco Carregamento Dia a Dia
    def bloco_carregamento_dia_a_dia():
        st.markdown(f"### 📅 Carregamento Dia a Dia - {nome_exibicao_op}")
        st.caption("Selecione o ano e o mês para visualizar o volume diário detalhado por indicador (em HL).")

        c_d1, c_d2 = st.columns(2)
        ano_dia = c_d1.number_input(
            "Ano de Análise:",
            min_value=2024,
            max_value=2030,
            value=datetime.now().year,
            key="ano_dia_a_dia",
        )

        meses_nomes_lista = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        mes_dia = c_d2.selectbox(
            "Mês de Análise:",
            list(range(1, 13)),
            format_func=lambda x: meses_nomes_lista[x - 1],
            index=datetime.now().month - 1,
            key="mes_dia_a_dia",
        )

        conn = sqlite3.connect("puxada_ambev.db")
        placeholders_op = ",".join(["?"] * len(nombres_filtro))
        query_dia = f"""
            SELECT data_registro, cesta, SUM(volume_sellin_hl) as vol_hl
            FROM gestao_ressuprimento_diario
            WHERE operacao IN ({placeholders_op}) 
              AND CAST(STRFTIME('%Y', data_registro) AS INTEGER) = ?
              AND CAST(STRFTIME('%m', data_registro) AS INTEGER) = ?
            GROUP BY data_registro, cesta
        """
        df_diario_bruto = pd.read_sql_query(
            query_dia,
            conn,
            params=nombres_filtro + [ano_dia, mes_dia],
        )
        conn.close()

        if not df_diario_bruto.empty:
            df_diario_bruto["data_dt"] = pd.to_datetime(df_diario_bruto["data_registro"], errors="coerce")
            df_diario_bruto["Dia"] = df_diario_bruto["data_dt"].dt.strftime("%d/%m/%Y")
            df_diario_bruto["Indicador"] = df_diario_bruto["cesta"].map(cestas_map).fillna("Outros")

            df_pivot = df_diario_bruto.pivot_table(
                index=["data_dt", "Dia"],
                columns="Indicador",
                values="vol_hl",
                aggfunc="sum"
            ).reset_index()

            df_pivot = df_pivot.sort_values("data_dt")
            df_pivot = df_pivot.drop(columns=["data_dt"])
            df_pivot = df_pivot.fillna(0.0)

            cols_indicadores = [c for c in df_pivot.columns if c != "Dia"]
            df_pivot["Total Dia (HL)"] = df_pivot[cols_indicadores].sum(axis=1)

            df_view_dia = df_pivot.copy()
            for col in cols_indicadores + ["Total Dia (HL)"]:
                df_view_dia[col] = df_view_dia[col].apply(formatar_br)

            st.markdown(f"##### 📊 Detalhamento Diário - {meses_nomes_lista[mes_dia - 1]}/{ano_dia}")
            st.dataframe(df_view_dia, use_container_width=True)

            st.download_button(
                "Exportar Carregamento Dia a Dia (.xlsx)",
                data=gerar_excel(df_pivot),
                file_name=f"Carregamento_Dia_a_Dia_{mes_dia:02d}_{ano_dia}_{operacao.replace(' ', '_')}.xlsx",
                key="dl_dia_a_dia"
            )
        else:
            st.info(f"ℹ️ Nenhum registro de carregamento diário encontrado para **{nome_exibicao_op}** em {meses_nomes_lista[mes_dia - 1]}/{ano_dia}.")

    if modo_estatico:
        st.markdown("---")
        bloco_acompanhamento()
        st.markdown("---")
        bloco_carregamento_dia_a_dia()
    else:
        with tab_m1:
            bloco_acompanhamento()

        with tab_m2:
            bloco_carregamento_dia_a_dia()

        with tab_m3:
            st.markdown(
                f"### 🎯 Cadastrar / Ajustar Metas Mensais ({nome_exibicao_op})"
            )
            c_m1, c_m2 = st.columns(2)
            ano_meta = c_m1.number_input(
                "Ano da Meta:",
                min_value=2024,
                max_value=2030,
                value=datetime.now().year,
                key="ano_meta_key",
            )
            meses_nomes_lista = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_meta = c_m2.selectbox(
                "Mês da Meta:",
                list(range(1, 13)),
                format_func=lambda x: meses_nomes_lista[x - 1],
                index=datetime.now().month - 1,
                key="mes_meta_key",
            )

            mes_ano_meta_str = f"{['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][mes_meta-1]}/{ano_meta}"

            conn = sqlite3.connect("puxada_ambev.db")
            df_exist_metas = pd.read_sql_query(
                f"SELECT cesta, meta_volume_hl FROM metas_ressuprimento_mensal WHERE operacao IN ({','.join(['?']*len(nombres_filtro))}) AND ano={ano_meta} AND mes={mes_meta}",
                conn,
                params=nombres_filtro,
            )
            conn.close()

            dict_metas_exist = (
                dict(
                    zip(
                        df_exist_metas["cesta"], df_exist_metas["meta_volume_hl"]
                    )
                )
                if not df_exist_metas.empty
                else {}
            )

            with st.form("form_cad_metas"):
                st.markdown(
                    f"**Metas em HL para {mes_ano_meta_str} - {nome_exibicao_op}:**"
                )
                input_metas = {}
                for cst in cestas_ordenadas:
                    cst_nome_amigavel = cestas_map.get(cst, cst)
                    val_init = float(dict_metas_exist.get(cst, 0.0))
                    input_metas[cst] = st.number_input(
                        f"Meta: {cst_nome_amigavel}",
                        min_value=0.0,
                        value=val_init,
                        step=10.0,
                    )

                if st.form_submit_button("💾 Salvar Metas Mensais"):
                    conn = sqlite3.connect("puxada_ambev.db")
                    cursor = conn.cursor()
                    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    op_para_salvar = (
                        operacao if operacao != "Bahia" else "Lima Barreiras"
                    )
                    for cst, m_val in input_metas.items():
                        cursor.execute(
                            """
                        INSERT INTO metas_ressuprimento_mensal (operacao, ano, mes, mes_ano, cesta, meta_volume_hl, dt_atualizacao)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(operacao, ano, mes, cesta) DO UPDATE SET
                            meta_volume_hl=excluded.meta_volume_hl, dt_atualizacao=excluded.dt_atualizacao
                        """,
                            (
                                op_para_salvar,
                                ano_meta,
                                mes_meta,
                                mes_ano_meta_str,
                                cst,
                                m_val,
                                dt_now,
                            ),
                        )
                    conn.commit()
                    conn.close()
                    st.success(
                        f"Metas de {mes_ano_meta_str} salvas com sucesso para {nome_exibicao_op}!"
                    )
                    st.rerun()

        with tab_m4:
            st.markdown("### 📁 Upload do Relatório Diário de Ressuprimento")
            st.caption(
                "Suba o arquivo consolidado contendo os volumes diários (.xlsx, .xls, .csv). O sistema mapeará rigorosamente a **Coluna A** (Operação), **Coluna C** (HL Puxado), **Coluna E** (Indicador) e **Coluna F** (Data)."
            )

            f_ress_daily = st.file_uploader(
                "Selecione o arquivo de relatório diário (.xlsx, .xls, .csv):",
                type=["xlsx", "xls", "csv"],
                key="up_ress_daily",
            )

            if f_ress_daily is not None and st.button(
                "🚀 Processar e Atualizar Base de Dados"
            ):
                try:
                    df_up = robust_read_file(f_ress_daily)

                    col_op = df_up.columns[0]
                    col_sellin = df_up.columns[2]
                    col_cesta = df_up.columns[4]
                    col_data = df_up.columns[5]

                    conn = sqlite3.connect("puxada_ambev.db")
                    cursor = conn.cursor()
                    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

                    registros_salvos = 0
                    for _, r in df_up.dropna(
                        subset=[col_cesta, col_data]
                    ).iterrows():
                        raw_op = (
                            str(r[col_op]).strip()
                            if pd.notna(r[col_op])
                            else operacao
                        )

                        if "Samavi" in raw_op or "São Félix" in raw_op:
                            op_salvar = "Lima Bahia Samavi"
                        elif "Barreiras" in raw_op or "Lima Bahia" in raw_op:
                            op_salvar = "Lima Bahia"
                        elif "Rio Verde" in raw_op:
                            op_salvar = "Lima - Rio Verde"
                        else:
                            op_salvar = raw_op

                        cst_val = str(r[col_cesta]).strip()
                        dt_val = str(
                            pd.to_datetime(r[col_data]).strftime("%Y-%m-%d")
                        )
                        mes_ano_val = str(
                            pd.to_datetime(r[col_data]).strftime("%b/%Y")
                        )

                        s_hl = parse_br_float(r[col_sellin])

                        cursor.execute(
                            """
                        INSERT INTO gestao_ressuprimento_diario (operacao, data_registro, mes_ano, cesta, volume_sellin_hl, volume_real_hl, dt_atualizacao)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(operacao, data_registro, cesta) DO UPDATE SET
                            volume_sellin_hl=excluded.volume_sellin_hl,
                            volume_real_hl=excluded.volume_sellin_hl,
                            dt_atualizacao=excluded.dt_atualizacao
                        """,
                            (
                                op_salvar,
                                dt_val,
                                mes_ano_val,
                                cst_val,
                                s_hl,
                                s_hl,
                                dt_now,
                            ),
                        )
                        registros_salvos += 1

                    conn.commit()
                    conn.close()
                    st.success(
                        f"Base de dados atualizada! **{registros_salvos}** registros diários sincronizados com sucesso."
                    )
                    st.rerun()

                except Exception as e:
                    st.error(f"Erro ao processar o arquivo nas colunas exigidas: {e}")


# 5. Navegação por Pilhas de Histórico (Botão Voltar)
if "nav_stack" not in st.session_state:
    st.session_state["nav_stack"] = ["Visão Geral (Dashboard)"]


def navigate_to(page_name):
    if st.session_state["nav_stack"][-1] != page_name:
        st.session_state["nav_stack"].append(page_name)


def go_back():
    if len(st.session_state["nav_stack"]) > 1:
        st.session_state["nav_stack"].pop()


# 6. Portal Comercial Direto ou Visualização Estática por Operação via Parâmetro URL
modo_comercial = False
modo_visualizacao_estatica = False
op_estatica = None

if "modo" in st.query_params:
    val_modo = st.query_params["modo"]
    if isinstance(val_modo, list):
        modo_comercial = "comercial" in val_modo
    else:
        modo_comercial = val_modo == "comercial"

if "visualizacao" in st.query_params:
    val_vis = st.query_params["visualizacao"]
    if isinstance(val_vis, list):
        modo_visualizacao_estatica = "ressuprimento" in val_vis
    else:
        modo_visualizacao_estatica = val_vis == "ressuprimento"

    if "op" in st.query_params:
        op_estatica = st.query_params["op"]
        if isinstance(op_estatica, list):
            op_estatica = op_estatica[0]


def render_estoque_dia(unidade):
    st.subheader("📱 Portal do RN - Consulta Comercial de Vendas")

    df = carregar_estoque_consolidado(unidade)

    if df is not None and not df.empty:
        st.caption(f"🕒 **Última Atualização:** {df['dt_atualizacao'].iloc[0]}")

        def get_status(doi, disp):
            if disp == 0:
                return "🔴 Stock Out (Zerado)"
            elif doi < 3.0:
                return "🟡 Stock Low (Baixo)"
            elif doi <= 15.0:
                return "🟢 Stock Ideal"
            else:
                return "🔵 Stock Over (Excesso)"

        df["status"] = df.apply(
            lambda r: get_status(r["doi_atual"], r["disp"]), axis=1
        )

        stock_out_cnt = len(df[df["status"] == "🔴 Stock Out (Zerado)"])
        stock_low_cnt = len(df[df["status"] == "🟡 Stock Low (Baixo)"])
        stock_ideal_cnt = len(df[df["status"] == "🟢 Stock Ideal"])
        stock_over_cnt = len(df[df["status"] == "🔵 Stock Over (Excesso)"])

        if "rn_filtro_status" not in st.session_state:
            st.session_state["rn_filtro_status"] = "TODOS"

        k1, k2, k3, k4 = st.columns(4)

        if k1.button(
            f"🔴 Stock Out\n### {stock_out_cnt} SKUs", use_container_width=True
        ):
            st.session_state["rn_filtro_status"] = "🔴 Stock Out (Zerado)"

        if k2.button(
            f"🟡 Stock Low\n### {stock_low_cnt} SKUs", use_container_width=True
        ):
            st.session_state["rn_filtro_status"] = "🟡 Stock Low (Baixo)"

        if k3.button(
            f"🟢 Stock Ideal\n### {stock_ideal_cnt} SKUs",
            use_container_width=True,
        ):
            st.session_state["rn_filtro_status"] = "🟢 Stock Ideal"

        if k4.button(
            f"🔵 Stock Over\n### {stock_over_cnt} SKUs",
            use_container_width=True,
        ):
            st.session_state["rn_filtro_status"] = "🔵 Stock Over (Excesso)"

        st.divider()

        c_f1, c_f2 = st.columns([2, 1])
        busca = c_f1.text_input("🔍 Pesquisar por Código ou Nome do Produto:")
        marca_sel = c_f2.selectbox(
            "Marca:", ["TODAS"] + sorted(df["marca"].unique().tolist())
        )

        if st.session_state["rn_filtro_status"] != "TODOS":
            c_clear, _ = st.columns([1, 4])
            if c_clear.button(
                f"Limpar Filtro ({st.session_state['rn_filtro_status']})"
            ):
                st.session_state["rn_filtro_status"] = "TODOS"
                st.rerun()

        df_filtrado = df.copy()
        if st.session_state["rn_filtro_status"] != "TODOS":
            df_filtrado = df_filtrado[
                df_filtrado["status"] == st.session_state["rn_filtro_status"]
            ]

        if marca_sel != "TODAS":
            df_filtrado = df_filtrado[df_filtrado["marca"] == marca_sel]

        if busca:
            df_filtrado = df_filtrado[
                df_filtrado["cod_clean"].astype(str).str.contains(busca)
                | df_filtrado["descricao"].str.contains(busca, case=False)
            ]

        modo_view = st.radio(
            "Formato de Visualização:",
            ["📱 Cards para Celular", "📊 Tabela Comercial"],
            horizontal=True,
        )

        if "Cards" in modo_view:
            st.markdown(f"Exibindo **{len(df_filtrado)}** produtos:")
            for _, r in df_filtrado.iterrows():
                if "Stock Out" in r["status"]:
                    border_color = "#dc3545"
                    bg_badge = "#f8d7da"
                elif "Stock Low" in r["status"]:
                    border_color = "#ffc107"
                    bg_badge = "#fff3cd"
                elif "Stock Ideal" in r["status"]:
                    border_color = "#28a745"
                    bg_badge = "#d4edda"
                else:
                    border_color = "#0288d1"
                    bg_badge = "#e8f4f8"

                disp_fmt = formatar_br(r['disp'])
                pux_fmt = formatar_br(r['total_puxada'])
                proj_fmt = formatar_br(r['estoque_projetado'])

                st.markdown(
                    f"""
                    <div style="background-color: #ffffff; border: 1px solid #e0e0e0; border-left: 6px solid {border_color}; border-radius: 8px; padding: 12px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 11px; color: #666; font-weight: bold;">CÓD: {r['cod_clean']} | {r['marca']}</span>
                            <span style="font-size: 11px; font-weight: bold; background-color: {bg_badge}; padding: 3px 8px; border-radius: 12px;">{r['status']}</span>
                        </div>
                        <div style="font-size: 15px; font-weight: bold; color: #111; margin: 6px 0;">{r['descricao']}</div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; background-color: #f9f9f9; padding: 8px; border-radius: 6px;">
                            <div><b>Estoque Físico:</b> <span style="color: #0288d1; font-size: 15px; font-weight: bold;">{disp_fmt} cx</span></div>
                            <div><b>A Caminho (Puxada):</b> <span style="color: #2e7d32; font-size: 15px; font-weight: bold;">{pux_fmt} cx</span></div>
                        </div>
                        <div style="display: flex; justify-content: space-between; margin-top: 6px; font-size: 12px; color: #555;">
                            <span>Estoque Projetado: <b>{proj_fmt} cx</b></span>
                            <span>Cobertura: <b>{r['doi_atual']:.1f} dias</b></span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            cols_rn = [
                "cod_clean",
                "descricao",
                "marca",
                "tipo",
                "categoria",
                "disp",
                "linear_vendas",
                "doi_atual",
                "status",
            ]
            df_view_rn = df_filtrado[cols_rn].copy()
            df_view_rn["disp"] = df_view_rn["disp"].apply(formatar_br)
            df_view_rn["linear_vendas"] = df_view_rn["linear_vendas"].apply(formatar_br)
            df_view_rn["doi_atual"] = df_view_rn["doi_atual"].apply(lambda x: f"{x:.1f}".replace(".", ","))

            st.dataframe(
                df_view_rn,
                use_container_width=True,
            )
    else:
        st.info(
            "ℹ️ **Nenhum estoque disponível no momento.** Solicite a atualização da base em Ressuprimento."
        )


if modo_comercial:
    st.title("Grupo Lima - Portal Comercial")
    unidade = st.selectbox(
        "Selecione a Unidade Operacional:", OPERACOES_DISPONIVEIS
    )
    render_estoque_dia(unidade)
    st.stop()

if modo_visualizacao_estatica:
    st.title("Grupo Lima - Visualização Estática (Acompanhamento de Ressuprimento)")
    op_alvo = op_estatica if op_estatica else "Lima Barreiras"
    st.info(f"🔒 **Modo Somente Leitura / Visualização Exclusiva** · Operação: **{op_alvo}**")
    render_gestao_ressuprimento(op_alvo, modo_estatico=True)
    st.stop()


# 7. Autenticação e Navegação do Sistema
if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    st.title("Sistema Revenda - Grupo Lima")
    st.subheader("Autenticação Integrada")
    col1, _ = st.columns([1, 2])
    with col1:
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar", use_container_width=True):
            conn = sqlite3.connect("puxada_ambev.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, nome, perfil, permissoes_operacoes, permissoes_deptos FROM usuarios WHERE nome = ? AND senha = ?",
                (usuario, senha),
            )
            user = cursor.fetchone()
            conn.close()

            if user:
                st.session_state["logado"] = True
                st.session_state["usuario"] = user[1]
                st.session_state["perfil"] = user[2]
                st.session_state["perm_ops"] = user[3]
                st.session_state["perm_deps"] = user[4]
                st.success("Acesso autorizado!")
                st.rerun()
            else:
                st.error("Credenciais inválidas.")

else:
    st.sidebar.title("Grupo Lima")
    st.sidebar.caption(
        f"Usuário: **{st.session_state['usuario']}** | Perfil: **{st.session_state['perfil']}**"
    )

    perm_ops_raw = st.session_state.get("perm_ops", "TODAS")
    ops_disponiveis = (
        OPERACOES_DISPONIVEIS
        if perm_ops_raw == "TODAS" or st.session_state["perfil"] == "Master"
        else [o.strip() for o in perm_ops_raw.split(",") if o.strip()]
    )

    unidade = st.sidebar.selectbox("Unidade / Operação", ops_disponiveis)
    st.sidebar.divider()

    perm_deps_raw = st.session_state.get("perm_deps", "TODOS")
    deps_disponiveis = (
        DEPARTAMENTOS_DISPONIVEIS.copy()
        if perm_deps_raw == "TODOS" or st.session_state["perfil"] == "Master"
        else [d.strip() for d in perm_deps_raw.split(",") if d.strip()]
    )

    if st.session_state["perfil"] == "Master":
        deps_disponiveis.append("Acesso Master (Gestão de Usuários)")

    curr_dept = st.session_state["nav_stack"][-1]
    dept = st.sidebar.radio(
        "Departamentos Integrados",
        deps_disponiveis,
        index=deps_disponiveis.index(curr_dept)
        if curr_dept in deps_disponiveis
        else 0,
    )

    if dept != st.session_state["nav_stack"][-1]:
        navigate_to(dept)

    st.sidebar.divider()
    if st.sidebar.button("Sair do Sistema", use_container_width=True):
        st.session_state["logado"] = False
        st.session_state["nav_stack"] = ["Visão Geral (Dashboard)"]
        st.rerun()

    c_back, c_title = st.columns([1, 8])
    if len(st.session_state["nav_stack"]) > 1:
        if c_back.button("⬅️ Voltar"):
            go_back()
            st.rerun()

    c_title.title(f"{st.session_state['nav_stack'][-1]}")
    st.caption(f"Operação ativa: **{unidade}**")

    dept_atual = st.session_state["nav_stack"][-1]

    # DASHBOARD PRINCIPAL
    if "Visão Geral" in dept_atual:
        st.subheader("Painel Geral de Desempenho Operacional")

        df_est_vg = carregar_estoque_consolidado(unidade)
        p_saude, k_ok, k_rup, k_exc = calcular_saude_estoque_dpo(df_est_vg)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🏥 Saúde do Estoque DPO", f"{p_saude}%")
        m2.metric("🟢 SKUs Saudáveis", f"{k_ok}")
        m3.metric("🔴 SKUs Ruptura", f"{k_rup}")
        m4.metric("🟡 SKUs Overstock", f"{k_exc}")

    # MÓDULO PUXADA
    elif "Puxada" in dept_atual:
        sub_pux = st.tabs([
            "📁 Cadastros & Solicitação",
            "📊 Gestão Completa de Fretes",
            "📜 Histórico",
        ])

        with sub_pux[0]:
            st.markdown("### Lançamento e Solicitação de Frete")
            c1, c2, c3 = st.columns(3)
            with c1:
                origem = st.text_input("Origem (Ex: Anápolis)")
                destino = st.text_input("Destino", value=unidade)
                dt_frete = st.date_input("Data do Frete")
            with c2:
                transp = st.text_input("Transportadora")
                valor = st.number_input(
                    "Valor Negociado (R$)", min_value=0.0, step=100.0
                )
                motivo = st.selectbox(
                    "Motivo da Puxada",
                    ["Regular", "Aumento de Demanda", "Emergencial"],
                )
            with c3:
                obs = st.text_area("Observações")

            if st.button("Registrar Frete"):
                conn = sqlite3.connect("puxada_ambev.db")
                cursor = conn.cursor()
                cursor.execute(
                    """
                INSERT INTO cotacoes_frete (operacao, origem, destino, data_frete, motivo, transportadora, valor_negociado, solicitante, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        unidade,
                        origem,
                        destino,
                        str(dt_frete),
                        motivo,
                        transp,
                        valor,
                        st.session_state["usuario"],
                        obs,
                    ),
                )
                conn.commit()
                conn.close()
                st.success("Frete registrado com sucesso!")

        with sub_pux[1]:
            st.markdown("### Gestão de Aprovações e Alçadas de Frete")
            conn = sqlite3.connect("puxada_ambev.db")
            df_p = pd.read_sql_query(
                f"SELECT id, origem, destino, transportadora, valor_negociado, solicitante FROM cotacoes_frete WHERE operacao = '{unidade}' AND status = 'Pendente Aprovação'",
                conn,
            )
            conn.close()
            st.dataframe(df_p, use_container_width=True)

        with sub_pux[2]:
            st.markdown("### Histórico Geral de Fretes e Puxadas")
            conn = sqlite3.connect("puxada_ambev.db")
            df_h = pd.read_sql_query(
                f"SELECT * FROM cotacoes_frete WHERE operacao = '{unidade}'",
                conn,
            )
            conn.close()
            st.dataframe(df_h, use_container_width=True)

    # MÓDULO RESSUPRIMENTO
    elif "Ressuprimento" in dept_atual:
        sub_ress = st.tabs([
            "📁 Cadastros & Atualização de Bases",
            "📊 Gestão de Estoque",
            "🛒 Sugestão de Compra & Marcação por Dia",
            "📅 Agendamento de Descarga",
            "📈 Gestão Ressuprimento (Cestas & Metas)",
        ])

        with sub_ress[0]:
            st.markdown("### Cadastros e Atualização das Bases Ambev")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown("**1. Relatório 01.11** *(Cadastro 1x)*")
                f_01 = st.file_uploader(
                    "Upload 01.11 (Excel, Word, CSV)",
                    type=["xlsx", "xls", "docx", "csv"],
                    key="up_01",
                )
                if f_01 and st.button("Salvar 01.11"):
                    salvar_base_01_11(f_01)
                    st.success("Base 01.11 salva!")

            with c2:
                st.markdown("**2. Relatório Linear** *(A cada 3 meses)*")
                f_lin = st.file_uploader(
                    "Upload Linear (Excel, Word, CSV)",
                    type=["xlsx", "xls", "docx", "csv"],
                    key="up_lin",
                )
                if f_lin and st.button("Salvar Linear"):
                    salvar_base_linear(f_lin)
                    st.success("Base Linear salva!")

            with c3:
                st.markdown("**3. Relatório 02.03.04** *(Diário)*")
                f_02 = st.file_uploader(
                    "Upload 02.03.04 (Excel, Word, CSV)",
                    type=["xlsx", "xls", "docx", "csv"],
                    key="up_02",
                )
                if f_02 and st.button("Atualizar Estoque do Dia"):
                    salvar_base_estoque_02(f_02, unidade)
                    st.success("Estoque Diário Atualizado!")

            with c4:
                st.markdown("**4. Puxada Marcada (D0, D1, D2)**")
                f_ped = st.file_uploader(
                    "Upload Pedidos Marcados (Excel, Word, CSV)",
                    type=["xlsx", "xls", "docx", "csv"],
                    key="up_ped_d012",
                )
                if f_ped and st.button("Salvar Pedidos Marcados"):
                    salvar_pedidos_marcados(f_ped, unidade)
                    st.success("Pedidos Marcados (D0, D1, D2) atualizados!")

        with sub_ress[1]:
            render_estoque_dia(unidade)

        with sub_ress[2]:
            st.subheader("🛒 Sugestão de Compra e Marcação por Dia de Puxada")
            st.caption("Selecione o dia de puxada desejado. O sistema calcula a necessidade abatendo o estoque atual e o já marcado no relatório.")

            conn = sqlite3.connect("puxada_ambev.db")
            df_marcadas_hist = pd.read_sql_query(
                f"SELECT DISTINCT data_puxada FROM pedidos_marcados WHERE operacao='{unidade}'",
                conn,
            )
            conn.close()

            datas_existentes = []
            if not df_marcadas_hist.empty:
                for dt_str in df_marcadas_hist["data_puxada"].dropna().unique():
                    try:
                        datas_existentes.append(datetime.strptime(str(dt_str).strip(), "%d/%m/%Y").date())
                    except Exception:
                        try:
                            datas_existentes.append(datetime.strptime(str(dt_str).strip(), "%Y-%m-%d").date())
                        except Exception:
                            pass

            ultima_data_marcacao = max(datas_existentes) if datas_existentes else datetime.now().date()
            min_data_permitida = ultima_data_marcacao + timedelta(days=1)

            df_sug_agend = carregar_estoque_consolidado(unidade)

            if df_sug_agend is not None and not df_sug_agend.empty:
                c_ag1, c_ag2 = st.columns(2)
                
                data_puxada_alvo = c_ag1.date_input(
                    "Data de Puxada Alvo:",
                    value=min_data_permitida,
                    min_value=min_data_permitida
                )
                meta_doi_marcacao = c_ag2.number_input(
                    "Meta DOI Desejada para Marcação (Dias):",
                    min_value=1.0,
                    max_value=30.0,
                    value=7.0,
                    step=0.5,
                    key="meta_doi_marcacao_key"
                )

                conn = sqlite3.connect("puxada_ambev.db")
                df_tot_marc = pd.read_sql_query(
                    f"SELECT cod_clean, SUM(cx_marcadas) as total_marcado_rel FROM pedidos_marcados WHERE operacao='{unidade}' GROUP BY cod_clean",
                    conn,
                )
                conn.close()

                if not df_tot_marc.empty:
                    df_sug_agend = pd.merge(df_sug_agend, df_tot_marc, on="cod_clean", how="left")
                    df_sug_agend["total_marcado_rel"] = df_sug_agend["total_marcado_rel"].fillna(0)
                else:
                    df_sug_agend["total_marcado_rel"] = 0.0

                df_sug_agend["estoque_disponivel_e_marcado"] = df_sug_agend["disp"] + df_sug_agend["total_marcado_rel"]
                dias_proj = max(1, (data_puxada_alvo - ultima_data_marcacao).days)

                caixas_sugeridas = []
                hl_sugeridos = []
                for _, r in df_sug_agend.iterrows():
                    lin = float(r["linear_vendas"])
                    disp_marc = float(r["estoque_disponivel_e_marcado"])
                    f_hl = float(r["fator_hl"])
                    
                    consumo_projetado = lin * dias_proj
                    estoque_projetado_alvo = max(0, disp_marc - consumo_projetado)
                    
                    cx_nec = max(0, int(lin * meta_doi_marcacao - estoque_projetado_alvo))
                    caixas_sugeridas.append(cx_nec)
                    hl_sugeridos.append(round(cx_nec * f_hl, 2))

                df_sug_agend["cx_sugeridas_marcacao"] = caixas_sugeridas
                df_sug_agend["hl_sugerido"] = hl_sugeridos
                df_sug_agend["paletes_sugeridos"] = (
                    df_sug_agend["cx_sugeridas_marcacao"] / df_sug_agend["cx_pallet"]
                ).round(1)

                tot_paletes_marc = df_sug_agend["paletes_sugeridos"].sum()
                tot_cx_marc = sum(caixas_sugeridas)
                tot_hl_marc = sum(hl_sugeridos)
                skus_marc = len([n for n in caixas_sugeridas if n > 0])

                st.markdown(f"##### 📦 Resumo da Sugestão para o Dia: {data_puxada_alvo.strftime('%d/%m/%Y')} (Base: {ultima_data_marcacao.strftime('%d/%m/%Y')})")
                m_ag1, m_ag2, m_ag3, m_ag4 = st.columns(4)
                m_ag1.metric("Total Paletes Sugeridos", f"{tot_paletes_marc:,.1f} paletes".replace(".", ","))
                m_ag2.metric("Total Caixas Sugeridas", f"{formatar_br(tot_cx_marc)} cx")
                m_ag3.metric("Volume Total Sugerido", f"{tot_hl_marc:,.2f} HL".replace(".", ","))
                m_ag4.metric("SKUs para Marcar", f"{skus_marc} SKUs")

                st.divider()

                cols_ag_view = [
                    "cod_clean",
                    "descricao",
                    "marca",
                    "classe_abc",
                    "disp",
                    "total_marcado_rel",
                    "linear_vendas",
                    "doi_atual",
                    "paletes_sugeridos",
                    "cx_sugeridas_marcacao",
                    "hl_sugerido",
                ]

                df_view_ag = df_sug_agend[cols_ag_view].copy()
                df_view_ag["disp"] = df_view_ag["disp"].apply(formatar_br)
                df_view_ag["total_marcado_rel"] = df_view_ag["total_marcado_rel"].apply(formatar_br)
                df_view_ag["linear_vendas"] = df_view_ag["linear_vendas"].apply(formatar_br)
                df_view_ag["doi_atual"] = df_view_ag["doi_atual"].apply(lambda x: f"{x:.1f}".replace(".", ","))
                df_view_ag["paletes_sugeridos"] = df_view_ag["paletes_sugeridos"].apply(lambda x: f"{x:.1f}".replace(".", ","))
                df_view_ag["cx_sugeridas_marcacao"] = df_view_ag["cx_sugeridas_marcacao"].apply(formatar_br)
                df_view_ag["hl_sugerido"] = df_view_ag["hl_sugerido"].apply(lambda x: f"{x:.2f}".replace(".", ","))

                st.dataframe(
                    df_view_ag.style.map(highlight_curva_abc, subset=["classe_abc"]),
                    use_container_width=True,
                )

                st.download_button(
                    "Exportar Sugestão de Marcação (.xlsx)",
                    data=gerar_excel(df_sug_agend[cols_ag_view]),
                    file_name=f"Sugestao_Marcacao_{data_puxada_alvo.strftime('%Y%m%d')}_{unidade}.xlsx",
                )
            else:
                st.info(
                    "ℹ️ **Nenhum dado de estoque disponível.** Faça o upload das bases em Cadastros para gerar as sugestões de marcação."
                )

        with sub_ress[3]:
            st.subheader("📅 Agendamento de Descarga")
            st.caption("Cadastre os agendamentos de descarga informando Placa, Slot, Data e Tipo de Carga. Os registros aparecerão automaticamente na aba de Descarga no Armazém.")

            with st.form("form_agendamento_descarga"):
                c_d1, c_d2 = st.columns(2)
                placa_input = c_d1.text_input("Placa do Veículo (Ex: ABC-1234):")
                slot_input = c_d2.text_input("Slot de Descarga (Ex: Slot 03):")

                c_d3, c_d4 = st.columns(2)
                data_descarga_input = c_d3.date_input("Data da Descarga:")
                tipo_carga_input = c_d4.selectbox("Tipo de Carga:", ["Descartável", "Retornável"])

                obs_descarga = st.text_area("Observações da Descarga:")

                if st.form_submit_button("🚚 Salvar Agendamento de Descarga"):
                    if not placa_input.strip() or not slot_input.strip():
                        st.error("Preencha a Placa e o Slot para prosseguir.")
                    else:
                        conn = sqlite3.connect("puxada_ambev.db")
                        cursor = conn.cursor()
                        dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")
                        cursor.execute(
                            """
                            INSERT INTO agendamentos_descarga (operacao, placa, slot, data_descarga, tipo_carga, observacao, dt_atualizacao)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                unidade,
                                placa_input.strip().upper(),
                                slot_input.strip(),
                                str(data_descarga_input),
                                tipo_carga_input,
                                obs_descarga,
                                dt_now,
                            ),
                        )
                        conn.commit()
                        conn.close()
                        st.success(f"Agendamento de descarga para a placa **{placa_input.upper()}** salvo com sucesso!")
                        st.rerun()

            st.divider()
            st.markdown("##### 📋 Agendamentos de Descarga Cadastrados")
            conn = sqlite3.connect("puxada_ambev.db")
            df_descargas = pd.read_sql_query(
                f"SELECT id, placa, slot, data_descarga, tipo_carga, observacao, dt_atualizacao FROM agendamentos_descarga WHERE operacao='{unidade}' ORDER BY data_descarga DESC",
                conn,
            )
            conn.close()

            if not df_descargas.empty:
                st.dataframe(df_descargas, use_container_width=True)
            else:
                st.info("Nenhum agendamento de descarga cadastrado para esta unidade.")

        with sub_ress[4]:
            render_gestao_ressuprimento(unidade)

    # MÓDULO VENDAS
    elif "Vendas" in dept_atual:
        sub_vendas = st.tabs(["Estoque Dia", "Metas de Vendas & PNR"])

        with sub_vendas[0]:
            render_estoque_dia(unidade)

        with sub_vendas[1]:
            st.subheader("Acompanhamento de Metas de Vendas")

    # MÓDULO ARMAZÉM REVENDA (DPO)
    elif "Armazém" in dept_atual:
        st.subheader("4 - ARMAZÉM REVENDA - GESTÃO & BOOK DPO AMBEV")

        df_est_saude = carregar_estoque_consolidado(unidade)
        p_saude, k_ok, k_rup, k_exc = calcular_saude_estoque_dpo(df_est_saude)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("🏥 Saúde do Estoque DPO", f"{p_saude}%".replace(".", ","), "Meta DPO ≥ 85%")
        s2.metric("🟢 SKUs Saudáveis (DOI 3-15)", f"{k_ok} SKUs")
        s3.metric("🔴 SKUs em Risco / Ruptura (<3)", f"{k_rup} SKUs")
        s4.metric("🟡 SKUs em Excesso (>15)", f"{k_exc} SKUs")

        st.divider()

        tab_fund, tab_manter, tab_melhorar, tab_descarga_arm = st.tabs([
            "📘 FUNDAMENTOS",
            "🔄 GERENCIAR PARA MANTER",
            "🚀 GERENCIAR PARA MELHORAR",
            "🚚 ABA DE DESCARGA (PÁTIO)",
        ])

        with tab_fund:
            sec_fund = st.selectbox(
                "Selecione o Pilar de Fundamentos DPO:",
                [
                    "1 - LAYOUT E CAPACIDADE",
                    "2 - QUALIDADE",
                    "3 - ACURACIDADE",
                ],
            )

            if "1 - LAYOUT" in sec_fund:
                sub_lay = st.tabs([
                    "1.1 - Otimização do Layout (Plantas & Imagens)",
                    "1.2 - O Layout Reflete a Curva ABC",
                    "1.3 - Gestão de Capacidade do Armazém",
                ])

                with sub_lay[0]:
                    render_gestao_layouts_armazem(unidade)
                    st.divider()
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "1.1 - Otimização do Layout"
                    )

                with sub_lay[1]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "1.2 - Layout Reflete ABC"
                    )

                with sub_lay[2]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "1.3 - Gestão de Capacidade"
                    )

            elif "2 - QUALIDADE" in sec_fund:
                sub_qual = st.tabs([
                    "2.1 - Treinamentos de Qualidade",
                    "2.2 - Padrões Globais de Qualidade",
                    "2.3 - Gestão de Validade",
                    "2.4 - Políticas de Bloqueio no Armazém",
                    "2.5 - Políticas de Devolução e Qualidade",
                ])
                with sub_qual[0]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "2.1 - Treinamentos de Qualidade"
                    )
                with sub_qual[1]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "2.2 - Padrões Globais Qualidade"
                    )
                with sub_qual[2]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "2.3 - Gestão de Validade"
                    )
                with sub_qual[3]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "2.4 - Políticas de Bloqueio"
                    )
                with sub_qual[4]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "2.5 - Devoluções e Qualidade"
                    )

            elif "3 - ACURACIDADE" in sec_fund:
                sub_acu = st.tabs([
                    "3.1 - Pacote Prejuízo",
                    "3.2 - Qualidade no Armazém",
                    "3.3 - Processo de Contagem de Inventário e Resultados",
                    "3.4 - Gestão de Ativos",
                ])
                with sub_acu[0]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "3.1 - Pacote Prejuízo"
                    )
                with sub_acu[1]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "3.2 - Qualidade no Armazém"
                    )
                with sub_acu[2]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "3.3 - Inventário e IRA"
                    )
                with sub_acu[3]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Armazém", "3.4 - Gestão de Ativos"
                    )

        with tab_manter:
            sub_man = st.tabs([
                "4.1 - Política de Descarte",
                "4.2 - Repack",
                "4.3 - Gestão de Qualidade da Puxada",
            ])
            with sub_man[0]:
                render_gerenciador_padroes_dpo(
                    unidade, "Armazém", "4.1 - Política de Descarte"
                )
            with sub_man[1]:
                render_gerenciador_padroes_dpo(
                    unidade, "Armazém", "4.2 - Repack"
                )
            with sub_man[2]:
                render_gerenciador_padroes_dpo(
                    unidade, "Armazém", "4.3 - Qualidade da Puxada"
                )

        with tab_melhorar:
            sub_mel = st.tabs([
                "5.1 - Eficiência de Carga e Descarga",
                "5.2 - Processo de Picking",
                "5.3 - Gestão do WLP",
                "5.4 - Ciclo das Carretas",
            ])
            with sub_mel[0]:
                render_gerenciador_padroes_dpo(
                    unidade, "Armazém", "5.1 - Eficiência Carga e Descarga"
                )
            with sub_mel[1]:
                render_gerenciador_padroes_dpo(
                    unidade, "Armazém", "5.2 - Processo de Picking"
                )
            with sub_mel[2]:
                render_gerenciador_padroes_dpo(
                    unidade, "Armazém", "5.3 - Gestão do WLP"
                )
            with sub_mel[3]:
                render_gerenciador_padroes_dpo(
                    unidade, "Armazém", "5.4 - Ciclo das Carretas"
                )

        with tab_descarga_arm:
            st.markdown("### 🚚 Controle de Pátio e Agendamentos de Descarga")
            st.caption("Visualização em tempo real dos caminhões agendados para descarga nesta unidade.")

            conn = sqlite3.connect("puxada_ambev.db")
            df_arm_desc = pd.read_sql_query(
                f"SELECT id, placa, slot, data_descarga, tipo_carga, observacao, dt_atualizacao FROM agendamentos_descarga WHERE operacao='{unidade}' ORDER BY data_descarga ASC",
                conn,
            )
            conn.close()

            if not df_arm_desc.empty:
                st.dataframe(df_arm_desc, use_container_width=True)

                if st.button("🗑️ Excluir Agendamento de Descarga"):
                    id_exc = st.number_input("Digite o ID do agendamento para remover:", min_value=1, step=1)
                    if st.button("Confirmar Exclusão"):
                        conn = sqlite3.connect("puxada_ambev.db")
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM agendamentos_descarga WHERE id=?", (id_exc,))
                        conn.commit()
                        conn.close()
                        st.success(f"Agendamento #{id_exc} removido com sucesso!")
                        st.rerun()
            else:
                st.info("ℹ️ Nenhum agendamento de descarga pendente no momento para esta unidade.")

    # MÓDULO 6 - ENTREGA REVENDA (DISTRIBUIÇÃO)
    elif "Distribuição" in dept_atual:
        st.subheader("6 - ENTREGA REVENDA (BOOK DPO 2026)")

        tab_fund_dist, tab_manter_dist, tab_melhorar_dist = st.tabs([
            "📘 FUNDAMENTOS",
            "🔄 GERENCIAR PARA MANTER",
            "🚀 GERENCIAR PARA MELHORAR",
        ])

        with tab_fund_dist:
            sec_dist = st.selectbox(
                "Selecione o Pilar de Fundamentos (Entrega):",
                [
                    "1 - PROCESSO DE EXECUÇÃO DA ENTREGA 2026",
                    "2 - QUALIDADE NA ENTREGA 2026",
                    "3 - EQUIPES EMPODERADAS 2026",
                    "4 - SATISFAÇÃO DO CLIENTE 2026",
                ],
            )

            if "1 - PROCESSO" in sec_dist:
                sub_p1 = st.tabs([
                    "1.1 - Pré-rota",
                    "1.2 - Entrega em Rota",
                    "1.3 - Pós-rota",
                    "1.4 - Jornada",
                ])
                with sub_p1[0]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "1.1 - Pré-rota"
                    )
                with sub_p1[1]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "1.2 - Entrega em Rota"
                    )
                with sub_p1[2]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "1.3 - Pós-rota"
                    )
                with sub_p1[3]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "1.4 - Jornada"
                    )

            elif "2 - QUALIDADE" in sec_dist:
                sub_p2 = st.tabs([
                    "2.1 - Treinamentos e Padrões de Qualidade",
                    "2.2 - Reposições e Trocas",
                    "2.3 - Delivery Quality Index",
                ])
                with sub_p2[0]:
                    render_gerenciador_padroes_dpo(
                        unidade,
                        "Entrega",
                        "2.1 - Treinamentos e Padrões de Qualidade",
                    )
                with sub_p2[1]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "2.2 - Reposições e Trocas"
                    )
                with sub_p2[2]:
                    st.markdown("#### 2.3 - Delivery Quality Index (DQI)")
                    st.metric("Índice DQI Corrente", "96,5%", "Meta DPO ≥ 95%")
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "2.3 - Delivery Quality Index"
                    )

            elif "3 - EQUIPES" in sec_dist:
                sub_p3 = st.tabs([
                    "3.1 - Visibilidade de Resultados",
                    "3.2 - Processo de Feedback",
                ])
                with sub_p3[0]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "3.1 - Visibilidade de Resultados"
                    )
                with sub_p3[1]:
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "3.2 - Processo de Feedback"
                    )

            elif "4 - SATISFAÇÃO" in sec_dist:
                sub_p4 = st.tabs(
                    ["4.1 - In Full", "4.2 - On Time", "4.3 - Devolução"]
                )
                with sub_p4[0]:
                    st.metric("OTIF / In Full", "98,2%", "Meta ≥ 98,0%")
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "4.1 - In Full"
                    )
                with sub_p4[1]:
                    st.metric(
                        "On Time (Janela do Cliente)", "95,1%", "Meta ≥ 95,0%"
                    )
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "4.2 - On Time"
                    )
                with sub_p4[2]:
                    st.metric("Taxa de Devolução Rota", "1,1%", "Meta ≤ 1,5%")
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "4.3 - Devolução"
                    )

        with tab_manter_dist:
            sec_manter = st.selectbox(
                "Selecione o Pilar para Manter:",
                ["5 - NÍVEL DE SERVIÇO 2026"],
            )
            sub_p5 = st.tabs([
                "5.1 - SAC/SAV",
                "5.2 - Feedback do Motorista",
                "5.3 - Flexible Delivery",
            ])
            with sub_p5[0]:
                render_gerenciador_padroes_dpo(
                    unidade, "Entrega", "5.1 - SAC/SAV"
                )
            with sub_p5[1]:
                render_gerenciador_padroes_dpo(
                    unidade, "Entrega", "5.2 - Feedback do Motorista"
                )
            with sub_p5[2]:
                render_gerenciador_padroes_dpo(
                    unidade, "Entrega", "5.3 - Flexible Delivery"
                )

        with tab_melhorar_dist:
            sec_melhorar = st.selectbox(
                "Selecione o Pilar para Melhorar:",
                ["6 - REPUTAÇÃO 2026"],
            )
            sub_p6 = st.tabs([
                "6.1 - NPS",
                "6.2 - NPS Entrega",
                "6.3 - Rating",
            ])
            with sub_p6[0]:
                st.metric("NPS Geral", "78", "+3 vs Mês Anterior")
                render_gerenciador_padroes_dpo(unidade, "Entrega", "6.1 - NPS")
            with sub_p6[1]:
                st.metric("NPS Entrega", "84", "Zona de Excelência")
                render_gerenciador_padroes_dpo(
                    unidade, "Entrega", "6.2 - NPS Entrega"
                )
            with sub_p6[2]:
                st.metric("Rating Clientes Bees", "4,8 / 5,0")
                render_gerenciador_padroes_dpo(
                    unidade, "Entrega", "6.3 - Rating"
                )

    # MÓDULO EXCLUSIVO MASTER
    elif "Acesso Master" in dept_atual:
        st.subheader("🔑 Gestão de Usuários e Permissões")

        tab_usr1, tab_usr2 = st.tabs(
            ["➕ Cadastrar Novo Usuário", "📋 Usuários Cadastrados & Permissões"]
        )

        with tab_usr1:
            with st.form("form_cad_usuario_master"):
                c_u1, c_u2 = st.columns(2)
                novo_nome = c_u1.text_input("Nome do Usuário / Login:")
                nova_senha = c_u2.text_input("Senha Inicial:", type="password")

                c_u3, c_u4 = st.columns(2)
                novo_email = c_u3.text_input("E-mail:")
                novo_cargo = c_u4.text_input(
                    "Cargo (Ex: Gerente de Armazém, Analista):"
                )

                c_u5, c_u6 = st.columns(2)
                novo_perfil = c_u5.selectbox(
                    "Perfil de Acesso:", ["Operacional", "Master"]
                )
                e_aprov = c_u6.selectbox(
                    "É Aprovador de Fretes?", ["Não", "Sim"]
                )

                st.divider()
                st.markdown("##### 🔒 Permissões de Operação e Módulos")

                sel_ops = st.multiselect(
                    "Selecione as Unidades Operacionais Permitidas:",
                    OPERACOES_DISPONIVEIS,
                    default=OPERACOES_DISPONIVEIS,
                )
                sel_deps = st.multiselect(
                    "Selecione os Departamentos Permitidos:",
                    DEPARTAMENTOS_DISPONIVEIS,
                    default=DEPARTAMENTOS_DISPONIVEIS,
                )

                if st.form_submit_button("Criar Usuário"):
                    if novo_nome and nova_senha:
                        ops_str = (
                            "TODAS"
                            if len(sel_ops) == len(OPERACOES_DISPONIVEIS)
                            else ",".join(sel_ops)
                        )
                        deps_str = (
                            "TODOS"
                            if len(sel_deps) == len(DEPARTAMENTOS_DISPONIVEIS)
                            else ",".join(sel_deps)
                        )

                        conn = sqlite3.connect("puxada_ambev.db")
                        cursor = conn.cursor()
                        try:
                            cursor.execute(
                                """
                            INSERT INTO usuarios (nome, senha, email, cargo, perfil, e_aprovador, permissoes_operacoes, permissoes_deptos)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                                (
                                    novo_nome,
                                    nova_senha,
                                    novo_email,
                                    novo_cargo,
                                    novo_perfil,
                                    e_aprov,
                                    ops_str,
                                    deps_str,
                                ),
                            )
                            conn.commit()
                            st.success(
                                f"Usuário **{novo_nome}** cadastrado com sucesso!"
                            )
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error(
                                "Erro: Já existe um usuário com esse login!"
                            )
                        finally:
                            conn.close()

        with tab_usr2:
            conn = sqlite3.connect("puxada_ambev.db")
            df_usrs = pd.read_sql_query(
                "SELECT id, nome, email, cargo, perfil, e_aprovador, permissoes_operacoes, permissoes_deptos FROM usuarios",
                conn,
            )
            conn.close()

            st.dataframe(df_usrs, use_container_width=True)

    elif "Relatórios" in dept_atual:
        st.subheader("Base de Dados Completa para Download")
        tabela = st.selectbox(
            "Escolha a tabela:",
            [
                "base_01_11",
                "base_linear",
                "base_estoque_02",
                "pedidos_marcados",
                "cotacoes_frete",
                "historico_curva_abc",
                "padroes_dpo",
                "layout_armazem",
                "gestao_ressuprimento_diario",
                "metas_ressuprimento_mensal",
                "agendamentos_descarga",
            ],
        )
        conn = sqlite3.connect("puxada_ambev.db")
        df = pd.read_sql_query(f"SELECT * FROM {tabela}", conn)
        conn.close()
        st.dataframe(df, use_container_width=True)

    else:
        st.info(f"O módulo de **{dept_atual}** está ativo e sincronizado.")
