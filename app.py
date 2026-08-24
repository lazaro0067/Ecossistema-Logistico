from datetime import datetime
import io
import re
import sqlite3
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import pandas as pd
import streamlit as st

# 1. Configuração Inicial do Streamlit
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
]


# 2. Banco de Dados SQLite
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

    # Tabela de Pedidos Marcados Puxada (D0, D1, D2)
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


# 3. Funções Auxiliares de Leitura e Tratamento
def robust_read_csv(file_obj):
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
    df_01 = robust_read_csv(f_01)
    df_01["cod_clean"] = pd.to_numeric(df_01["Código"], errors="coerce")
    col_q = df_01.columns[16]
    df_01["fator_hl"] = (
        df_01[col_q].astype(str).str.replace(",", ".").astype(float)
    )
    df_01["cx_pallet"] = pd.to_numeric(
        df_01["Caixas Pallet"], errors="coerce"
    ).fillna(1)
    df_01["cx_pallet"] = df_01["cx_pallet"].apply(lambda x: x if x > 0 else 1)

    df_sub = df_01[["cod_clean", "Descrição", "fator_hl", "cx_pallet"]].dropna(
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
                str(r["Descrição"]),
                float(r["fator_hl"]),
                float(r["cx_pallet"]),
            ),
        )
    conn.commit()
    conn.close()


