import io
import re
import sqlite3
import urllib.parse
import datetime
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
        return pd.read_csv(file_obj, sep=";", encoding="utf-8-sig", engine="python", on_bad_lines="skip")
    except Exception:
        file_obj.seek(0)
        return pd.read_csv(file_obj, sep=";", encoding="latin1", engine="python", on_bad_lines="skip")


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


def carregar_pedidos_pivoted(operacao):
    conn = sqlite3.connect("puxada_ambev.db")
    df_pm = pd.read_sql_query(f"SELECT data_puxada, cod_clean, cx_marcadas FROM pedidos_marcados WHERE operacao='{operacao}'", conn)
    conn.close()

    if df_pm.empty:
        return None, []

    datas_unicas = sorted(df_pm["data_puxada"].unique())
    df_grp = df_pm.groupby(["cod_clean", "data_puxada"])["cx_marcadas"].sum().reset_index()
    df_piv = df_grp.pivot(index="cod_clean", columns="data_puxada", values="cx_marcadas").fillna(0).reset_index()

    d0_col = datas_unicas[0] if len(datas_unicas) > 0 else None
    d1_col = datas_unicas[1] if len(datas_unicas) > 1 else None
    d2_col = datas_unicas[2] if len(datas_unicas) > 2 else None

    df_piv["Puxada_D0"] = df_piv[d0_col] if d0_col else 0.0
    df_piv["Puxada_D1"] = df_piv[d1_col] if d1_col else 0.0
    df_piv["Puxada_D2"] = df_piv[d2_col] if d2_col else 0.0
    df_piv["Total_Puxada"] = df_piv["Puxada_D0"] + df_piv["Puxada_D1"] + df_piv["Puxada_D2"]

    return df_piv[["cod_clean", "Puxada_D0", "Puxada_D1", "Puxada_D2", "Total_Puxada"]], datas_unicas


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
    df_abc = pd.read_sql_query(f"SELECT cod_clean, classe_abc FROM historico_curva_abc WHERE operacao='{operacao}' AND mes_ano = (SELECT MAX(mes_ano) FROM historico_curva_abc WHERE operacao='{operacao}')", conn)
    conn.close()

    if df.empty:
        return None

    if not df_abc.empty:
        df = pd.merge(df, df_abc, left_on="Cod_clean", right_on="cod_clean", how="left")
        df["Classe_ABC"] = df["classe_abc"].fillna("C")
        df.drop(columns=["cod_clean", "classe_abc"], inplace=True, errors="ignore")
    else:
        df["Classe_ABC"] = "C"

    df_piv, datas_puxada = carregar_pedidos_pivoted(operacao)
    if df_piv is not None and not df_piv.empty:
        df = pd.merge(df, df_piv, left_on="Cod_clean", right_on="cod_clean", how="left")
        df["Puxada_D0"] = df["Puxada_D0"].fillna(0)
        df["Puxada_D1"] = df["Puxada_D1"].fillna(0)
        df["Puxada_D2"] = df["Puxada_D2"].fillna(0)
        df["Total_Puxada"] = df["Total_Puxada"].fillna(0)
        df.drop(columns=["cod_clean"], inplace=True, errors="ignore")
    else:
        df["Puxada_D0"] = 0.0
        df["Puxada_D1"] = 0.0
        df["Puxada_D2"] = 0.0
        df["Total_Puxada"] = 0.0

    # Conversão para Paletes utilizando o parâmetro cx_pallet da 01.11
    df["Paletes_Disp"] = (df["Disp"] / df["cx_pallet"]).round(1)
    df["Paletes_D0"] = (df["Puxada_D0"] / df["cx_pallet"]).round(1)
    df["Paletes_D1"] = (df["Puxada_D1"] / df["cx_pallet"]).round(1)
    df["Paletes_D2"] = (df["Puxada_D2"] / df["cx_pallet"]).round(1)
    df["Paletes_Total_Puxada"] = (df["Total_Puxada"] / df["cx_pallet"]).round(1)
    
    df["Estoque_Projetado_CX"] = df["Disp"] + df["Total_Puxada"]
    df["Paletes_Projetados"] = (df["Estoque_Projetado_CX"] / df["cx_pallet"]).round(1)

    df["DOI_Atual"] = df.apply(
        lambda r: round(r["Disp"] / r["Linear_Vendas"], 1) if r["Linear_Vendas"] > 0 else (999.0 if r["Disp"] > 0 else 0.0),
        axis=1,
    )

    df["Estoque_HL"] = (df["fator_hl"] * df["Disp"]).round(2)
    df["Marca"] = df["Descricao"].apply(extract_ambev_brand)

    return df


