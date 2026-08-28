from datetime import datetime, timedelta
import io
import re
import sqlite3
import pandas as pd
import streamlit as st

# Importação condicional do docx para evitar falhas no Streamlit Cloud
try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# 1. Configuração Inicial da Página & Design System Sênior CSS
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

# 2. Inicialização do Banco de Dados SQLite e Migrações Seguras
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
        data_registro TEXT,
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

    colunas_para_verificar = [
        ("perfil", "TEXT DEFAULT 'Operacional'"),
        ("permissoes_operacoes", "TEXT DEFAULT 'TODAS'"),
        ("permissoes_deptos", "TEXT DEFAULT 'TODOS'"),
        ("status", "TEXT DEFAULT 'Ativo'"),
        ("email", "TEXT"),
        ("cargo", "TEXT"),
        ("e_aprovador", "TEXT DEFAULT 'Não'"),
    ]
    for col_nome, col_tipo in colunas_para_verificar:
        try:
            cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {col_nome} {col_tipo}")
        except Exception:
            pass

    cursor.execute("SELECT count(*) FROM usuarios WHERE nome = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO usuarios (nome, senha, email, cargo, perfil, e_aprovador, alcada_reais, permissoes_operacoes, permissoes_deptos, status)
        VALUES ('admin', 'admin123', 'admin@grupolima.com.br', 'Administrador Master', 'Master', 'Sim', 9999999.0, 'TODAS', 'TODOS', 'Ativo')
        """)

    conn.commit()
    conn.close()

init_db()

# 3. Funções Auxiliares e de Salvamento de Bases
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

def formatar_inteiro_br(val):
    try:
        if pd.isna(val): return "0"
        val_int = int(round(float(val)))
        return f"{val_int:,}".replace(",", ".")
    except Exception:
        return str(val)

def gerar_excel(df):
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Dados")
    except Exception:
        df.to_csv(output, index=False, sep=";")
    return output.getvalue()

def gerar_csv(df):
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")

def render_botoes_download(df_export, nome_base):
    c_dl1, c_dl2 = st.columns(2)
    c_dl1.download_button(
        f"📥 Baixar {nome_base} (.xlsx)",
        data=gerar_excel(df_export),
        file_name=f"{nome_base}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    c_dl2.download_button(
        f"📥 Baixar {nome_base} (.csv)",
        data=gerar_csv(df_export),
        file_name=f"{nome_base}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

def salvar_base_01_11(f_01):
    df_01 = robust_read_file(f_01)
    col_cod = [c for c in df_01.columns if "Código" in str(c) or "Cod" in str(c)][0]
    df_01["cod_clean"] = pd.to_numeric(df_01[col_cod], errors="coerce")
    col_q = df_01.columns[16] if len(df_01.columns) > 16 else df_01.columns[-1]
    df_01["fator_hl"] = df_01[col_q].astype(str).str.replace(",", ".").astype(float)
    col_cx = [c for c in df_01.columns if "Caixas Pallet" in str(c) or "Pallet" in str(c)]
    df_01["cx_pallet"] = pd.to_numeric(df_01[col_cx[0]], errors="coerce").fillna(1) if col_cx else 1.0
    col_desc = [c for c in df_01.columns if "Descrição" in str(c) or "Desc" in str(c)][0]
    df_sub = df_01[["cod_clean", col_desc, "fator_hl", "cx_pallet"]].dropna(subset=["cod_clean"])

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    for _, r in df_sub.iterrows():
        cursor.execute("""
            INSERT INTO base_01_11 (cod_clean, descricao, fator_hl, cx_pallet)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cod_clean) DO UPDATE SET
                descricao=excluded.descricao, fator_hl=excluded.fator_hl, cx_pallet=excluded.cx_pallet
        """, (int(r["cod_clean"]), str(r[col_desc]), float(r["fator_hl"]), float(r["cx_pallet"])))
    conn.commit()
    conn.close()

def salvar_base_linear(f_lin):
    df_lin = robust_read_file(f_lin)
    col_cod = df_lin.columns[0]
    for i, c in enumerate(df_lin.columns):
        if "cód" in str(c).lower() or "cod" in str(c).lower():
            col_cod = df_lin.columns[i]
            break
    col_vendas = df_lin.columns[4] if len(df_lin.columns) > 4 else df_lin.columns[1]
    df_lin["cod_clean"] = pd.to_numeric(df_lin[col_cod], errors="coerce")
    df_lin["linear_vendas"] = df_lin[col_vendas].apply(parse_br_float)
    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    for _, r in df_lin.dropna(subset=["cod_clean"]).iterrows():
        cursor.execute("""
            INSERT INTO base_linear (cod_clean, tipo, categoria, linear_vendas, dt_atualizacao)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cod_clean) DO UPDATE SET
                linear_vendas=excluded.linear_vendas, dt_atualizacao=excluded.dt_atualizacao
        """, (int(r["cod_clean"]), "CERVEJA", "Geral", float(r["linear_vendas"]), dt_now))
    conn.commit()
    conn.close()

def salvar_base_estoque_02(f_02, operacao):
    df_02 = robust_read_file(f_02)
    col_cod = [c for c in df_02.columns if "Cod" in str(c) or "COD" in str(c)][0]
    col_desc = [c for c in df_02.columns if "Desc" in str(c)][0]
    col_disp = [c for c in df_02.columns if "Disp" in str(c)][0]

    df_02["cod_clean"] = pd.to_numeric(df_02[col_cod], errors="coerce")
    df_02["Disp."] = pd.to_numeric(df_02[col_disp], errors="coerce").fillna(0)
    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    for _, r in df_02.dropna(subset=["cod_clean"]).iterrows():
        cursor.execute("""
            INSERT INTO base_estoque_02 (operacao, cod_clean, descricao, inicial, entrada, saida, disponivel, dt_atualizacao)
            VALUES (?, ?, ?, 0, 0, 0, ?, ?)
            ON CONFLICT(operacao, cod_clean) DO UPDATE SET
                descricao=excluded.descricao, disponivel=excluded.disponivel, dt_atualizacao=excluded.dt_atualizacao
        """, (operacao, int(r["cod_clean"]), str(r[col_desc]), float(r["Disp."]), dt_now))
    conn.commit()
    conn.close()

def salvar_pedidos_marcados(f_pedidos, operacao):
    df_pedidos = robust_read_file(f_pedidos)
    col_cod_r = df_pedidos.columns[17] if len(df_pedidos.columns) > 17 else df_pedidos.columns[0]
    col_marc_w = df_pedidos.columns[22] if len(df_pedidos.columns) > 22 else df_pedidos.columns[1]
    col_desc = df_pedidos.columns[1] if len(df_pedidos.columns) > 1 else df_pedidos.columns[0]
    col_dt = df_pedidos.columns[0]

    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pedidos_marcados WHERE operacao=?", (operacao,))
    dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    for _, r in df_pedidos.iterrows():
        cod_raw = str(r.get(col_cod_r, "")).strip()
        cod_clean_str = cod_raw[:-1] if len(cod_raw) > 1 else cod_raw
        cod_clean = pd.to_numeric(cod_clean_str, errors="coerce")
        if pd.isna(cod_clean): continue

        cursor.execute("""
            INSERT INTO pedidos_marcados (operacao, data_puxada, cod_clean, descricao, cx_solicitadas, cx_marcadas, hl_marcado, status_item, numero_pedido, dt_atualizacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (operacao, str(r.get(col_dt)).strip(), int(cod_clean), str(r.get(col_desc)).strip(), 0.0, parse_br_float(r.get(col_marc_w)), 0.0, "", "", dt_now))
    conn.commit()
    conn.close()