def salvar_base_linear(f_lin):
    try:
        df_lin = pd.read_excel(f_lin, sheet_name=0)
    except Exception:
        df_lin = pd.read_excel(f_lin, header=1)

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
    df_02 = robust_read_csv(f_02)

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
    df_pedidos = robust_read_csv(f_pedidos)

    col_cod_r = (
        df_pedidos.columns[17]
        if len(df_pedidos.columns) > 17
        else [c for c in df_pedidos.columns if "Código" in str(c)][0]
    )
    col_marc_w = (
        df_pedidos.columns[22]
        if len(df_pedidos.columns) > 22
        else [c for c in df_pedidos.columns if "Marcado" in str(c)][0]
    )
    col_desc = [
        c for c in df_pedidos.columns if "Produto" in str(c) or "Desc" in str(c)
    ][0]
    col_dt = [
        c for c in df_pedidos.columns if "Data Puxada" in str(c) or "Data" in str(c)
    ][0]
    col_solic = [c for c in df_pedidos.columns if "QtdeSKUs - Item" in str(c)][0]
    col_hl = [
        c for c in df_pedidos.columns if "Qtde Hecto - Item - Marcado" in str(c)
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


def carregar_pedidos_pivoted(operacao):
    conn = sqlite3.connect("puxada_ambev.db")
    df_pm = pd.read_sql_query(
        f"SELECT data_puxada, cod_clean, cx_marcadas FROM pedidos_marcados WHERE operacao='{operacao}'",
        conn,
    )
    conn.close()

    if df_pm.empty:
        return None, []

    datas_unicas = sorted(df_pm["data_puxada"].unique())

    df_grp = (
        df_pm.groupby(["cod_clean", "data_puxada"])["cx_marcadas"]
        .sum()
        .reset_index()
    )
    df_piv = (
        df_grp.pivot(
            index="cod_clean", columns="data_puxada", values="cx_marcadas"
        )
        .fillna(0)
        .reset_index()
    )

    d0_col = datas_unicas[0] if len(datas_unicas) > 0 else None
    d1_col = datas_unicas[1] if len(datas_unicas) > 1 else None
    d2_col = datas_unicas[2] if len(datas_unicas) > 2 else None

    df_piv["Puxada_D0"] = df_piv[d0_col] if d0_col else 0.0
    df_piv["Puxada_D1"] = df_piv[d1_col] if d1_col else 0.0
    df_piv["Puxada_D2"] = df_piv[d2_col] if d2_col else 0.0
    df_piv["Total_Puxada"] = (
        df_piv["Puxada_D0"] + df_piv["Puxada_D1"] + df_piv["Puxada_D2"]
    )

    return (
        df_piv[
            ["cod_clean", "Puxada_D0", "Puxada_D1", "Puxada_D2", "Total_Puxada"]
        ],
        datas_unicas,
    )


def carregar_estoque_consolidado(operacao):
    conn = sqlite3.connect("puxada_ambev.db")

    query = f"""
    SELECT 
        e.cod_clean AS Cod_clean,
        e.descricao AS Descricao,
        COALESCE(l.tipo, 'OUTROS') AS Tipo,
        COALESCE(l.categoria, 'OUTROS') AS Categoria,
        CAST(COALESCE(e.inicial, 0) AS INTEGER) AS Inicial,
        CAST(COALESCE(e.entrada, 0) AS INTEGER) AS Entrada,
        CAST(COALESCE(e.saida, 0) AS INTEGER) AS Saida,
        CAST(COALESCE(e.disponivel, 0) AS INTEGER) AS Disp,
        CAST(COALESCE(l.linear_vendas, 0) AS INTEGER) AS Linear_Vendas,
        COALESCE(b.fator_hl, 0.0) AS fator_hl,
        COALESCE(b.cx_pallet, 1.0) AS cx_pallet,
        e.dt_atualizacao AS dt_atualizacao
    FROM base_estoque_02 e
    LEFT JOIN base_01_11 b ON e.cod_clean = b.cod_clean
    LEFT JOIN base_linear l ON e.cod_clean = l.cod_clean
    WHERE e.operacao = '{operacao}'
    """

    df = pd.read_sql_query(query, conn)

    df_abc = pd.read_sql_query(
        f"""
    SELECT cod_clean, classe_abc 
    FROM historico_curva_abc 
    WHERE operacao='{operacao}' 
    AND mes_ano = (SELECT MAX(mes_ano) FROM historico_curva_abc WHERE operacao='{operacao}')
    """,
        conn,
    )
    conn.close()

    if df.empty:
        return None

    if not df_abc.empty:
        df = pd.merge(
            df, df_abc, left_on="Cod_clean", right_on="cod_clean", how="left"
        )
        df["Classe_ABC"] = df["classe_abc"].fillna("C")
        df.drop(
            columns=["cod_clean", "classe_abc"], inplace=True, errors="ignore"
        )
    else:
        df["Classe_ABC"] = "C"

    # Pedidos Marcados Puxada (D0, D1, D2)
    df_piv, datas_puxada = carregar_pedidos_pivoted(operacao)
    if df_piv is not None and not df_piv.empty:
        df = pd.merge(
            df, df_piv, left_on="Cod_clean", right_on="cod_clean", how="left"
        )
        df["Puxada_D0"] = df["Puxada_D0"].fillna(0).astype(int)
        df["Puxada_D1"] = df["Puxada_D1"].fillna(0).astype(int)
        df["Puxada_D2"] = df["Puxada_D2"].fillna(0).astype(int)
        df["Total_Puxada"] = df["Total_Puxada"].fillna(0).astype(int)
        df.drop(columns=["cod_clean"], inplace=True, errors="ignore")
    else:
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
                "Anexar/Substituir Arquivo do Padrão (.txt / .csv):",
                type=["txt", "csv"],
            )
            if file_padrao is not None:
                try:
                    cont_input = file_padrao.read().decode("utf-8")
                    st.info("Conteúdo do arquivo importado com sucesso!")
                except Exception:
                    pass

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


# 5. Navegação por Pilhas de Histórico (Botão Voltar)
if "nav_stack" not in st.session_state:
    st.session_state["nav_stack"] = ["Visão Geral (Dashboard)"]


def navigate_to(page_name):
    if st.session_state["nav_stack"][-1] != page_name:
        st.session_state["nav_stack"].append(page_name)


def go_back():
    if len(st.session_state["nav_stack"]) > 1:
        st.session_state["nav_stack"].pop()


