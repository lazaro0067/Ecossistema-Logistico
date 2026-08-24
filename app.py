import datetime
import sqlite3
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Grupo Lima — Ecossistema Integrado 2026",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --- BANCO DE DADOS INTEGRADO COM TODAS AS TABELAS ---
def init_db():
    conn = sqlite3.connect("puxada_ambev.db")
    cursor = conn.cursor()

    # 1. Empresas / Operações Independentes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        cnpj TEXT,
        cidade TEXT,
        uf TEXT
    )""")

    # 2. Usuários e Permissões Granulares
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
        perm_puxada INTEGER DEFAULT 1,
        perm_ressuprimento INTEGER DEFAULT 1,
        perm_armazem INTEGER DEFAULT 1,
        perm_distribuicao INTEGER DEFAULT 1,
        perm_gente INTEGER DEFAULT 1,
        perm_frota INTEGER DEFAULT 1,
        perm_vendas INTEGER DEFAULT 1,
        perm_financeiro INTEGER DEFAULT 1,
        perm_compras INTEGER DEFAULT 1
    )""")

    # 3. Puxada e Trechos
    cursor.execute("""CREATE TABLE IF NOT EXISTS origens_destinos (id INTEGER PRIMARY KEY AUTOINCREMENT, operacao TEXT, nome TEXT, cidade TEXT, uf TEXT, tipo TEXT, UNIQUE(operacao, nome))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS trechos (id INTEGER PRIMARY KEY AUTOINCREMENT, operacao TEXT, origem TEXT, destino TEXT, distancia_km REAL, pedagio REAL, valor_remunerado REAL, valor_frete REAL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS transportadoras (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, cnpj TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS centros_custo (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)""")

    # 4. Fretes & Cotações
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cotacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT, origem TEXT, destino TEXT, data_requisicao TEXT,
        data_frete TEXT, motivo TEXT, transportadora TEXT, valor_negociado REAL,
        centro_custo TEXT, solicitante TEXT, aprovador TEXT, observacao TEXT,
        status TEXT DEFAULT 'Pendente Aprovação', nf_nome TEXT, cte_nome TEXT
    )""")

    # 5. Módulo Compras
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compras_pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT, item TEXT, quantidade REAL, valor_unitario REAL,
        fornecedor TEXT, status TEXT DEFAULT 'Pendente', solicitante TEXT, data TEXT
    )""")

    # 6. PNR (Plano de Necessidade de Ressuprimento / Metas)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pnr_metas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT, mes_ano TEXT, meta_volume_hl REAL, meta_frete_real REAL,
        UNIQUE(operacao, mes_ano)
    )""")

    # 7. Controle de Carretos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS carretos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operacao TEXT, motorista TEXT, placa TEXT, valor REAL, status TEXT DEFAULT 'Em Trânsito', data TEXT
    )""")

    # Populate Inicial das Empresas Independentes
    empresas = [
        ("Lima Rio Verde", "12.345.678/0001-90", "Rio Verde", "GO"),
        ("Lima Barreiras", "98.765.432/0001-10", "Barreiras", "BA"),
        ("Lima São Félix", "45.678.912/0001-33", "São Félix do Coribe", "BA"),
    ]
    for emp in empresas:
        cursor.execute(
            "INSERT OR IGNORE INTO operacoes (nome, cnpj, cidade, uf) VALUES"
            " (?,?,?,?)",
            emp,
        )

    # Administrador Master
    cursor.execute("SELECT count(*) FROM usuarios WHERE nome = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO usuarios (nome, senha, email, cargo, perfil, e_aprovador, alcada_reais, perm_puxada, perm_ressuprimento, perm_armazem, perm_distribuicao, perm_gente, perm_frota, perm_vendas, perm_financeiro, perm_compras)
        VALUES ('admin', 'admin123', 'admin@grupolima.com.br', 'Administrador Master', 'Master', 'Sim', 9999999.0, 1, 1, 1, 1, 1, 1, 1, 1, 1)
        """)

    conn.commit()
    conn.close()


init_db()

# --- GERENCIAMENTO DE SESSÃO ---
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "operacao_atual" not in st.session_state:
    st.session_state.operacao_atual = "Lima Rio Verde"

conn = sqlite3.connect("puxada_ambev.db")

# ==========================================
# TELA DE LOGIN
# ==========================================
if not st.session_state.usuario:
    st.title("🌐 Grupo Lima — Sistema de Gestão Integrada")
    st.caption("Acesso Restrito às Operações e Unidades")

    with st.form("f_login"):
        u = st.text_input("Usuário / Login")
        s = st.text_input("Senha", type="password")
        if st.form_submit_button("Acessar Painel"):
            df = pd.read_sql_query(
                "SELECT * FROM usuarios WHERE nome=? AND senha=?",
                conn,
                params=(u, s),
            )
            if not df.empty:
                st.session_state.usuario = df.iloc[0].to_dict()
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    st.stop()

usr = st.session_state.usuario

# ==========================================
# BARRA LATERAL (SELETOR DE EMPRESAS)
# ==========================================
st.sidebar.title("🏢 Grupo Lima")
st.sidebar.markdown(f"**Operador:** {usr['nome']}")
st.sidebar.caption(f"Cargo: {usr['cargo']} | Perfil: {usr['perfil']}")

lista_ops = pd.read_sql_query("SELECT nome FROM operacoes", conn)[
    "nome"
].tolist()
st.session_state.operacao_atual = st.sidebar.selectbox(
    "Seleção de Empresa / Unidade",
    lista_ops,
    index=lista_ops.index(st.session_state.operacao_atual)
    if st.session_state.operacao_atual in lista_ops
    else 0,
)

if st.sidebar.button("🚪 Sair do Sistema"):
    st.session_state.usuario = None
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Menu Módulos")

# Construção dinâmica do menu conforme rotas e permissões
menu_opcoes = []
if usr["perfil"] == "Master" or usr.get("perm_puxada") == 1:
    menu_opcoes.append("🚚 Puxada & Fretes")
if usr["perfil"] == "Master" or usr.get("perm_ressuprimento") == 1:
    menu_opcoes.append("📦 Ressuprimento & PNR")
if usr["perfil"] == "Master" or usr.get("perm_compras") == 1:
    menu_opcoes.append("🛒 Compras & Cotações")
if usr["perfil"] == "Master" or usr.get("perm_armazem") == 1:
    menu_opcoes.append("🏬 Armazém & Estoque")
if usr["perfil"] == "Master" or usr.get("perm_distribuicao") == 1:
    menu_opcoes.append("🚛 Distribuição & Devolução")
if usr["perfil"] == "Master" or usr.get("perm_frota") == 1:
    menu_opcoes.append("🛡️ Segurança & Frota")
if usr["perfil"] == "Master" or usr.get("perm_financeiro") == 1:
    menu_opcoes.append("💰 Financeiro, Carreto & OBZ")

if usr["perfil"] == "Master":
    menu_opcoes.append("🔑 Painel Admin (Acessos)")

menu = st.sidebar.radio("Selecione o Módulo", menu_opcoes)
op_atual = st.session_state.operacao_atual

# ==========================================
# 1. MÓDULO: PUXADA & FRETES
# ==========================================
if menu == "🚚 Puxada & Fretes":
    st.title(f"🚚 Puxada e Gestão de Fretes — {op_atual}")

    t1, t2, t3, t4, t5 = st.tabs([
        "📝 Nova Cotação",
        "✅ Central de Aprovações",
        "📋 Painel de Fretes",
        "🧮 Simulador Subida/Frete",
        "⚙️ Cadastros de Suporte",
    ])

    with t1:
        st.subheader("Solicitação de Frete / Cotação")
        ods = pd.read_sql_query(
            "SELECT nome FROM origens_destinos WHERE operacao=?",
            conn,
            params=(op_atual,),
        )["nome"].tolist()
        transps = pd.read_sql_query("SELECT nome FROM transportadoras", conn)[
            "nome"
        ].tolist()
        ccs = pd.read_sql_query("SELECT nome FROM centros_custo", conn)[
            "nome"
        ].tolist()
        aprovs = pd.read_sql_query(
            "SELECT nome FROM usuarios WHERE e_aprovador='Sim'", conn
        )["nome"].tolist()

        with st.form("f_pux_nova"):
            c1, c2 = st.columns(2)
            orig = c1.selectbox("Origem", ["Selecione..."] + ods)
            dest = c2.selectbox("Destino", ["Selecione..."] + ods)
            c3, c4 = st.columns(2)
            tr = c3.selectbox("Transportadora", ["Selecione..."] + transps)
            val = c4.number_input("Valor Negociado (R$)", min_value=0.0)
            c5, c6 = st.columns(2)
            cc = c5.selectbox("Centro de Custo", ["Selecione..."] + ccs)
            ap = c6.selectbox("Aprovador", ["Selecione..."] + aprovs)
            obs = st.text_area("Motivo / Observações")

            if st.form_submit_button("Enviar para Aprovação"):
                conn.execute(
                    """INSERT INTO cotacoes (operacao, origem, destino, data_requisicao, data_frete, motivo, transportadora, valor_negociado, centro_custo, solicitante, aprovador, observacao)
                VALUES (?, ?, ?, ?, ?, 'Transferência', ?, ?, ?, ?, ?, ?)""",
                    (
                        op_atual,
                        orig,
                        dest,
                        str(datetime.date.today()),
                        str(datetime.date.today()),
                        tr,
                        val,
                        cc,
                        usr["nome"],
                        ap,
                        obs,
                    ),
                )
                conn.commit()
                st.success("Cotação enviada com sucesso!")
                st.rerun()

    with t2:
        st.subheader("Fretes Aguardando Sua Aprovação")
        df_p = pd.read_sql_query(
            "SELECT * FROM cotacoes WHERE status='Pendente Aprovação' AND"
            " operacao=?",
            conn,
            params=(op_atual,),
        )
        for idx, r in df_p.iterrows():
            with st.expander(
                f"Solicitação #{r['id']} — {r['origem']} ➔ {r['destino']} | R$"
                f" {r['valor_negociado']:,.2f}"
            ):
                st.write(
                    f"**Solicitante:** {r['solicitante']} |"
                    f" **Transportadora:** {r['transportadora']}"
                )
                col_a, col_b = st.columns(2)
                if col_a.button(f"Aprovar #{r['id']}"):
                    conn.execute(
                        "UPDATE cotacoes SET status='Aprovado' WHERE id=?",
                        (r["id"],),
                    )
                    conn.commit()
                    st.rerun()
                if col_b.button(f"Rejeitar #{r['id']}"):
                    conn.execute(
                        "UPDATE cotacoes SET status='Rejeitado' WHERE id=?",
                        (r["id"],),
                    )
                    conn.commit()
                    st.rerun()

    with t3:
        st.subheader("Painel Geral")
        st.dataframe(
            pd.read_sql_query(
                "SELECT * FROM cotacoes WHERE operacao=?",
                conn,
                params=(op_atual,),
            ),
            use_container_width=True,
        )

    with t4:
        st.subheader("Simulador de Custos por Trecho")
        c1, c2, c3 = st.columns(3)
        dist = c1.number_input("Distância em KM", value=350.0)
        cons = c2.number_input("Consumo Médio (KM/L)", value=2.2)
        p_diesel = c3.number_input("Preço Diesel (R$)", value=5.89)

        custo = (dist / cons) * p_diesel
        st.metric(
            "Custo Estimado de Combustível",
            f"R$ {custo:,.2f}",
            help="Cálculo base para auxílio na tomada de decisão.",
        )

    with t5:
        st.subheader("Origens, Destinos e Trechos")
        c1, c2, c3 = st.columns(3)
        nod = c1.text_input("Nome Local")
        cid = c2.text_input("Cidade")
        uf = c3.text_input("UF")
        if st.button("+ Salvar Local"):
            conn.execute(
                "INSERT OR IGNORE INTO origens_destinos (operacao, nome, cidade,"
                " uf, tipo) VALUES (?,?,?,?,'Origem e destino')",
                (op_atual, nod, cid, uf),
            )
            conn.commit()
            st.rerun()

# ==========================================
# 2. MÓDULO: COMPRAS & COTAÇÕES
# ==========================================
elif menu == "🛒 Compras & Cotações":
    st.title(f"🛒 Módulo de Compras — {op_atual}")

    c1, c2 = st.tabs(["🛍️ Novo Pedido de Compra", "📋 Quadro de Pedidos"])

    with c1:
        with st.form("f_comp"):
            item = st.text_input("Item / Produto")
            c1_c, c2_c, c3_c = st.columns(3)
            qtd = c1_c.number_input("Quantidade", min_value=1.0)
            v_unit = c2_c.number_input("Valor Unitário Estimado", min_value=0.0)
            forn = c3_c.text_input("Fornecedor Pretendido")

            if st.form_submit_button("Lançar Pedido"):
                conn.execute(
                    "INSERT INTO compras_pedidos (operacao, item, quantidade, valor_unitario, fornecedor, solicitante, data) VALUES (?,?,?,?,?,?,?)",
                    (
                        op_atual,
                        item,
                        qtd,
                        v_unit,
                        forn,
                        usr["nome"],
                        str(datetime.date.today()),
                    ),
                )
                conn.commit()
                st.success("Pedido gravado com sucesso!")

    with c2:
        st.dataframe(
            pd.read_sql_query(
                "SELECT * FROM compras_pedidos WHERE operacao=?",
                conn,
                params=(op_atual,),
            ),
            use_container_width=True,
        )

# ==========================================
# 3. MÓDULO: RESSUPRIMENTO & PNR POR METAS
# ==========================================
elif menu == "📦 Ressuprimento & PNR":
    st.title(f"📦 Ressuprimento e PNR por Metas — {op_atual}")

    p1, p2 = st.tabs(["📊 Controle de Metas PNR", "📈 Inserir Metas do Mês"])

    with p1:
        mes_f = datetime.date.today().strftime("%Y-%m")
        df_pnr = pd.read_sql_query(
            "SELECT * FROM pnr_metas WHERE operacao=? AND mes_ano=?",
            conn,
            params=(op_atual, mes_f),
        )

        m_vol = df_pnr["meta_volume_hl"].iloc[0] if not df_pnr.empty else 0.0
        m_frete = df_pnr["meta_frete_real"].iloc[0] if not df_pnr.empty else 0.0

        col1, col2 = st.columns(2)
        col1.metric("Meta de Volume (HL)", f"{m_vol:,.2f} HL")
        col2.metric("Meta Limite de Frete", f"R$ {m_frete:,.2f}")

    with p2:
        with st.form("f_pnr_meta"):
            mes_input = st.text_input(
                "Mês/Ano", value=datetime.date.today().strftime("%Y-%m")
            )
            v_hl = st.number_input("Meta Volume (HL)", min_value=0.0)
            v_fr = st.number_input("Meta Frete Limite (R$)", min_value=0.0)

            if st.form_submit_button("Salvar Meta PNR"):
                conn.execute(
                    "INSERT OR REPLACE INTO pnr_metas (operacao, mes_ano, meta_volume_hl, meta_frete_real) VALUES (?,?,?,?)",
                    (op_atual, mes_input, v_hl, v_fr),
                )
                conn.commit()
                st.success("Meta PNR Gravada!")

# ==========================================
# 4. MÓDULO: FINANCEIRO, CARRETO & OBZ
# ==========================================
elif menu == "💰 Financeiro, Carreto & OBZ":
    st.title(f"💰 Financeiro & Controle de Carretos — {op_atual}")

    f1, f2 = st.tabs(["🚛 Controle de Carretos", "📊 Visão OBZ Orçamentária"])

    with f1:
        st.subheader("Carretos Lançados")
        with st.form("f_carreto"):
            c1, c2, c3 = st.columns(3)
            mot = c1.text_input("Motorista")
            plc = c2.text_input("Placa Veículo")
            v_c = c3.number_input("Valor Carreto (R$)", min_value=0.0)
            if st.form_submit_button("Registrar Carreto"):
                conn.execute(
                    "INSERT INTO carretos (operacao, motorista, placa, valor, data) VALUES (?,?,?,?,?)",
                    (op_atual, mot, plc, v_c, str(datetime.date.today())),
                )
                conn.commit()
                st.success("Carreto Lançado!")

        st.dataframe(
            pd.read_sql_query(
                "SELECT * FROM carretos WHERE operacao=?",
                conn,
                params=(op_atual,),
            ),
            use_container_width=True,
        )

    with f2:
        st.subheader("Resumo Orçamentário OBZ")
        realizado_fretes = (
            pd.read_sql_query(
                "SELECT SUM(valor_negociado) as total FROM cotacoes WHERE"
                " operacao=? AND status IN ('Aprovado', 'Finalizado')",
                conn,
                params=(op_atual,),
            )["total"].iloc[0]
            or 0.0
        )
        realizado_carretos = (
            pd.read_sql_query(
                "SELECT SUM(valor) as total FROM carretos WHERE operacao=?",
                conn,
                params=(op_atual,),
            )["total"].iloc[0]
            or 0.0
        )

        st.metric(
            "Custo Total Comprometido (Fretes + Carretos)",
            f"R$ {realizado_fretes + realizado_carretos:,.2f}",
        )

# ==========================================
# 5. MÓDULO: ADMINISTRADOR (ACESSOS)
# ==========================================
elif menu == "🔑 Painel Admin (Acessos)":
    st.title("🔑 Cadastro de Usuários e Permissões Unificadas")

    with st.form("f_cad_usr"):
        st.subheader("Novo Usuário")
        u_m = st.text_input("Login")
        s_m = st.text_input("Senha", type="password")
        e_m = st.text_input("E-mail")

        c1, c2 = st.columns(2)
        cargo_m = c1.text_input("Cargo", value="Analista Logístico")
        perfil_m = c2.selectbox("Perfil", ["Operacional", "Master"])

        st.write("**Permissões:**")
        ca, cb, cc = st.columns(3)
        p1 = ca.checkbox("Puxada", value=True)
        p2 = cb.checkbox("Ressuprimento", value=True)
        p3 = cc.checkbox("Compras", value=True)
        p4 = ca.checkbox("Armazém")
        p5 = cb.checkbox("Distribuição")
        p6 = cc.checkbox("Financeiro")

        if st.form_submit_button("Salvar Usuário"):
            conn.execute(
                """INSERT INTO usuarios (nome, senha, email, cargo, perfil, perm_puxada, perm_ressuprimento, perm_compras, perm_armazem, perm_distribuicao, perm_financeiro)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    u_m,
                    s_m,
                    e_m,
                    cargo_m,
                    perfil_m,
                    1 if p1 else 0,
                    1 if p2 else 0,
                    1 if p3 else 0,
                    1 if p4 else 0,
                    1 if p5 else 0,
                    1 if p6 else 0,
                ),
            )
            conn.commit()
            st.success("Usuário Cadastrado!")
            st.rerun()

    st.subheader("Usuários Ativos")
    st.dataframe(
        pd.read_sql_query("SELECT id, nome, email, cargo, perfil FROM usuarios", conn),
        use_container_width=True,
    )

else:
    st.title(f"{menu} — {op_atual}")
    st.info("Módulo ativo e integrado à base local.")

conn.close()