def carregar_estoque_consolidado(operacao):
    conn = sqlite3.connect("puxada_ambev.db")
    ops_filtro = [operacao]
    if operacao == "Bahia":
        ops_filtro = ["Lima Barreiras", "Lima São Félix", "Lima Bahia", "Lima Bahia Samavi"]

    placeholders = ",".join(["?"] * len(ops_filtro))
    query = f"""
    SELECT 
        e.cod_clean AS cod_clean,
        COALESCE(e.descricao, b_01.descricao, 'PRODUTO') AS descricao,
        COALESCE(l.tipo, 'OUTROS') AS tipo,
        COALESCE(l.categoria, 'OUTROS') AS categoria,
        CAST(COALESCE(e.disponivel, 0) AS INTEGER) AS disp,
        CAST(COALESCE(l.linear_vendas, 0) AS INTEGER) AS linear_vendas,
        COALESCE(b_01.fator_hl, 0.0) AS fator_hl,
        e.dt_atualizacao AS dt_atualizacao
    FROM base_estoque_02 e
    LEFT JOIN base_01_11 b_01 ON e.cod_clean = b_01.cod_clean
    LEFT JOIN base_linear l ON e.cod_clean = l.cod_clean
    WHERE e.operacao IN ({placeholders})
    """
    df = pd.read_sql_query(query, conn, params=ops_filtro)
    conn.close()

    if df.empty: return None
    df.columns = [str(c).lower() for c in df.columns]
    df["doi_atual"] = df.apply(lambda r: round(r["disp"] / r["linear_vendas"], 1) if r["linear_vendas"] > 0 else (999.0 if r["disp"] > 0 else 0.0), axis=1)
    return df

