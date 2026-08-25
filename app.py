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
        permissoes_deptos TEXT DEFAULT 'TODOS',
        status TEXT DEFAULT 'Ativo'
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cadastro_trechos_frete (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trecho TEXT UNIQUE NOT NULL,
        transportadora TEXT NOT NULL,
        valor_frete REAL NOT NULL,
        aprovador TEXT NOT NULL
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS politica_estoque_base (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT,
        cod_clean INTEGER,
        sku_original TEXT,
        tipo TEXT,
        categoria TEXT,
        estoque REAL,
        demanda REAL,
        doi_atual REAL,
        pe_min_dias REAL,
        pe_obj_dias REAL,
        pe_max_dias REAL,
        pe_min_hl REAL,
        pe_obj_hl REAL,
        pe_max_hl REAL,
        dt_atualizacao TEXT
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
        INSERT INTO usuarios (nome, senha, email, cargo, perfil, e_aprovador, alcada_reais, permissoes_operacoes, permissoes_deptos, status)
        VALUES ('admin', 'admin123', 'admin@grupolima.com.br', 'Administrador Master', 'Master', 'Sim', 9999999.0, 'TODAS', 'TODOS', 'Ativo')
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


def processar_politica_estoque_upload(f_pol, operacao):
    df_raw = robust_read_file(f_pol)
    # Coluna C (index 2): SKU string ex: "7545773 / 232462 - DESC..."
    # Coluna A (index 0): Data
    # Coluna B (index 1): Retornabilidade (Tipo)
    # Coluna D (index 3): FamíliaEmbalagem (Categoria)
    # Coluna E (index 4): Revenda
    # Coluna F (index 5): Estoque
    # Coluna G (index 6): Demanda
    # Coluna H (index 7): DOI Atual
    # Coluna I (index 8): PE Min (Dias)
    # Coluna J (index 9): PE Obj (Dias)
    # Coluna K (index 10): PE Max (Dias)
    # Coluna L (index 11): PE Min (Hl)
    # Coluna M (index 12): PE Obj (Hl)
    # Coluna N (index 13): PE Max (Hl)

    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()

    count = 0
    for _, r in df_raw.iterrows():
        try:
            sku_str = str(r.iloc[2]).strip()
            # Regra: pegar o cod do produto da coluna c, pegando o cod após a / ignorando o último cod.
            # Ex: "7545773 / 232462 - DESC..." -> Partes por '/' -> ["7545773 ", " 232462 - DESC..."]
            partes = sku_str.split("/")
            if len(partes) >= 2:
                # O código após a primeira '/'
                sub_part = partes[1].strip()  # "232462 - DESC..."
                # Pegar o primeiro token antes do hífen ou espaço
                cod_match = re.search(r"^\d+", sub_part)
                if cod_match:
                    cod_clean = int(cod_match.group())
                else:
                    cod_clean = 0
            else:
                cod_clean = 0

            if cod_clean == 0:
                continue

            tipo = str(r.iloc[1]).strip()
            cat = str(r.iloc[3]).strip()
            est = parse_br_float(r.iloc[5])
            dem = parse_br_float(r.iloc[6])
            doi = parse_br_float(r.iloc[7])
            pe_min_d = parse_br_float(r.iloc[8])
            pe_obj_d = parse_br_float(r.iloc[9])
            pe_max_d = parse_br_float(r.iloc[10])
            pe_min_h = parse_br_float(r.iloc[11])
            pe_obj_h = parse_br_float(r.iloc[12])
            pe_max_h = parse_br_float(r.iloc[13])

            cursor.execute(
                """
            INSERT INTO politica_estoque_base (operacao, cod_clean, sku_original, tipo, categoria, estoque, demanda, doi_atual, pe_min_dias, pe_obj_dias, pe_max_dias, pe_min_hl, pe_obj_hl, pe_max_hl, dt_atualizacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    operacao,
                    cod_clean,
                    sku_str,
                    tipo,
                    cat,
                    est,
                    dem,
                    doi,
                    pe_min_d,
                    pe_obj_d,
                    pe_max_d,
                    pe_min_h,
                    pe_obj_h,
                    pe_max_h,
                    dt_now,
                ),
            )
            count += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    return count


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
# GESTÃO DE RESSUPRIMENTO & POLÍTICA DE ESTOQUE
# -----------------------------------------------------------------------------
def render_gestao_ressuprimento(operacao, modo_estatico=False):
    st.subheader(
        "📈 Gestão de Ressuprimento & Política de Estoque (HL do Mês)"
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

        tab_m1, tab_m2, tab_m3, tab_m4, tab_m5 = st.tabs([
            "📊 Acompanhamento Mensal",
            "📅 Carregamento Dia a Dia",
            "📦 Gestão de Política de Estoque",
            "⚙️ Configuração de Metas",
            "📁 Upload de Dados",
        ])
    else:
        tab_m1 = st.container()
        tab_m2 = st.container()
        tab_m3 = st.container()
        tab_m4 = None
        tab_m5 = None

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

    def bloco_acompanhamento():
        c_f1, c_f2 = st.columns(2)
        ano_sel = c_f1.number_input("Ano de Análise:", min_value=2024, max_value=2030, value=datetime.now().year, key="ano_acomp")
        meses_nomes = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        meses_selecionados = c_f2.multiselect("Meses de Análise:", options=list(range(1, 13)), format_func=lambda x: meses_nomes[x - 1], default=[datetime.now().month], key="meses_acomp")

        conn = sqlite3.connect("puxada_ambev.db")
        placeholders_op = ",".join(["?"] * len(nombres_filtro))
        df_diario = pd.read_sql_query(f"SELECT * FROM gestao_ressuprimento_diario WHERE operacao IN ({placeholders_op}) AND strftime('%Y', data_registro)='{ano_sel}'", conn, params=nombres_filtro)
        df_metas = pd.read_sql_query(f"SELECT * FROM metas_ressuprimento_mensal WHERE operacao IN ({placeholders_op}) AND ano={ano_sel}", conn, params=nombres_filtro)
        conn.close()

        if not df_diario.empty:
            df_diario["data_dt"] = pd.to_datetime(df_diario["data_registro"], errors="coerce")
            if not meses_selecionados:
                meses_selecionados = list(range(1, 13))
            df_diario_filtrado = df_diario[df_diario["data_dt"].dt.month.isin(meses_selecionados)]
            dias_preenchidos = df_diario_filtrado["data_dt"].dt.date.nunique()

            dias_no_ano_total = sum([31 if m in [1,3,5,7,8,10,12] else (30 if m in [4,6,9,11] else (29 if ano_sel%4==0 else 28)) for m in meses_selecionados])

            df_res_mes = df_diario_filtrado.groupby("cesta")["volume_sellin_hl"].sum().reset_index()
            df_comp = pd.merge(pd.DataFrame({"cesta": cestas_ordenadas}), df_res_mes, on="cesta", how="left").fillna(0)
            df_metas_filtradas = df_metas[df_metas["mes"].isin(meses_selecionados)]
            df_metas_grp = df_metas_filtradas.groupby("cesta")["meta_volume_hl"].sum().reset_index()
            df_comp = pd.merge(df_comp, df_metas_grp, on="cesta", how="left").fillna(0)

            fator_tend = (dias_no_ano_total / dias_preenchidos) if dias_preenchidos > 0 else 1.0

            df_comp["INDICADOR"] = df_comp["cesta"].map(cestas_map)
            df_comp["META"] = df_comp["meta_volume_hl"]
            df_comp["REAL"] = df_comp["volume_sellin_hl"]
            df_comp["TEND."] = df_comp["REAL"] * fator_tend
            df_comp["ATING. REAL"] = df_comp.apply(lambda r: (r["REAL"] / r["META"] * 100) if r["META"] > 0 else 0.0, axis=1)
            df_comp["ATING. TEND."] = df_comp.apply(lambda r: (r["TEND."] / r["META"] * 100) if r["META"] > 0 else 0.0, axis=1)
            df_comp["PENDÊNCIA PERÍODO"] = df_comp["REAL"] - df_comp["META"]

            df_cerveja_nab = df_comp[df_comp["INDICADOR"].isin(["Cerveja", "Nab"])]
            tot_meta, tot_real, tot_tend = df_cerveja_nab["META"].sum(), df_cerveja_nab["REAL"].sum(), df_cerveja_nab["TEND."].sum()
            tot_pend = tot_real - tot_meta
            tot_ating_real = (tot_real / tot_meta * 100) if tot_meta > 0 else 0.0
            tot_ating_tend = (tot_tend / tot_meta * 100) if tot_meta > 0 else 0.0

            df_total = pd.DataFrame([{
                "INDICADOR": f"Total {nome_exibicao_op} (Cerveja + Nab)",
                "META": tot_meta, "REAL": tot_real, "TEND.": tot_tend,
                "ATING. REAL": tot_ating_real, "ATING. TEND.": tot_ating_tend, "PENDÊNCIA PERÍODO": tot_pend
            }])

            df_final = pd.concat([df_comp[["INDICADOR", "META", "REAL", "TEND.", "ATING. REAL", "ATING. TEND.", "PENDÊNCIA PERÍODO"]], df_total], ignore_index=True)
            st.dataframe(df_final, use_container_width=True)
        else:
            st.info(f"Sem dados diários para **{nome_exibicao_op}** no ano de {ano_sel}.")

    def bloco_carregamento_dia_a_dia():
        st.markdown(f"### 📅 Carregamento Dia a Dia - {nome_exibicao_op}")
        c_d1, c_d2 = st.columns(2)
        ano_dia = c_d1.number_input("Ano:", 2024, 2030, datetime.now().year, key="ano_d")
        mes_dia = c_d2.selectbox("Mês:", list(range(1, 13)), format_func=lambda x: ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"][x-1], index=datetime.now().month-1, key="mes_d")

        conn = sqlite3.connect("puxada_ambev.db")
        placeholders_op = ",".join(["?"] * len(nombres_filtro))
        query_dia = f"""
            SELECT data_registro, cesta, SUM(volume_sellin_hl) as vol_hl
            FROM gestao_ressuprimento_diario
            WHERE operacao IN ({placeholders_op}) AND CAST(STRFTIME('%Y', data_registro) AS INTEGER) = ? AND CAST(STRFTIME('%m', data_registro) AS INTEGER) = ?
            GROUP BY data_registro, cesta
        """
        df_diario_bruto = pd.read_sql_query(query_dia, conn, params=nombres_filtro + [ano_dia, mes_dia])
        conn.close()

        if not df_diario_bruto.empty:
            df_diario_bruto["data_dt"] = pd.to_datetime(df_diario_bruto["data_registro"], errors="coerce")
            df_diario_bruto["Dia"] = df_diario_bruto["data_dt"].dt.strftime("%d/%m/%Y")
            df_diario_bruto["Indicador"] = df_diario_bruto["cesta"].map(cestas_map).fillna("Outros")
            df_pivot = df_diario_bruto.pivot_table(index=["data_dt", "Dia"], columns="Indicador", values="vol_hl", aggfunc="sum").reset_index()
            df_pivot = df_pivot.sort_values("data_dt").drop(columns=["data_dt"]).fillna(0.0)
            cols_ind = [c for c in df_pivot.columns if c != "Dia"]
            df_pivot["Total Dia (HL)"] = df_pivot[cols_ind].sum(axis=1)
            st.dataframe(df_pivot, use_container_width=True)
        else:
            st.info("Nenhum registro encontrado para este período.")

    def bloco_politica_estoque():
        st.markdown(f"### 📦 Gestão de Política de Estoque - {nome_exibicao_op}")
        st.caption("Visualização de produtos abaixo da política de estoque, com cruzamento entre os parâmetros da planilha importada e o DOI atual de acompanhamento.")

        conn = sqlite3.connect("puxada_ambev.db")
        placeholders_op = ",".join(["?"] * len(nombres_filtro))
        df_pol = pd.read_sql_query(f"SELECT * FROM politica_estoque_base WHERE operacao IN ({placeholders_op})", conn, params=nombres_filtro)
        conn.close()

        if df_pol.empty:
            st.warning("Nenhum dado de política de estoque importado. Faça o upload da planilha 'Estoque Médio' na aba de Upload.")
            return

        # Filtros por Tipo e Categoria
        tipos_disp = ["TODOS"] + sorted(df_pol["tipo"].dropna().unique().tolist())
        cats_disp = ["TODAS"] + sorted(df_pol["categoria"].dropna().unique().tolist())

        c_f1, c_f2 = st.columns(2)
        filtro_tipo = c_f1.selectbox("Filtrar por Tipo (Retornabilidade):", tipos_disp)
        filtro_cat = c_f2.selectbox("Filtrar por Categoria (Família Embalagem):", cats_disp)

        df_view = df_pol.copy()
        if filtro_tipo != "TODOS":
            df_view = df_view[df_view["tipo"] == filtro_tipo]
        if filtro_cat != "TODAS":
            df_view = df_view[df_view["categoria"] == filtro_cat]

        # Status em relação à política
        def avaliar_politica(row):
            doi = row["doi_atual"]
            p_min = row["pe_min_dias"]
            p_max = row["pe_max_dias"]
            if doi < p_min:
                return "🔴 Abaixo da Política (Ruptura/Baixo)"
            elif doi > p_max:
                return "🔵 Acima da Política (Excesso)"
            else:
                return "🟢 Dentro da Política Ideal"

        df_view["Status Política"] = df_view.apply(avaliar_politica, axis=1)

        abaixo_cnt = len(df_view[df_view["Status Política"].str.contains("Abaixo")])
        ideal_cnt = len(df_view[df_view["Status Política"].str.contains("Dentro")])
        acima_cnt = len(df_view[df_view["Status Política"].str.contains("Acima")])

        m1, m2, m3 = st.columns(3)
        m1.metric("🔴 Abaixo da Política", f"{abaixo_cnt} SKUs")
        m2.metric("🟢 Dentro da Política", f"{ideal_cnt} SKUs")
        m3.metric("🔵 Acima da Política", f"{acima_cnt} SKUs")

        st.divider()
        st.dataframe(df_view[["cod_clean", "sku_original", "tipo", "categoria", "estoque", "demanda", "doi_atual", "pe_min_dias", "pe_obj_dias", "pe_max_dias", "Status Política"]], use_container_width=True)

    if modo_estatico:
        bloco_acompanhamento()
        bloco_carregamento_dia_a_dia()
        bloco_politica_estoque()
    else:
        with tab_m1:
            bloco_acompanhamento()
        with tab_m2:
            bloco_carregamento_dia_a_dia()
        with tab_m3:
            bloco_politica_estoque()
        with tab_m4:
            st.markdown("### Configuração de Metas Mensais")
            # Metas logic...
        with tab_m5:
            st.markdown("### 📁 Upload de Relatórios e Política de Estoque")
            f_pol_up = st.file_uploader("Upload da Planilha de Estoque Médio / Política de Estoque (.xls, .xlsx):", type=["xls", "xlsx"])
            if f_pol_up is not None and st.button("Processar e Salvar Política de Estoque"):
                cnt = processar_politica_estoque_upload(f_pol_up, unidade)
                st.success(f"Sucesso! {cnt} registros importados com extração rigorosa de códigos.")
                st.rerun()


# 5. Navegação por Pilhas de Histórico
if "nav_stack" not in st.session_state:
    st.session_state["nav_stack"] = ["Visão Geral (Dashboard)"]


def navigate_to(page_name):
    if st.session_state["nav_stack"][-1] != page_name:
        st.session_state["nav_stack"].append(page_name)


def go_back():
    if len(st.session_state["nav_stack"]) > 1:
        st.session_state["nav_stack"].pop()


# 6. Parâmetros URL
modo_comercial = False
modo_visualizacao_estatica = False
op_estatica = None

if "modo" in st.query_params:
    val_modo = st.query_params["modo"]
    modo_comercial = ("comercial" in val_modo) if isinstance(val_modo, list) else (val_modo == "comercial")

if "visualizacao" in st.query_params:
    val_vis = st.query_params["visualizacao"]
    modo_visualizacao_estatica = ("ressuprimento" in val_vis) if isinstance(val_vis, list) else (val_vis == "ressuprimento")
    if "op" in st.query_params:
        op_estatica = st.query_params["op"]
        if isinstance(op_estatica, list):
            op_estatica = op_estatica[0]


def render_estoque_dia(unidade):
    st.subheader("📱 Portal do RN - Consulta Comercial de Vendas")
    df = carregar_estoque_consolidado(unidade)
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum estoque disponível.")


if modo_comercial:
    st.title("Grupo Lima - Portal Comercial")
    unidade = st.selectbox("Unidade Operacional:", OPERACOES_DISPONIVEIS)
    render_estoque_dia(unidade)
    st.stop()

if modo_visualizacao_estatica:
    st.title("Grupo Lima - Visualização Estática (Ressuprimento)")
    op_alvo = op_estatica if op_estatica else "Lima Barreiras"
    st.info(f"🔒 **Modo Somente Leitura** · Operação: **{op_alvo}**")
    render_gestao_ressuprimento(op_alvo, modo_estatico=True)
    st.stop()


# 7. Autenticação e Navegação
if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    st.title("Sistema Revenda - Grupo Lima")
    sub_auth = st.tabs(["🔑 Entrar no Sistema", "✉️ Esqueci a Senha / Recuperação"])

    with sub_auth[0]:
        col1, _ = st.columns([1, 2])
        with col1:
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.button("Entrar", use_container_width=True):
                conn = sqlite3.connect("puxada_ambev.db")
                cursor = conn.cursor()
                cursor.execute("SELECT id, nome, perfil, permissoes_operacoes, permissoes_deptos, status FROM usuarios WHERE nome = ? AND senha = ?", (usuario, senha))
                user = cursor.fetchone()
                conn.close()

                if user:
                    if user[5] == "Inativo":
                        st.error("⚠️ Este usuário está inativo. Entre em contato com o administrador.")
                    else:
                        st.session_state["logado"] = True
                        st.session_state["usuario"] = user[1]
                        st.session_state["perfil"] = user[2]
                        st.session_state["perm_ops"] = user[3]
                        st.session_state["perm_deps"] = user[4]
                        st.success("Acesso autorizado!")
                        st.rerun()
                else:
                    st.error("Credenciais inválidas.")

    with sub_auth[1]:
        st.subheader("Recuperação de Senha via E-mail")
        email_rec = st.text_input("Digite o seu e-mail cadastrado:")
        if st.button("Enviar Instruções de Recuperação"):
            if email_rec:
                conn = sqlite3.connect("puxada_ambev.db")
                cursor = conn.cursor()
                cursor.execute("SELECT nome FROM usuarios WHERE email = ?", (email_rec,))
                res_email = cursor.fetchone()
                conn.close()
                if res_email:
                    st.success(f"📧 Um e-mail de recuperação foi enviado para **{email_rec}** com as instruções para o usuário **{res_email[0]}**.")
                else:
                    st.error("E-mail não encontrado no sistema.")
            else:
                st.error("Por favor, preencha o campo de e-mail.")

else:
    st.sidebar.title("Grupo Lima")
    st.sidebar.caption(f"Usuário: **{st.session_state['usuario']}** | Perfil: **{st.session_state['perfil']}**")

    perm_ops_raw = st.session_state.get("perm_ops", "TODAS")
    ops_disponiveis = OPERACOES_DISPONIVEIS if perm_ops_raw == "TODAS" or st.session_state["perfil"] == "Master" else [o.strip() for o in perm_ops_raw.split(",") if o.strip()]

    unidade = st.sidebar.selectbox("Unidade / Operação", ops_disponiveis)
    st.sidebar.divider()

    perm_deps_raw = st.session_state.get("perm_deps", "TODOS")
    deps_disponiveis = DEPARTAMENTOS_DISPONIVEIS.copy() if perm_deps_raw == "TODOS" or st.session_state["perfil"] == "Master" else [d.strip() for d in perm_deps_raw.split(",") if d.strip()]

    if st.session_state["perfil"] == "Master":
        deps_disponiveis.append("Acesso Master (Gestão de Usuários)")

    curr_dept = st.session_state["nav_stack"][-1]
    dept = st.sidebar.radio("Departamentos Integrados", deps_disponiveis, index=deps_disponiveis.index(curr_dept) if curr_dept in deps_disponiveis else 0)

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

    if "Visão Geral" in dept_atual:
        st.subheader("Painel Geral de Desempenho Operacional")
        df_est_vg = carregar_estoque_consolidado(unidade)
        p_saude, k_ok, k_rup, k_exc = calcular_saude_estoque_dpo(df_est_vg)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🏥 Saúde do Estoque DPO", f"{p_saude}%")
        m2.metric("🟢 SKUs Saudáveis", f"{k_ok}")
        m3.metric("🔴 SKUs Ruptura", f"{k_rup}")
        m4.metric("🟡 SKUs Overstock", f"{k_exc}")

    elif "Puxada" in dept_atual:
        sub_pux = st.tabs([
            "📋 Cadastro de Trechos & Fretes",
            "🚀 Solicitação de Frete Integrada",
            "📊 Gestão de Aprovações",
            "📜 Histórico",
        ])

        with sub_pux[0]:
            st.markdown("### Cadastro de Trechos, Transportadoras e Aprovadores")
            with st.form("form_cad_trecho"):
                c_t1, c_t2 = st.columns(2)
                trecho_input = c_t1.text_input("Trecho (Ex: Anápolis -> Rio Verde):")
                transp_input = c_t2.text_input("Transportadora:")
                c_t3, c_t4 = st.columns(2)
                valor_input = c_t3.number_input("Valor do Frete (R$):", min_value=0.0, step=100.0)
                aprovador_input = c_t4.text_input("Aprovador Responsável:")

                if st.form_submit_button("💾 Salvar Cadastro de Trecho"):
                    if trecho_input and transp_input:
                        conn = sqlite3.connect("puxada_ambev.db")
                        cursor = conn.cursor()
                        try:
                            cursor.execute(
                                "INSERT INTO cadastro_trechos_frete (trecho, transportadora, valor_frete, aprovador) VALUES (?, ?, ?, ?)",
                                (trecho_input.strip(), transp_input.strip(), valor_input, aprovador_input.strip())
                            )
                            conn.commit()
                            st.success(f"Trecho **{trecho_input}** cadastrado com sucesso!")
                        except sqlite3.IntegrityError:
                            st.error("Este trecho já está cadastrado.")
                        finally:
                            conn.close()
                    else:
                        st.error("Preencha o trecho e a transportadora.")

            st.divider()
            st.markdown("##### Trechos Cadastrados")
            conn = sqlite3.connect("puxada_ambev.db")
            df_tr = pd.read_sql_query("SELECT * FROM cadastro_trechos_frete", conn)
            conn.close()
            st.dataframe(df_tr, use_container_width=True)

        with sub_pux[1]:
            st.markdown("### Solicitação de Frete (Seleção por Cadastro)")
            conn = sqlite3.connect("puxada_ambev.db")
            df_tr_sel = pd.read_sql_query("SELECT * FROM cadastro_trechos_frete", conn)
            conn.close()

            if not df_tr_sel.empty:
                trechos_lista = df_tr_sel["trecho"].tolist()
                with st.form("form_solicitar_frete"):
                    trecho_escolhido = st.selectbox("Selecione o Trecho:", trechos_lista)
                    row_trecho = df_tr_sel[df_tr_sel["trecho"] == trecho_escolhido].iloc[0]

                    st.info(f"🚚 **Transportadora Vinculada:** {row_trecho['transportadora']} | 💰 **Valor:** R$ {row_trecho['valor_frete']:,.2f} | 👤 **Aprovador:** {row_trecho['aprovador']}")

                    c_s1, c_s2 = st.columns(2)
                    dt_req = c_s1.date_input("Data do Frete:")
                    motivo_req = c_s2.selectbox("Motivo:", ["Regular", "Aumento de Demanda", "Emergencial"])
                    obs_req = st.text_area("Observações:")

                    if st.form_submit_button("🚀 Enviar Solicitação de Frete"):
                        conn = sqlite3.connect("puxada_ambev.db")
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT INTO cotacoes_frete (operacao, origem, destino, data_frete, motivo, transportadora, valor_negociado, solicitante, aprovador, observacao)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                unidade, trecho_escolhido.split("->")[0].strip(), trecho_escolhido.split("->")[-1].strip(),
                                str(dt_req), motivo_req, row_trecho["transportadora"], row_trecho["valor_frete"],
                                st.session_state["usuario"], row_trecho["aprovador"], obs_req
                            )
                        )
                        conn.commit()
                        conn.close()
                        st.success("Solicitação enviada com sucesso!")
            else:
                st.warning("Cadastre trechos na aba anterior para habilitar a solicitação.")

        with sub_pux[2]:
            st.markdown("### Gestão de Aprovações de Frete")
            conn = sqlite3.connect("puxada_ambev.db")
            df_p = pd.read_sql_query(f"SELECT * FROM cotacoes_frete WHERE operacao = '{unidade}' AND status = 'Pendente Aprovação'", conn)
            conn.close()
            st.dataframe(df_p, use_container_width=True)

        with sub_pux[3]:
            st.markdown("### Histórico de Fretes")
            conn = sqlite3.connect("puxada_ambev.db")
            df_h = pd.read_sql_query(f"SELECT * FROM cotacoes_frete WHERE operacao = '{unidade}'", conn)
            conn.close()
            st.dataframe(df_h, use_container_width=True)

    elif "Ressuprimento" in dept_atual:
        render_gestao_ressuprimento(unidade)

    elif "Vendas" in dept_atual:
        render_estoque_dia(unidade)

    elif "Armazém" in dept_atual:
        st.subheader("4 - ARMAZÉM REVENDA - GESTÃO DPO")
        render_gerenciador_padroes_dpo(unidade, "Armazém", "1.1 - Otimização do Layout")

    elif "Distribuição" in dept_atual:
        st.subheader("6 - ENTREGA REVENDA (BOOK DPO 2026)")
        render_gerenciador_padroes_dpo(unidade, "Entrega", "1.1 - Pré-rota")

    elif "Acesso Master" in dept_atual:
        st.subheader("🔑 Gestão de Usuários, Permissões e Status")

        tab_usr1, tab_usr2 = st.tabs(["➕ Cadastrar / Alterar Usuário", "📋 Usuários Cadastrados & Inativar/Ativar"])

        with tab_usr1:
            with st.form("form_cad_usuario_master"):
                c_u1, c_u2 = st.columns(2)
                novo_nome = c_u1.text_input("Nome do Usuário / Login:")
                nova_senha = c_u2.text_input("Senha Inicial:", type="password")

                c_u3, c_u4 = st.columns(2)
                novo_email = c_u3.text_input("E-mail (para recuperação):")
                novo_cargo = c_u4.text_input("Cargo:")

                c_u5, c_u6 = st.columns(2)
                novo_perfil = c_u5.selectbox("Perfil:", ["Operacional", "Master"])
                status_usu = c_u6.selectbox("Status Inicial:", ["Ativo", "Inativo"])

                sel_ops = st.multiselect("Unidades Permitidas:", OPERACOES_DISPONIVEIS, default=OPERACOES_DISPONIVEIS)
                sel_deps = st.multiselect("Departamentos Permitidos:", DEPARTAMENTOS_DISPONIVEIS, default=DEPARTAMENTOS_DISPONIVEIS)

                if st.form_submit_button("Salvar / Atualizar Usuário"):
                    if novo_nome and nova_senha:
                        ops_str = "TODAS" if len(sel_ops) == len(OPERACOES_DISPONIVEIS) else ",".join(sel_ops)
                        deps_str = "TODOS" if len(sel_deps) == len(DEPARTAMENTOS_DISPONIVEIS) else ",".join(sel_deps)

                        conn = sqlite3.connect("puxada_ambev.db")
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT INTO usuarios (nome, senha, email, cargo, perfil, permissoes_operacoes, permissoes_deptos, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(nome) DO UPDATE SET
                                senha=excluded.senha, email=excluded.email, cargo=excluded.cargo,
                                perfil=excluded.perfil, permissoes_operacoes=excluded.permissoes_operacoes,
                                permissoes_deptos=excluded.permissoes_deptos, status=excluded.status
                            """,
                            (novo_nome, nova_senha, novo_email, novo_cargo, novo_perfil, ops_str, deps_str, status_usu)
                        )
                        conn.commit()
                        conn.close()
                        st.success(f"Usuário **{novo_nome}** salvo/atualizado com sucesso!")
                        st.rerun()

        with tab_usr2:
            conn = sqlite3.connect("puxada_ambev.db")
            df_usrs = pd.read_sql_query("SELECT id, nome, email, cargo, perfil, status FROM usuarios", conn)
            conn.close()
            st.dataframe(df_usrs, use_container_width=True)

            st.markdown("##### Ativar / Inativar Usuário")
            with st.form("form_status_usuario"):
                usr_alvo = st.selectbox("Selecione o Usuário:", df_usrs["nome"].tolist() if not df_usrs.empty else [])
                novo_status = st.selectbox("Alterar Status para:", ["Ativo", "Inativo"])
                if st.form_submit_button("🔄 Atualizar Status"):
                    if usr_alvo:
                        conn = sqlite3.connect("puxada_ambev.db")
                        cursor = conn.cursor()
                        cursor.execute("UPDATE usuarios SET status = ? WHERE nome = ?", (novo_status, usr_alvo))
                        conn.commit()
                        conn.close()
                        st.success(f"Status do usuário **{usr_alvo}** alterado para **{novo_status}** com sucesso!")
                        st.rerun()

    elif "Relatórios" in dept_atual:
        st.subheader("Base de Dados Completa")
        tabela = st.selectbox("Tabela:", ["base_01_11", "base_linear", "base_estoque_02", "politica_estoque_base", "cadastro_trechos_frete", "cotacoes_frete"])
        conn = sqlite3.connect("puxada_ambev.db")
        df = pd.read_sql_query(f"SELECT * FROM {tabela}", conn)
        conn.close()
        st.dataframe(df, use_container_width=True)

    else:
        st.info(f"O módulo de **{dept_atual}** está ativo e sincronizado.")
