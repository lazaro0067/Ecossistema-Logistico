from datetime import datetime
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


# 3. Funções Auxiliares de Leitura e Tratamento (Excel, Word, CSV)
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

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        file_obj.seek(0)
        try:
            return pd.read_excel(file_obj, engine="openpyxl")
        except Exception:
            file_obj.seek(0)
            try:
                return pd.read_excel(file_obj)
            except Exception:
                file_obj.seek(0)
                try:
                    return pd.read_excel(file_obj, engine="xlrd")
                except Exception:
                    file_obj.seek(0)
                    return pd.read_excel(file_obj, header=1)

    elif filename.endswith(".docx") or filename.endswith(".doc"):
        text = read_word_file(file_obj)
        lines = [line.split("|") for line in text.split("\n") if line.strip()]
        return pd.DataFrame(lines) if lines else pd.DataFrame()

    else:
        try:
            file_obj.seek(0)
            return pd.read_csv(
                file_obj,
                sep=";",
                encoding="utf-8-sig",
                engine="python",
                on_bad_lines="skip",
            )
        except Exception:
            file_obj.seek(0)
            return pd.read_csv(
                file_obj,
                sep=";",
                encoding="latin1",
                engine="python",
                on_bad_lines="skip",
            )


def parse_br_float(val):
    if pd.isna(val):
        return 0.0
    s = str(val).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


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

    col_cod = [
        c for c in df_lin.columns if "Cód" in str(c) or "COD" in str(c)
    ][0]
    col_vendas = [c for c in df_lin.columns if "Linear" in str(c)][0]

    df_lin["cod_clean"] = pd.to_numeric(df_lin[col_cod], errors="coerce")
    df_lin["linear_vendas"] = pd.to_numeric(
        df_lin[col_vendas], errors="coerce"
    ).fillna(0)
    df_lin["Tipo"] = df_lin.get("Tipo", pd.Series()).fillna("OUTROS")
    df_lin["Categoria"] = df_lin.get("Categoria", pd.Series()).fillna("OUTROS")

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
        e.cod_clean AS Cod_clean,
        e.descricao AS Descricao,
        COALESCE(l.tipo, 'OUTROS') AS Tipo,
        COALESCE(l.categoria, 'OUTROS') AS Categoria,
        SUM(CAST(COALESCE(e.inicial, 0) AS INTEGER)) AS Inicial,
        SUM(CAST(COALESCE(e.entrada, 0) AS INTEGER)) AS Entrada,
        SUM(CAST(COALESCE(e.saida, 0) AS INTEGER)) AS Saida,
        SUM(CAST(COALESCE(e.disponivel, 0) AS INTEGER)) AS Disp,
        CAST(COALESCE(l.linear_vendas, 0) AS INTEGER) AS Linear_Vendas,
        COALESCE(b.fator_hl, 0.0) AS fator_hl,
        COALESCE(b.cx_pallet, 1.0) AS cx_pallet,
        MAX(e.dt_atualizacao) AS dt_atualizacao
    FROM base_estoque_02 e
    LEFT JOIN base_01_11 b ON e.cod_clean = b.cod_clean
    LEFT JOIN base_linear l ON e.cod_clean = l.cod_clean
    WHERE e.operacao IN ({placeholders})
    GROUP BY e.cod_clean
    """

    df = pd.read_sql_query(query, conn, params=ops_filtro)
    conn.close()

    if df.empty:
        return None

    df["Classe_ABC"] = "C"
    df["Puxada_D0"] = 0
    df["Puxada_D1"] = 0
    df["Puxada_D2"] = 0
    df["Total_Puxada"] = 0
    df["Estoque_Projetado"] = df["Disp"] + df["Total_Puxada"]

    df["DOI_Atual"] = df.apply(
        lambda r: round(r["Disp"] / r["Linear_Vendas"], 1)
        if r["Linear_Vendas"] > 0
        else (999.0 if r["Disp"] > 0 else 0.0),
        axis=1,
    )

    df["Estoque_HL"] = (df["fator_hl"] * df["Disp"]).round(2)
    df["Marca"] = df["Descricao"].apply(extract_ambev_brand)
    df["Paletes_Ocupados"] = (df["Disp"] / df["cx_pallet"]).round(1)

    return df


def calcular_saude_estoque_dpo(df):
    if df is None or df.empty:
        return 0.0, 0, 0, 0
    total_skus = len(df)
    saudaveis = len(df[(df["DOI_Atual"] >= 3.0) & (df["DOI_Atual"] <= 15.0)])
    ruptura = len(df[df["DOI_Atual"] < 3.0])
    excesso = len(df[df["DOI_Atual"] > 15.0])
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


# 4. GESTÃO DE RESSUPRIMENTO & ACOMPANHAMENTO DE PUXADA (AJUSTADO RIGOROSAMENTE ÀS COLUNAS A, C, E, F)
def render_gestao_ressuprimento(operacao):
    st.subheader(
        "📈 Gestão de Ressuprimento & Acompanhamento de Puxada (HL do Mês)"
    )

    # Mapeamento unificado para Bahia (Barreiras + São Félix)
    mapa_op_sistema = {
        "Lima Rio Verde": ["Lima - Rio Verde", "Rio Verde", "Lima Rio Verde"],
        "Lima Barreiras": ["Lima Bahia", "Barreiras", "Lima Barreiras"],
        "Lima São Félix": [
            "Lima Bahia Samavi",
            "Samavi",
            "São Félix",
            "Lima São Félix",
        ],
        "Bahia": [
            "Lima Bahia",
            "Barreiras",
            "Lima Barreiras",
            "Lima Bahia Samavi",
            "Samavi",
            "São Félix",
            "Lima São Félix",
        ],
    }

    nombres_filtro = mapa_op_sistema.get(operacao, [operacao])
    nome_exibicao_op = (
        "Bahia (Barreiras + São Félix)"
        if operacao == "Bahia"
        else operacao.replace("Lima ", "")
    )

    tab_m1, tab_m2, tab_m3, tab_m4 = st.tabs([
        "📊 Acompanhamento Mensal & HL do Mês",
        "📅 Acompanhamento de Puxada Dia a Dia",
        "⚙️ Configuração de Metas Mensais",
        "📁 Upload & Atualização da Base Diária",
    ])

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

    with tab_m1:
        c_f1, c_f2 = st.columns(2)
        ano_sel = c_f1.number_input(
            "Ano de Análise:",
            min_value=2024,
            max_value=2030,
            value=datetime.now().year,
        )
        mes_sel = c_f2.selectbox(
            "Mês de Análise:",
            list(range(1, 13)),
            format_func=lambda x: [
                "Janeiro",
                "Fevereiro",
                "Março",
                "Abril",
                "Maio",
                "Junho",
                "Julho",
                "Agosto",
                "Setembro",
                "Outubro",
                "Novembro",
                "Dezembro",
            ][x - 1],
            index=datetime.now().month - 1,
        )

        mes_ano_str = f"{['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][mes_sel-1]}/{ano_sel}"

        conn = sqlite3.connect("puxada_ambev.db")
        placeholders = ",".join(["?"] * len(nombres_filtro))
        df_diario = pd.read_sql_query(
            f"SELECT * FROM gestao_ressuprimento_diario WHERE operacao IN ({placeholders}) AND strftime('%Y', data_registro)='{ano_sel}'",
            conn,
            params=nombres_filtro,
        )
        df_metas = pd.read_sql_query(
            f"SELECT * FROM metas_ressuprimento_mensal WHERE operacao IN ({placeholders}) AND ano={ano_sel} AND mes={mes_sel}",
            conn,
            params=nombres_filtro,
        )
        conn.close()

        if not df_diario.empty:
            df_diario["data_dt"] = pd.to_datetime(
                df_diario["data_registro"], errors="coerce"
            )
            df_diario_mes = df_diario[df_diario["data_dt"].dt.month == mes_sel]

            dias_preenchidos = df_diario_mes["data_dt"].dt.date.nunique()

            if mes_sel in [1, 3, 5, 7, 8, 10, 12]:
                dias_no_mes = 31
            elif mes_sel in [4, 6, 9, 11]:
                dias_no_mes = 30
            else:
                dias_no_mes = (
                    29
                    if (
                        ano_sel % 4 == 0
                        and (ano_sel % 100 != 0 or ano_sel % 400 == 0)
                    )
                    else 28
                )

            # Somando a Coluna C (volume_sellin_hl) agrupada por cesta/indicador para descobrir o HL do mês
            df_res_mes = (
                df_diario_mes.groupby("cesta")["volume_sellin_hl"]
                .sum()
                .reset_index()
            )

            df_comp = pd.merge(
                pd.DataFrame({"cesta": cestas_ordenadas}),
                df_res_mes,
                on="cesta",
                how="left",
            ).fillna(0)

            df_comp = pd.merge(
                df_comp,
                df_metas.groupby("cesta")["meta_volume_hl"].sum().reset_index(),
                on="cesta",
                how="left",
            ).fillna(0)

            fator_tend = (
                (dias_no_mes / dias_preenchidos) if dias_preenchidos > 0 else 1.0
            )

            df_comp["INDICADOR"] = (
                df_comp["cesta"].map(cestas_map).fillna(df_comp["cesta"])
            )
            df_comp["META"] = df_comp["meta_volume_hl"]
            df_comp["HL REAL MÊS"] = df_comp["volume_sellin_hl"]
            df_comp["TEND."] = df_comp["HL REAL MÊS"] * fator_tend

            df_comp["ATING. REAL"] = df_comp.apply(
                lambda r: (r["HL REAL MÊS"] / r["META"] * 100)
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

            tot_meta = df_comp["META"].sum()
            tot_real = df_comp["HL REAL MÊS"].sum()
            tot_tend = df_comp["TEND."].sum()
            tot_ating_real = (
                (tot_real / tot_meta * 100) if tot_meta > 0 else 0.0
            )
            tot_ating_tend = (
                (tot_tend / tot_meta * 100) if tot_meta > 0 else 0.0
            )

            df_total = pd.DataFrame([{
                "INDICADOR": f"Total {nome_exibicao_op}",
                "META": tot_meta,
                "HL REAL MÊS": tot_real,
                "TEND.": tot_tend,
                "ATING. REAL": tot_ating_real,
                "ATING. TEND.": tot_ating_tend,
            }])

            st.markdown(
                f"""
                <div style="background-color: #0d2149; color: white; padding: 12px 20px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                    <h3 style="margin:0; font-size: 20px; color: white;">🔵 {nome_exibicao_op}</h3>
                    <span style="font-size: 13px; color: #b0c4de;">Somatório de HL do Mês (Coluna C) · {dias_preenchidos} dia(s) computado(s)</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            df_final = pd.concat([
                df_comp[[
                    "INDICADOR",
                    "META",
                    "HL REAL MÊS",
                    "TEND.",
                    "ATING. REAL",
                    "ATING. TEND.",
                ]],
                df_total,
            ], ignore_index=True)

            format_dict = {
                "META": "{:,.2f}",
                "HL REAL MÊS": "{:,.2f}",
                "TEND.": "{:,.2f}",
                "ATING. REAL": "{:.1f}%",
                "ATING. TEND.": "{:.1f}%",
            }

            st.dataframe(
                df_final.style.format(format_dict),
                use_container_width=True,
                height=(len(df_final) + 1) * 38 + 5,
            )
        else:
            st.info(
                f"ℹ️ Nenhum dado diário encontrado para **{nome_exibicao_op}** neste mês ({mes_ano_str})."
            )

    with tab_m2:
        st.markdown(
            f"### 📅 Acompanhamento de Puxada Dia a Dia ({nome_exibicao_op})"
        )
        if not df_diario.empty:
            df_diario["Indicador_Amigavel"] = (
                df_diario["cesta"].map(cestas_map).fillna(df_diario["cesta"])
            )
            df_piv_dia = (
                df_diario.pivot_table(
                    index="Indicador_Amigavel",
                    columns="data_registro",
                    values="volume_sellin_hl",
                    aggfunc="sum",
                )
                .fillna(0)
                .reset_index()
            )
            st.dataframe(
                df_piv_dia.style.format(formatter="{:,.2f}", na_rep="0.00"),
                use_container_width=True,
            )
        else:
            st.info("ℹ️ Sem registros diários para montar a tabela dia a dia.")

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
        mes_meta = c_m2.selectbox(
            "Mês da Meta:",
            list(range(1, 13)),
            format_func=lambda x: [
                "Janeiro",
                "Fevereiro",
                "Março",
                "Abril",
                "Maio",
                "Junho",
                "Julho",
                "Agosto",
                "Setembro",
                "Outubro",
                "Novembro",
                "Dezembro",
            ][x - 1],
            index=datetime.now().month - 1,
            key="mes_meta_key",
        )
        mes_ano_meta_str = f"{['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][mes_meta-1]}/{ano_meta}"

        conn = sqlite3.connect("puxada_ambev.db")
        df_exist_metas = pd.read_sql_query(
            f"SELECT cesta, meta_volume_hl FROM metas_ressuprimento_mensal WHERE operacao IN ({placeholders}) AND ano={ano_meta} AND mes={mes_meta}",
            conn,
            params=nombres_filtro,
        )
        conn.close()
        dict_metas_exist = (
            df_exist_metas.groupby("cesta")["meta_volume_hl"].sum().to_dict()
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
        st.markdown(
            "### 📁 Upload do Relatório Diário de Puxada / Ressuprimento"
        )
        st.caption(
            "O arquivo deve obedecer estritamente à estrutura: **Coluna A** (Operação), **Coluna C** (HL Puxado), **Coluna E** (Indicador) e **Coluna F** (Data)."
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

                # Mapeamento estrito pelas colunas solicitadas: A(0), C(2), E(4), F(5)
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
                    f"Base atualizada com sucesso! **{registros_salvos}** registros sincronizados."
                )
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar o arquivo nas colunas exigidas: {e}")


# Controle de Pilha de Navegação
if "nav_stack" not in st.session_state:
    st.session_state["nav_stack"] = ["Visão Geral (Dashboard)"]


def navigate_to(page_name):
    if st.session_state["nav_stack"][-1] != page_name:
        st.session_state["nav_stack"].append(page_name)


def go_back():
    if len(st.session_state["nav_stack"]) > 1:
        st.session_state["nav_stack"].pop()


# Portal Comercial Direto
modo_comercial = False
if "modo" in st.query_params:
    val_modo = st.query_params["modo"]
    modo_comercial = (
        "comercial" in val_modo
        if isinstance(val_modo, list)
        else val_modo == "comercial"
    )


def render_estoque_dia(unidade):
    st.subheader("📱 Portal do RN - Consulta Comercial de Vendas")
    df = carregar_estoque_consolidado(unidade)
    if df is not None and not df.empty:
        st.caption(f"🕒 **Última Atualização:** {df['dt_atualizacao'].max()}")

        def get_status(doi, disp):
            if disp == 0:
                return "🔴 Stock Out (Zerado)"
            elif doi < 3.0:
                return "🟡 Stock Low (Baixo)"
            elif doi <= 15.0:
                return "🟢 Stock Ideal"
            else:
                return "🔵 Stock Over (Excesso)"

        df["Status"] = df.apply(
            lambda r: get_status(r["DOI_Atual"], r["Disp"]), axis=1
        )
        stock_out_cnt = len(df[df["Status"] == "🔴 Stock Out (Zerado)"])
        stock_low_cnt = len(df[df["Status"] == "🟡 Stock Low (Baixo)"])
        stock_ideal_cnt = len(df[df["Status"] == "🟢 Stock Ideal"])
        stock_over_cnt = len(df[df["Status"] == "🔵 Stock Over (Excesso)"])

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
            "Marca:", ["TODAS"] + sorted(df["Marca"].unique().tolist())
        )

        df_filtrado = df.copy()
        if st.session_state["rn_filtro_status"] != "TODOS":
            df_filtrado = df_filtrado[
                df_filtrado["Status"] == st.session_state["rn_filtro_status"]
            ]
        if marca_sel != "TODAS":
            df_filtrado = df_filtrado[df_filtrado["Marca"] == marca_sel]
        if busca:
            df_filtrado = df_filtrado[
                df_filtrado["Cod_clean"].astype(str).str.contains(busca)
                | df_filtrado["Descricao"].str.contains(busca, case=False)
            ]

        for _, r in df_filtrado.iterrows():
            st.markdown(
                f"""
                <div style="background-color: #ffffff; border: 1px solid #e0e0e0; border-left: 6px solid #28a745; border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                    <div style="font-size: 11px; font-weight: bold;">CÓD: {r['Cod_clean']} | {r['Marca']} - {r['Status']}</div>
                    <div style="font-size: 15px; font-weight: bold; margin: 6px 0;">{r['Descricao']}</div>
                    <div><b>Estoque Físico:</b> {r['Disp']:,.0f} cx | <b>Cobertura:</b> {r['DOI_Atual']:.1f} dias</div>
                </div>
            """,
                unsafe_allow_html=True,
            )
    else:
        st.info("ℹ️ **Nenhum estoque disponível no momento.**")