# 4. Módulo de Gestão de Ressuprimento Completo
def render_gestao_ressuprimento(operacao):
    st.subheader("📈 Gestão de Ressuprimento & Acompanhamento de Cestas (HL do Mês)")

    mapa_op_sistema = {
        "Lima Rio Verde": ["Lima Rio Verde", "Lima - Rio Verde", "Rio Verde"],
        "Lima Barreiras": ["Lima Bahia", "Barreiras", "Lima Barreiras"],
        "Lima São Félix": ["Lima Bahia Samavi", "Samavi", "São Félix", "Lima São Félix"],
        "Bahia": ["Lima Barreiras", "Lima São Félix", "Barreiras", "Samavi", "São Félix", "Lima Bahia", "Lima Bahia Samavi"],
    }

    nombres_filtro = mapa_op_sistema.get(operacao, [operacao])
    placeholders = ",".join(["?"] * len(nombres_filtro))
    nome_exibicao_op = "Bahia (Barreiras + São Félix)" if operacao == "Bahia" else operacao.replace("Lima ", "")

    tab_m1, tab_m2, tab_m3, tab_m4, tab_m5, tab_m6 = st.tabs([
        "📊 Acompanhamento Mensal & Volume Total",
        "📅 Carregamento Dia a Dia",
        "📦 Gestão de Política de Estoque",
        "⚙️ Configuração de Metas Mensais",
        "📁 Cadastros & Atualização (Estoque Dia)",
        "📁 Upload Base Diária",
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
        ano_sel = c_f1.number_input("Ano de Análise:", min_value=2024, max_value=2030, value=datetime.now().year, key="ano_acompanhamento")
        meses_nomes = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        meses_selecionados = c_f2.multiselect("Selecione os Meses de Análise:", options=list(range(1, 13)), format_func=lambda x: meses_nomes[x - 1], default=[datetime.now().month], key="meses_acompanhamento")

        conn = sqlite3.connect("puxada_ambev.db")
        df_diario = pd.read_sql_query(f"SELECT * FROM gestao_ressuprimento_diario WHERE operacao IN ({placeholders}) AND strftime('%Y', data_registro)='{ano_sel}'", conn, params=nombres_filtro)
        df_metas = pd.read_sql_query(f"SELECT * FROM metas_ressuprimento_mensal WHERE operacao IN ({placeholders}) AND ano={ano_sel}", conn, params=nombres_filtro)
        conn.close()

        if not df_diario.empty:
            df_diario["data_dt"] = pd.to_datetime(df_diario["data_registro"], errors="coerce")
            if not meses_selecionados: meses_selecionados = list(range(1, 13))
            df_diario_filtrado = df_diario[df_diario["data_dt"].dt.month.isin(meses_selecionados)]
            
            df_res_mes = df_diario_filtrado.groupby("cesta")["volume_sellin_hl"].sum().reset_index() if not df_diario_filtrado.empty else pd.DataFrame(columns=["cesta", "volume_sellin_hl"])
            df_comp = pd.merge(pd.DataFrame({"cesta": cestas_ordenadas}), df_res_mes, on="cesta", how="left").fillna(0)
            
            df_metas_filtradas = df_metas[df_metas["mes"].isin(meses_selecionados)] if not df_metas.empty else pd.DataFrame(columns=["cesta", "meta_volume_hl"])
            df_metas_grp = df_metas_filtradas.groupby("cesta")["meta_volume_hl"].sum().reset_index() if not df_metas_filtradas.empty else pd.DataFrame(columns=["cesta", "meta_volume_hl"])
            
            df_comp = pd.merge(df_comp, df_metas_grp, on="cesta", how="left").fillna(0)

            df_comp["INDICADOR"] = df_comp["cesta"].map(cestas_map).fillna(df_comp["cesta"])
            df_comp["META"] = df_comp["meta_volume_hl"] if "meta_volume_hl" in df_comp.columns else 0.0
            df_comp["REAL"] = df_comp["volume_sellin_hl"] if "volume_sellin_hl" in df_comp.columns else 0.0
            df_comp["ATING. REAL"] = df_comp.apply(lambda r: (r["REAL"] / r["META"] * 100) if r["META"] > 0 else 0.0, axis=1)

            df_view = df_comp[["INDICADOR", "META", "REAL", "ATING. REAL"]].copy()
            df_view["META"] = df_view["META"].apply(formatar_inteiro_br)
            df_view["REAL"] = df_view["REAL"].apply(formatar_inteiro_br)
            df_view["ATING. REAL"] = df_view["ATING. REAL"].apply(lambda x: f"{x:.1f}%".replace(".", ","))

            st.markdown(f"### 🔵 Acompanhamento - {nome_exibicao_op}")
            st.dataframe(df_view, use_container_width=True)
            render_botoes_download(df_comp, f"Acompanhamento_Mensal_{operacao}")
        else:
            st.info(f"ℹ️ Nenhum dado diário encontrado para **{nome_exibicao_op}** em {ano_sel}. Utilize a aba de Upload para inserir os dados.")

    with tab_m2:
        st.markdown(f"### 📅 Carregamento Dia a Dia - {nome_exibicao_op}")
        c_d1, c_d2 = st.columns(2)
        ano_dia = c_d1.number_input("Ano de Análise:", min_value=2024, max_value=2030, value=datetime.now().year, key="ano_dia_a_dia")
        meses_nomes_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_dia = c_d2.selectbox("Mês de Análise:", list(range(1, 13)), format_func=lambda x: meses_nomes_lista[x - 1], index=datetime.now().month - 1, key="mes_dia_a_dia")

        conn = sqlite3.connect("puxada_ambev.db")
        query_dia = f"""
            SELECT data_registro, cesta, SUM(volume_sellin_hl) as vol_hl
            FROM gestao_ressuprimento_diario
            WHERE operacao IN ({placeholders}) 
              AND CAST(STRFTIME('%Y', data_registro) AS INTEGER) = ?
              AND CAST(STRFTIME('%m', data_registro) AS INTEGER) = ?
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

            cols_indicadores = [c for c in df_pivot.columns if c != "Dia"]
            df_pivot["Total Dia (HL)"] = df_pivot[cols_indicadores].sum(axis=1)

            df_view_dia = df_pivot.copy()
            for col in cols_indicadores + ["Total Dia (HL)"]:
                df_view_dia[col] = df_view_dia[col].apply(formatar_inteiro_br)

            st.dataframe(df_view_dia, use_container_width=True)
            render_botoes_download(df_pivot, f"Carregamento_Dia_a_Dia_{mes_dia:02d}_{ano_dia}_{operacao}")
        else:
            st.info("ℹ️ Nenhum registro diário encontrado.")

    with tab_m3:
        st.markdown("### 📦 Gestão de Política de Estoque")
        df_pol = carregar_estoque_consolidado(operacao)
        if df_pol is not None and not df_pol.empty:
            st.dataframe(df_pol, use_container_width=True)
        else:
            st.info("Nenhum dado de política de estoque disponível.")

    with tab_m4:
        st.markdown(f"### 🎯 Cadastrar / Ajustar Metas Mensais ({nome_exibicao_op})")
        c_m1, c_m2 = st.columns(2)
        ano_meta = c_m1.number_input("Ano da Meta:", min_value=2024, max_value=2030, value=datetime.now().year, key="ano_meta_key")
        mes_meta = c_m2.selectbox("Mês da Meta:", list(range(1, 13)), format_func=lambda x: meses_nomes[x - 1], index=datetime.now().month - 1, key="mes_meta_key")

        mes_ano_meta_str = f"{['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][mes_meta-1]}/{ano_meta}"

        conn = sqlite3.connect("puxada_ambev.db")
        df_exist_metas = pd.read_sql_query(f"SELECT cesta, meta_volume_hl FROM metas_ressuprimento_mensal WHERE operacao IN ({placeholders}) AND ano={ano_meta} AND mes={mes_meta}", conn, params=nombres_filtro)
        conn.close()

        dict_metas_exist = dict(zip(df_exist_metas["cesta"], df_exist_metas["meta_volume_hl"])) if not df_exist_metas.empty else {}

        with st.form("form_cad_metas"):
            st.markdown(f"**Metas em HL para {mes_ano_meta_str} - {nome_exibicao_op}:**")
            input_metas = {}
            for cst in cestas_ordenadas:
                cst_nome_amigavel = cestas_map.get(cst, cst)
                val_init = float(dict_metas_exist.get(cst, 0.0))
                input_metas[cst] = st.number_input(f"Meta: {cst_nome_amigavel}", min_value=0.0, value=val_init, step=10.0)

            if st.form_submit_button("💾 Salvar Metas Mensais"):
                conn = sqlite3.connect("puxada_ambev.db")
                cursor = conn.cursor()
                dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")
                op_para_salvar = operacao if operacao != "Bahia" else "Lima Barreiras"
                for cst, m_val in input_metas.items():
                    cursor.execute("""
                        INSERT INTO metas_ressuprimento_mensal (operacao, ano, mes, mes_ano, cesta, meta_volume_hl, dt_atualizacao)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(operacao, ano, mes, cesta) DO UPDATE SET
                            meta_volume_hl=excluded.meta_volume_hl, dt_atualizacao=excluded.dt_atualizacao
                    """, (op_para_salvar, ano_meta, mes_meta, mes_ano_meta_str, cst, m_val, dt_now))
                conn.commit()
                conn.close()
                st.success(f"Metas de {mes_ano_meta_str} salvas com sucesso!")
                st.rerun()

    with tab_m5:
        st.markdown("### 📁 Cadastros & Atualização de Bases (Estoque do Dia)")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("**1. Relatório 01.11**")
            f_01 = st.file_uploader("Upload 01.11", type=["xlsx", "xls", "csv"], key="up_01")
            if f_01 and st.button("Salvar 01.11"):
                salvar_base_01_11(f_01)
                st.success("Base 01.11 salva!")
        with c2:
            st.markdown("**2. Relatório Linear**")
            f_lin = st.file_uploader("Upload Linear", type=["xlsx", "xls", "csv"], key="up_lin")
            if f_lin and st.button("Salvar Linear"):
                salvar_base_linear(f_lin)
                st.success("Base Linear salva!")
        with c3:
            st.markdown("**3. Relatório 02.03.04**")
            f_02 = st.file_uploader("Upload Estoque Dia", type=["xlsx", "xls", "csv"], key="up_02")
            if f_02 and st.button("Atualizar Estoque"):
                salvar_base_estoque_02(f_02, unidade)
                st.success("Estoque Atualizado!")
        with c4:
            st.markdown("**4. Puxada Marcada**")
            f_ped = st.file_uploader("Upload Puxadas", type=["xlsx", "xls", "csv"], key="up_ped")
            if f_ped and st.button("Salvar Puxadas"):
                salvar_pedidos_marcados(f_ped, unidade)
                st.success("Puxadas Salvas!")

    with tab_m6:
        st.markdown("### 📁 Upload do Relatório Diário de Ressuprimento")
        f_ress_daily = st.file_uploader("Selecione o arquivo de relatório diário (.xlsx, .xls, .csv):", type=["xlsx", "xls", "csv"])
        if f_ress_daily is not None and st.button("🚀 Processar e Atualizar Base"):
            try:
                df_up = robust_read_file(f_ress_daily)
                col_op, col_sellin, col_cesta, col_data = df_up.columns[0], df_up.columns[2], df_up.columns[4], df_up.columns[5]
                
                conn = sqlite3.connect("puxada_ambev.db")
                cursor = conn.cursor()
                dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")
                
                for _, r in df_up.dropna(subset=[col_cesta, col_data]).iterrows():
                    raw_op = str(r[col_op]).strip() if pd.notna(r[col_op]) else operacao
                    cst_val = str(r[col_cesta]).strip()
                    dt_val = str(pd.to_datetime(r[col_data]).strftime("%Y-%m-%d"))
                    mes_ano_val = str(pd.to_datetime(r[col_data]).strftime("%b/%Y"))
                    s_hl = parse_br_float(r[col_sellin])

                    cursor.execute("""
                        INSERT INTO gestao_ressuprimento_diario (operacao, data_registro, mes_ano, cesta, volume_sellin_hl, volume_real_hl, dt_atualizacao)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(operacao, data_registro, cesta) DO UPDATE SET
                            volume_sellin_hl=excluded.volume_sellin_hl, volume_real_hl=excluded.volume_sellin_hl, dt_atualizacao=excluded.dt_atualizacao
                    """, (raw_op, dt_val, mes_ano_val, cst_val, s_hl, s_hl, dt_now))
                
                conn.commit()
                conn.close()
                st.success("Base de dados de ressuprimento atualizada com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar o arquivo: {e}")

# 5. Navegação por Pilhas de Histórico (Botão Voltar)
if "nav_stack" not in st.session_state:
    st.session_state["nav_stack"] = ["Visão Geral (Dashboard)"]

def navigate_to(page_name):
    if st.session_state["nav_stack"][-1] != page_name:
        st.session_state["nav_stack"].append(page_name)

def go_back():
    if len(st.session_state["nav_stack"]) > 1:
        st.session_state["nav_stack"].pop()

# 6. Autenticação e Layout Principal
if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    st.markdown("""
        <div style="text-align: center; padding: 20px;">
            <h1 style="color: #0d2149;">Sistema Revenda - Grupo Lima</h1>
            <p style="color: #555;">Faça login com suas credenciais corporativas para acessar o sistema.</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.container():
            st.markdown("""
                <div style="background: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;">
                <h3 style="color: #0d2149; margin-top: 0; text-align: center;">🔐 Acesso Restrito</h3>
            """, unsafe_allow_html=True)

            usuario = st.text_input("Usuário Corporativo")
            senha = st.text_input("Senha", type="password")

            if st.button("🚀 Entrar no Sistema", use_container_width=True):
                conn = sqlite3.connect("puxada_ambev.db")
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, nome, perfil, permissoes_operacoes, permissoes_deptos, status FROM usuarios WHERE nome = ? AND senha = ?",
                    (usuario, senha),
                )
                user = cursor.fetchone()
                conn.close()

                if user:
                    if user[5] == "Inativo":
                        st.error("⚠️ Este usuário está inativo.")
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
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.sidebar.title("Grupo Lima")
    st.sidebar.caption(f"Usuário: **{st.session_state['usuario']}** | Perfil: **{st.session_state['perfil']}**")

    unidade = st.sidebar.selectbox("Unidade / Operação", OPERACOES_DISPONIVEIS)
    st.sidebar.divider()

    st.sidebar.markdown("### Departamentos Integrados")
    for d_name in DEPARTAMENTOS_DISPONIVEIS:
        is_active = (st.session_state["nav_stack"][-1] == d_name)
        tipo_btn = "primary" if is_active else "secondary"
        if st.sidebar.button(d_name, key=f"sidebar_btn_{d_name}", use_container_width=True, type=tipo_btn):
            navigate_to(d_name)
            st.rerun()

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

    dept_atual = st.session_state["nav_stack"][-1]
    c_title.title(f"{dept_atual}")
    st.caption(f"Operação ativa: **{unidade}**")

    # Roteamento dos Módulos
    if "Visão Geral" in dept_atual:
        st.subheader("Painel Geral de Desempenho Operacional")
        st.info("Selecione um departamento no menu lateral para acessar os módulos detalhados.")
    elif "Ressuprimento" in dept_atual:
        render_gestao_ressuprimento(unidade)
    else:
        st.info(f"O módulo de **{dept_atual}** está pronto para configuração.")