def calcular_saude_estoque_dpo(df):
    if df is None or df.empty:
        return 0.0, 0, 0, 0, 0
    total_skus = len(df)
    saudaveis = len(df[(df["DOI_Atual"] >= 7.0) & (df["DOI_Atual"] <= 30.0)])
    baixo = len(df[(df["DOI_Atual"] >= 3.0) & (df["DOI_Atual"] < 7.0)])
    ruptura = len(df[df["DOI_Atual"] < 3.0])
    overstock = len(df[df["DOI_Atual"] > 30.0])
    pct_saude = (saudaveis / total_skus) * 100.0 if total_skus > 0 else 0.0
    return round(pct_saude, 1), saudaveis, baixo, ruptura, overstock


def gerar_excel(df):
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Dados")
    except Exception:
        df.to_csv(output, index=False, sep=";")
    return output.getvalue()


# 4. Portal Comercial e Interface Mobile Otimizada
modo_comercial = False
unidade_param = "Lima Rio Verde"

if "modo" in st.query_params:
    val_modo = st.query_params["modo"]
    modo_comercial = "comercial" in val_modo if isinstance(val_modo, list) else val_modo == "comercial"

if "unidade" in st.query_params:
    val_u = st.query_params["unidade"]
    unidade_param = val_u[0] if isinstance(val_u, list) else val_u