if modo_comercial:
    st.title("Grupo Lima - Portal Comercial")
    unidade = st.selectbox(
        "Selecione a Unidade Operacional:", OPERACOES_DISPONIVEIS
    )
    render_estoque_dia(unidade)
    st.stop()


# Autenticação e Navegação do Sistema
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

    unidade = st.sidebar.selectbox("Unidade / Operação", OPERACOES_DISPONIVEIS)
    st.sidebar.divider()

    deps_disponiveis = DEPARTAMENTOS_DISPONIVEIS.copy()
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

    if "Visão Geral" in dept_atual:
        st.subheader("Painel Geral de Desempenho Operacional")
        df_est_vg = carregar_estoque_consolidado(unidade)
        p_saude, k_ok, k_rup, k_exc = calcular_saude_estoque_dpo(df_est_vg)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🏥 Saúde do Estoque DPO", f"{p_saude}%")
        m2.metric("🟢 SKUs Saudáveis", f"{k_ok}")
        m3.metric("🔴 SKUs Ruptura", f"{k_rup}")
        m4.metric("🟡 SKUs Overstock", f"{k_exc}")

    elif "Ressuprimento" in dept_atual:
        sub_ress = st.tabs([
            "📁 Cadastros & Atualização de Bases",
            "📊 Gestão de Estoque",
            "📈 Gestão Ressuprimento (Cestas & Puxada)",
        ])
        with sub_ress[0]:
            st.markdown("### Cadastros e Atualização das Bases Ambev")
            c1, c2, c3 = st.columns(3)
            with c1:
                f_01 = st.file_uploader(
                    "Upload 01.11",
                    type=["xlsx", "xls", "docx", "csv"],
                    key="up_01",
                )
                if f_01 and st.button("Salvar 01.11"):
                    salvar_base_01_11(f_01)
                    st.success("Base 01.11 salva!")
            with c2:
                f_lin = st.file_uploader(
                    "Upload Linear",
                    type=["xlsx", "xls", "docx", "csv"],
                    key="up_lin",
                )
                if f_lin and st.button("Salvar Linear"):
                    salvar_base_linear(f_lin)
                    st.success("Base Linear salva!")
            with c3:
                f_02 = st.file_uploader(
                    "Upload 02.03.04",
                    type=["xlsx", "xls", "docx", "csv"],
                    key="up_02",
                )
                if f_02 and st.button("Atualizar Estoque do Dia"):
                    salvar_base_estoque_02(
                        f_02, unidade if unidade != "Bahia" else "Lima Barreiras"
                    )
                    st.success("Estoque Atualizado!")
        with sub_ress[1]:
            render_estoque_dia(unidade)
        with sub_ress[2]:
            render_gestao_ressuprimento(unidade)

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
                "gestao_ressuprimento_diario",
                "metas_ressuprimento_mensal",
            ],
        )
        conn = sqlite3.connect("puxada_ambev.db")
        df = pd.read_sql_query(f"SELECT * FROM {tabela}", conn)
        conn.close()
        st.dataframe(df, use_container_width=True)

    else:
        st.info(f"O módulo de **{dept_atual}** está ativo e sincronizado.")