# 6. Portal Comercial Direto (MOBILE & QR CODE)
modo_comercial = False
if "modo" in st.query_params:
    val_modo = st.query_params["modo"]
    if isinstance(val_modo, list):
        modo_comercial = "comercial" in val_modo
    else:
        modo_comercial = val_modo == "comercial"


def render_estoque_dia(unidade):
    st.subheader("Estoque Dia - Consulta Comercial em Tempo Real")

    detected_host = "localhost:8501"
    try:
        if hasattr(st, "context") and hasattr(st.context, "headers"):
            detected_host = st.context.headers.get("Host", "localhost:8501")
    except Exception:
        pass

    exp_link = st.expander("📲 Configurar e Acessar pelo Celular (Atalho / QR Code)", expanded=False)
    with exp_link:
        custom_ip = st.text_input("IP do Servidor / Rede Local (ex: 192.168.1.100:8501):", value=detected_host)
        link_web = f"http://{custom_ip}/?modo=comercial"
        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(link_web)}"
        
        c_qr1, c_qr2 = st.columns([1, 3])
        c_qr1.image(qr_code_url, caption="Aponte a câmera do celular", width=140)
        c_qr2.markdown(f"""
        🔗 **Link Direto:** <a href="{link_web}" target="_blank" style="font-size: 16px; font-weight: bold; color: #0288d1;">{link_web}</a>  
        📱 **Dica Mobile:** Ao abrir no navegador do celular, clique em **"Adicionar à Tela Inicial"** para salvar como aplicativo.
        """, unsafe_allow_html=True)

    link_web_main = f"http://{detected_host}/?modo=comercial"
    msg_wa = urllib.parse.quote(f"📲 *Estoque Dia ({unidade})*\nAcesse diretamente: {link_web_main}")
    link_whatsapp = f"https://api.whatsapp.com/send?text={msg_wa}"

    c_l1, c_l2 = st.columns([3, 1])
    c_l1.markdown(
        f"""
        <div style="background-color: #e8f4f8; padding: 12px; border-radius: 8px; border-left: 5px solid #0288d1;">
            🔗 <b>Link de Acesso Comercial:</b><br>
            <a href="{link_web_main}" target="_blank" style="font-size: 16px; font-weight: bold; color: #0288d1; text-decoration: underline;">
                🚀 Clique aqui para abrir o Estoque Dia em Nova Aba ({link_web_main})
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_l2.markdown(
        f"""
        <div style="padding-top: 10px;">
            <a href="{link_whatsapp}" target="_blank" style="background-color: #25D366; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                📲 Compartilhar no WhatsApp
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    df = carregar_estoque_consolidado(unidade)

    if df is not None and not df.empty:
        st.caption(
            f"🕒 **Última Atualização (02.03.04):** {df['dt_atualizacao'].iloc[0]}"
        )

        def get_status(doi, disp):
            if disp == 0 or doi < 1.0:
                return "🔴 Indisponível / Ruptura"
            elif doi < 3.0:
                return "🟡 Estoque Baixo"
            else:
                return "🟢 Disponível"

        df["Status"] = df.apply(
            lambda r: get_status(r["DOI_Atual"], r["Disp"]), axis=1
        )

        if "filtro_status_dia" not in st.session_state:
            st.session_state["filtro_status_dia"] = "TODOS"

        # Painel de Resumo do Estoque & Puxadas Marcadas
        m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
        m_col1.metric("SKUs Totais", f"{len(df)}")
        m_col2.metric("Estoque Físico", f"{df['Disp'].sum():,.0f} cx")
        m_col3.metric("Chegando D0", f"{df['Puxada_D0'].sum():,.0f} cx")
        m_col4.metric("Chegando D1", f"{df['Puxada_D1'].sum():,.0f} cx")
        m_col5.metric("Chegando D2", f"{df['Puxada_D2'].sum():,.0f} cx")
        m_col6.metric("Estoque Projetado", f"{df['Estoque_Projetado'].sum():,.0f} cx")

        st.divider()

        k1, k2, k3, k4 = st.columns(4)
        if k1.button(f"SKUs Totais\n\n### {len(df)}"):
            st.session_state["filtro_status_dia"] = "TODOS"
        if k2.button(
            f"Disponíveis 🟢\n\n### {len(df[df['Status'] == '🟢 Disponível'])}"
        ):
            st.session_state["filtro_status_dia"] = "🟢 Disponível"
        if k3.button(
            f"Estoque Baixo 🟡\n\n### {len(df[df['Status'] == '🟡 Estoque Baixo'])}"
        ):
            st.session_state["filtro_status_dia"] = "🟡 Estoque Baixo"
        if k4.button(
            f"Ruptura / Zerados 🔴\n\n### {len(df[df['Status'] == '🔴 Indisponível / Ruptura'])}"
        ):
            st.session_state["filtro_status_dia"] = "🔴 Indisponível / Ruptura"

        if st.session_state["filtro_status_dia"] != "TODOS":
            df_exib = df[df["Status"] == st.session_state["filtro_status_dia"]]
            st.caption(
                f"Filtro aplicado: **{st.session_state['filtro_status_dia']}**"
            )
        else:
            df_exib = df

        st.divider()

        tab_cod, tab_marca, tab_tipo, tab_cat = st.tabs(
            [
                "🔍 Pesquisa por Código / Nome",
                "🍺 Por Marca",
                "🏷️ Por Tipo",
                "📦 Por Categoria",
            ]
        )

        cols_view = [
            "Cod_clean",
            "Descricao",
            "Marca",
            "Tipo",
            "Categoria",
            "Classe_ABC",
            "Inicial",
            "Entrada",
            "Saida",
            "Disp",
            "Puxada_D0",
            "Puxada_D1",
            "Puxada_D2",
            "Total_Puxada",
            "Estoque_Projetado",
            "Estoque_HL",
            "Linear_Vendas",
            "DOI_Atual",
            "Status",
        ]

        format_dict = {
            "Inicial": "{:,.0f}",
            "Entrada": "{:,.0f}",
            "Saida": "{:,.0f}",
            "Disp": "{:,.0f}",
            "Puxada_D0": "{:,.0f}",
            "Puxada_D1": "{:,.0f}",
            "Puxada_D2": "{:,.0f}",
            "Total_Puxada": "{:,.0f}",
            "Estoque_Projetado": "{:,.0f}",
            "Linear_Vendas": "{:,.0f}",
            "Estoque_HL": "{:,.2f}",
            "DOI_Atual": "{:,.1f}",
        }

        with tab_cod:
            busca = st.text_input("Digite o Código ou Nome:")
            if busca:
                df_res = df_exib[
                    df_exib["Cod_clean"].astype(str).str.contains(busca)
                    | df_exib["Descricao"].str.contains(busca, case=False)
                ]
            else:
                df_res = df_exib

            df_styled = (
                df_res[cols_view]
                .style.map(highlight_curva_abc, subset=["Classe_ABC"])
                .format(format_dict)
            )
            st.dataframe(df_styled, use_container_width=True)
            st.download_button(
                "Exportar Tabela (.xlsx)",
                data=gerar_excel(df_res[cols_view]),
                file_name=f"Estoque_Dia_{unidade}.xlsx",
            )

        with tab_marca:
            m_sel = st.selectbox(
                "Escolha a Marca:", sorted(df_exib["Marca"].unique())
            )
            st.dataframe(
                df_exib[df_exib["Marca"] == m_sel][cols_view]
                .style.map(highlight_curva_abc, subset=["Classe_ABC"])
                .format(format_dict),
                use_container_width=True,
            )

        with tab_tipo:
            t_sel = st.selectbox(
                "Escolha o Tipo:", sorted(df_exib["Tipo"].unique())
            )
            st.dataframe(
                df_exib[df_exib["Tipo"] == t_sel][cols_view]
                .style.map(highlight_curva_abc, subset=["Classe_ABC"])
                .format(format_dict),
                use_container_width=True,
            )

        with tab_cat:
            c_sel = st.selectbox(
                "Escolha a Categoria:", sorted(df_exib["Categoria"].unique())
            )
            st.dataframe(
                df_exib[df_exib["Categoria"] == c_sel][cols_view]
                .style.map(highlight_curva_abc, subset=["Classe_ABC"])
                .format(format_dict),
                use_container_width=True,
            )
    else:
        st.info(
            "ℹ️ **Nenhum estoque sincronizado no momento.** Faça o upload em **Ressuprimento**."
        )


if modo_comercial:
    st.title("Grupo Lima - Portal Comercial de Vendas")
    unidade = st.selectbox(
        "Selecione a Unidade Operacional:",
        ["Lima Rio Verde", "Lima Barreiras", "Lima São Félix"],
    )
    render_estoque_dia(unidade)
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

    # BOTÃO NAVEGAÇÃO VOLTAR (<)
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
            "🛒 Sugestão de Compra (100% Estoque)",
            "📅 Agendamento de Pedidos (Dia da Marcação)",
        ])

        with sub_ress[0]:
            st.markdown("### Cadastros e Atualização das Bases Ambev")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown("**1. Relatório 01.11** *(Cadastro 1x)*")
                f_01 = st.file_uploader(
                    "Upload 01.11 (Cadastro/Fator Q)",
                    type=["xls", "csv"],
                    key="up_01",
                )
                if f_01 and st.button("Salvar 01.11"):
                    salvar_base_01_11(f_01)
                    st.success("Base 01.11 salva!")

            with c2:
                st.markdown("**2. Relatório Linear** *(A cada 3 meses)*")
                f_lin = st.file_uploader(
                    "Upload Linear (Vendas)", type=["xls", "xlsx"], key="up_lin"
                )
                if f_lin and st.button("Salvar Linear"):
                    salvar_base_linear(f_lin)
                    st.success("Base Linear salva!")

            with c3:
                st.markdown("**3. Relatório 02.03.04** *(Diário)*")
                f_02 = st.file_uploader(
                    "Upload 02.03.04 (Estoque Físico)",
                    type=["xls", "csv"],
                    key="up_02",
                )
                if f_02 and st.button("Atualizar Estoque do Dia"):
                    salvar_base_estoque_02(f_02, unidade)
                    st.success("Estoque Diário Atualizado!")

            with c4:
                st.markdown("**4. Puxada Marcada (D0, D1, D2)**")
                f_ped = st.file_uploader(
                    "Upload Listagem Pedidos Marcados",
                    type=["xls", "csv"],
                    key="up_ped_d012",
                )
                if f_ped and st.button("Salvar Pedidos Marcados"):
                    salvar_pedidos_marcados(f_ped, unidade)
                    st.success("Pedidos Marcados (D0, D1, D2) atualizados!")

        with sub_ress[1]:
            render_estoque_dia(unidade)

        with sub_ress[2]:
            st.subheader("🛒 Sugestão de Compra e Necessidade de Puxada")
            df_sug_compra = carregar_estoque_consolidado(unidade)

            if df_sug_compra is not None and not df_sug_compra.empty:
                c_s1, c_s2 = st.columns([1, 3])
                meta_doi_desejada = c_s1.number_input(
                    "Meta de Cobertura Desejada (Dias de Estoque):",
                    min_value=1.0,
                    max_value=30.0,
                    value=7.0,
                    step=0.5,
                )

                # Cálculo exato da necessidade de compra descontando o que já está marcado na puxada
                df_sug_compra["DOI_Projetado"] = df_sug_compra.apply(
                    lambda r: round(r["Estoque_Projetado"] / r["Linear_Vendas"], 1)
                    if r["Linear_Vendas"] > 0
                    else (999.0 if r["Estoque_Projetado"] > 0 else 0.0),
                    axis=1,
                )

                nec_caixas = []
                for _, r in df_sug_compra.iterrows():
                    lin = float(r["Linear_Vendas"])
                    tot_proj = float(r["Estoque_Projetado"])
                    nec_caixas.append(max(0, int(lin * meta_doi_desejada - tot_proj)))

                df_sug_compra["Necessidade_Compra_CX"] = nec_caixas
                df_sug_compra["Paletes_Necessarios"] = (
                    df_sug_compra["Necessidade_Compra_CX"] / df_sug_compra["cx_pallet"]
                ).round(1)

                total_cx_comprar = sum(nec_caixas)
                skus_comprar = len([n for n in nec_caixas if n > 0])

                m_c1, m_c2, m_c3 = st.columns(3)
                m_c1.metric("SKUs que Precisam de Compra", f"{skus_comprar} SKUs")
                m_c2.metric("Total de Caixas a Comprar", f"{total_cx_comprar:,.0f} cx")
                m_c3.metric(
                    "Estimativa de Paletes",
                    f"{df_sug_compra['Paletes_Necessarios'].sum():,.1f} paletes",
                )

                st.divider()

                cols_sug = [
                    "Cod_clean",
                    "Descricao",
                    "Marca",
                    "Classe_ABC",
                    "Disp",
                    "Total_Puxada",
                    "Estoque_Projetado",
                    "Linear_Vendas",
                    "DOI_Atual",
                    "DOI_Projetado",
                    "Necessidade_Compra_CX",
                    "Paletes_Necessarios",
                ]

                format_sug = {
                    "Disp": "{:,.0f}",
                    "Total_Puxada": "{:,.0f}",
                    "Estoque_Projetado": "{:,.0f}",
                    "Linear_Vendas": "{:,.0f}",
                    "DOI_Atual": "{:,.1f}",
                    "DOI_Projetado": "{:,.1f}",
                    "Necessidade_Compra_CX": "{:,.0f}",
                    "Paletes_Necessarios": "{:,.1f}",
                }

                filtro_sug = st.radio(
                    "Exibir SKUs:",
                    ["Apenas SKUs com Necessidade de Compra", "Todos os SKUs"],
                    horizontal=True,
                )

                if "Apenas" in filtro_sug:
                    df_sug_disp = df_sug_compra[df_sug_compra["Necessidade_Compra_CX"] > 0]
                else:
                    df_sug_disp = df_sug_compra

                st.dataframe(
                    df_sug_disp[cols_sug]
                    .style.map(highlight_curva_abc, subset=["Classe_ABC"])
                    .format(format_sug),
                    use_container_width=True,
                )

                st.download_button(
                    "Exportar Sugestão de Compra (.xlsx)",
                    data=gerar_excel(df_sug_disp[cols_sug]),
                    file_name=f"Sugestao_Compra_{unidade}.xlsx",
                )
            else:
                st.info("ℹ️ Atualize a base de Estoque 02.03.04 e Linear para visualizar a sugestão de compra.")

        with sub_ress[3]:
            st.subheader("📅 Agendamento e Marcação de Pedidos da Puxada")

            conn = sqlite3.connect("puxada_ambev.db")
            df_pm_raw = pd.read_sql_query(
                f"SELECT * FROM pedidos_marcados WHERE operacao='{unidade}'",
                conn,
            )
            conn.close()

            if not df_pm_raw.empty:
                datas_pux = sorted(df_pm_raw["data_puxada"].unique())

                g_col1, g_col2 = st.columns([1, 2])
                g_col1.markdown(f"**Datas de Puxada Identificadas no Anexo:** {', '.join(datas_pux)}")

                # Totais Agendados por Dia
                resumo_dias = (
                    df_pm_raw.groupby("data_puxada")
                    .agg(
                        Total_Caixas=("cx_marcadas", "sum"),
                        Total_HL=("hl_marcado", "sum"),
                        Total_Itens=("cod_clean", "nunique"),
                    )
                    .reset_index()
                )

                st.markdown("##### 📦 Resumo Agendado por Data de Puxada")
                cols_met = st.columns(len(datas_pux))
                for idx, row_d in resumo_dias.iterrows():
                    if idx < len(cols_met):
                        cols_met[idx].metric(
                            f"📅 {row_d['data_puxada']}",
                            f"{row_d['Total_Caixas']:,.0f} cx",
                            f"{row_d['Total_HL']:,.2f} HL ({row_d['Total_Itens']} SKUs)",
                        )

                st.divider()

                st.markdown("##### 📋 Listagem Detalhada de Pedidos e SKUs Marcados")
                cols_pm = [
                    "data_puxada",
                    "cod_clean",
                    "descricao",
                    "cx_solicitadas",
                    "cx_marcadas",
                    "hl_marcado",
                    "status_item",
                    "numero_pedido",
                    "dt_atualizacao",
                ]

                format_pm = {
                    "cx_solicitadas": "{:,.0f}",
                    "cx_marcadas": "{:,.0f}",
                    "hl_marcado": "{:,.2f}",
                }

                st.dataframe(
                    df_pm_raw[cols_pm].style.format(format_pm),
                    use_container_width=True,
                )

                st.download_button(
                    "Exportar Agendamento de Pedidos (.xlsx)",
                    data=gerar_excel(df_pm_raw[cols_pm]),
                    file_name=f"Agendamento_Pedidos_{unidade}.xlsx",
                )
            else:
                st.info(
                    "ℹ️ **Nenhum agendamento sincronizado.** Faça o upload do arquivo de **Puxada Marcada (Item 4)** na aba Cadastros."
                )

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
        s1.metric("🏥 Saúde do Estoque DPO", f"{p_saude}%", "Meta DPO ≥ 85%")
        s2.metric("🟢 SKUs Saudáveis (DOI 3-15)", f"{k_ok} SKUs")
        s3.metric("🔴 SKUs em Risco / Ruptura (<3)", f"{k_rup} SKUs")
        s4.metric("🟡 SKUs em Excesso (>15)", f"{k_exc} SKUs")

        st.divider()

        tab_fund, tab_manter, tab_melhorar = st.tabs([
            "📘 FUNDAMENTOS",
            "🔄 GERENCIAR PARA MANTER",
            "🚀 GERENCIAR PARA MELHORAR",
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
                    "1.1 - Otimização do Layout",
                    "1.2 - O Layout Reflete a Curva ABC",
                    "1.3 - Gestão de Capacidade do Armazém",
                ])

                with sub_lay[0]:
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
                sub_p1 = st.tabs(
                    ["1.1 - Pré-rota", "1.2 - Entrega em Rota", "1.3 - Pós-rota", "1.4 - Jornada"]
                )
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
                    st.metric("Índice DQI Corrente", "96.5%", "Meta DPO ≥ 95%")
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
                sub_p4 = st.tabs(["4.1 - In Full", "4.2 - On Time", "4.3 - Devolução"])
                with sub_p4[0]:
                    st.metric("OTIF / In Full", "98.2%", "Meta ≥ 98.0%")
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "4.1 - In Full"
                    )
                with sub_p4[1]:
                    st.metric("On Time (Janela do Cliente)", "95.1%", "Meta ≥ 95.0%")
                    render_gerenciador_padroes_dpo(
                        unidade, "Entrega", "4.2 - On Time"
                    )
                with sub_p4[2]:
                    st.metric("Taxa de Devolução Rota", "1.1%", "Meta ≤ 1.5%")
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
                render_gerenciador_padroes_dpo(
                    unidade, "Entrega", "6.1 - NPS"
                )
            with sub_p6[1]:
                st.metric("NPS Entrega", "84", "Zona de Excelência")
                render_gerenciador_padroes_dpo(
                    unidade, "Entrega", "6.2 - NPS Entrega"
                )
            with sub_p6[2]:
                st.metric("Rating Clientes Bees", "4.8 / 5.0")
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
            ],
        )
        conn = sqlite3.connect("puxada_ambev.db")
        df = pd.read_sql_query(f"SELECT * FROM {tabela}", conn)
        conn.close()
        st.dataframe(df, use_container_width=True)

    else:
        st.info(f"O módulo de **{dept_atual}** está ativo e sincronizado.")