def render_estoque_dia(unidade):
    st.subheader(f"Estoque Dia — Consulta Comercial ({unidade})")

    df = carregar_estoque_consolidado(unidade)

    if df is not None and not df.empty:
        st.caption(f"🕒 **Sincronizado em:** {df['dt_atualizacao'].iloc[0]}")

        # Regra de classificação unificada com Stock Out e Stock Overstock
        def get_status(doi, disp):
            if disp == 0 or doi < 3.0:
                return "🔴 Stock Out / Ruptura (<3d)"
            elif doi < 7.0:
                return "🟡 Estoque Baixo (3-7d)"
            elif doi > 30.0:
                return "🟠 Stock Over / Elevado (>30d)"
            else:
                return "🟢 Disponível / OK (7-30d)"

        df["Status"] = df.apply(lambda r: get_status(r["DOI_Atual"], r["Disp"]), axis=1)

        # Indicadores Gerais Convertidos para Paletes
        m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
        m_col1.metric("SKUs Ativos", f"{len(df)}")
        m_col2.metric("Estoque Físico", f"{df['Paletes_Disp'].sum():,.1f} plt")
        m_col3.metric("Chegando D0", f"{df['Paletes_D0'].sum():,.1f} plt")
        m_col4.metric("Chegando D1", f"{df['Paletes_D1'].sum():,.1f} plt")
        m_col5.metric("Chegando D2", f"{df['Paletes_D2'].sum():,.1f} plt")
        m_col6.metric("Projeção Total", f"{df['Paletes_Projetados'].sum():,.1f} plt")

        st.divider()

        # Filtros Rápidos
        if "filtro_status_dia" not in st.session_state:
            st.session_state["filtro_status_dia"] = "TODOS"

        k1, k2, k3, k4, k5 = st.columns(5)
        if k1.button(f"Todos\n\n### {len(df)}"):
            st.session_state["filtro_status_dia"] = "TODOS"
        if k2.button(f"Disponível 🟢\n\n### {len(df[df['Status'].str.contains('🟢')])}"):
            st.session_state["filtro_status_dia"] = "🟢 Disponível / OK (7-30d)"
        if k3.button(f"Estoque Baixo 🟡\n\n### {len(df[df['Status'].str.contains('🟡')])}"):
            st.session_state["filtro_status_dia"] = "🟡 Estoque Baixo (3-7d)"
        if k4.button(f"Stock Over 🟠\n\n### {len(df[df['Status'].str.contains('🟠')])}"):
            st.session_state["filtro_status_dia"] = "🟠 Stock Over / Elevado (>30d)"
        if k5.button(f"Stock Out 🔴\n\n### {len(df[df['Status'].str.contains('🔴')])}"):
            st.session_state["filtro_status_dia"] = "🔴 Stock Out / Ruptura (<3d)"

        df_exib = df if st.session_state["filtro_status_dia"] == "TODOS" else df[df["Status"] == st.session_state["filtro_status_dia"]]

        mod_visual = st.radio("Selecione o Formato de Exibição:", ["📲 Visão Mobile (Cards de Paletes)", "📊 Visão Tabela Completa"], horizontal=True)

        st.divider()

        if "Cards" in mod_visual:
            busca_card = st.text_input("🔍 Pesquisar por código ou marca:", key="b_card")
            if busca_card:
                df_cards = df_exib[df_exib["Cod_clean"].astype(str).str.contains(busca_card) | df_exib["Descricao"].str.contains(busca_card, case=False)]
            else:
                df_cards = df_exib

            # Renderização dos Cards com Paletes e Código de Cores
            grid_cols = st.columns(3)
            for idx, r in df_cards.reset_index().iterrows():
                col_target = grid_cols[idx % 3]

                if "🟢" in r["Status"]:
                    border_color, bg_color = "#2e7d32", "#f1f8e9"
                elif "🟡" in r["Status"]:
                    border_color, bg_color = "#f57f17", "#fffde7"
                elif "🟠" in r["Status"]:
                    border_color, bg_color = "#e65100", "#fff3e0"
                else:
                    border_color, bg_color = "#c62828", "#ffebee"

                with col_target:
                    st.markdown(f"""
                    <div style="border: 2px solid {border_color}; background-color: {bg_color}; border-radius: 10px; padding: 12px; margin-bottom: 12px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                        <div style="font-weight: bold; font-size: 14px; color: #333; height: 38px; overflow: hidden;">{r['Descricao']}</div>
                        <div style="font-size: 11px; color: #666; margin-bottom: 8px;">Cód: <b>{r['Cod_clean']}</b> | Marca: <b>{r['Marca']}</b> | Cobertura: <b>{r['DOI_Atual']} dias</b></div>
                        <div style="font-size: 18px; font-weight: bold; color: {border_color}; margin-bottom: 6px;">
                            📦 {r['Paletes_Disp']:,.1f} Paletes <span style="font-size:12px; color:#555;">({r['Disp']:,.0f} cx)</span>
                        </div>
                        <div style="font-size: 11px; background-color: #ffffff; padding: 6px; border-radius: 6px; border: 1px solid #e0e0e0;">
                            🚛 <b>Puxada Agendada (Paletes):</b><br>
                            • D0: <b>{r['Paletes_D0']:,.1f} plt</b> | • D1: <b>{r['Paletes_D1']:,.1f} plt</b> | • D2: <b>{r['Paletes_D2']:,.1f} plt</b><br>
                            🎯 <b>Projeção Total:</b> <span style="color:#0288d1; font-weight:bold;">{r['Paletes_Projetados']:,.1f} plt</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            cols_view = [
                "Cod_clean", "Descricao", "Marca", "Paletes_Disp", "Paletes_D0", "Paletes_D1", "Paletes_D2", 
                "Paletes_Projetados", "Disp", "Total_Puxada", "Linear_Vendas", "DOI_Atual", "Status"
            ]
            format_dict = {
                "Paletes_Disp": "{:,.1f}", "Paletes_D0": "{:,.1f}", "Paletes_D1": "{:,.1f}", "Paletes_D2": "{:,.1f}",
                "Paletes_Projetados": "{:,.1f}", "Disp": "{:,.0f}", "Total_Puxada": "{:,.0f}", "Linear_Vendas": "{:,.0f}", "DOI_Atual": "{:,.1f}"
            }
            st.dataframe(df_exib[cols_view].style.format(format_dict), use_container_width=True)

    else:
        st.info("ℹ️ Nenhum estoque sincronizado nesta operação. Faça a atualização na aba **Ressuprimento**.")


if modo_comercial:
    st.title("Grupo Lima — Portal Comercial de Vendas")
    unidade_sel = st.selectbox("Selecione a Unidade Operacional:", OPERACOES_DISPONIVEIS, index=OPERACOES_DISPONIVEIS.index(unidade_param) if unidade_param in OPERACOES_DISPONIVEIS else 0)
    render_estoque_dia(unidade_sel)
    st.stop()

# 5. Módulo Principal com Login
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
            cursor.execute("SELECT id, nome, perfil, permissoes_operacoes, permissoes_deptos FROM usuarios WHERE nome = ? AND senha = ?", (usuario, senha))
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
    st.sidebar.caption(f"Usuário: **{st.session_state['usuario']}** | Perfil: **{st.session_state['perfil']}**")

    perm_ops_raw = st.session_state.get("perm_ops", "TODAS")
    ops_disponiveis = OPERACOES_DISPONIVEIS if perm_ops_raw == "TODAS" or st.session_state["perfil"] == "Master" else [o.strip() for o in perm_ops_raw.split(",") if o.strip()]

    unidade = st.sidebar.selectbox("Unidade / Operação", ops_disponiveis)
    st.sidebar.divider()

    dept = st.sidebar.radio("Departamentos", DEPARTAMENTOS_DISPONIVEIS)

    st.title(f"{dept}")
    st.caption(f"Operação ativa: **{unidade}**")

    if "Armazém" in dept or "Ressuprimento" in dept or "Vendas" in dept:
        render_estoque_dia(unidade)
    else:
        st.info(f"O módulo **{dept}** está ativo e pronto para uso.")
