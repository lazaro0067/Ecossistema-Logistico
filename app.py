import calendar
import datetime
import sqlite3
import pandas as pd
import streamlit as st

# ---------------------------------------------------------
# 1. CONFIGURAÇÃO INICIAL DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestão DPO & Distribuição - Grupo Lima",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# 2. CONEXÃO E ESTRUTURA DO BANCO DE DADOS (SQLite)
# ---------------------------------------------------------
DB_NAME = "puxada_ambev.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabela para armazenamento do histórico do diário de ressuprimento
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ressuprimento_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data DATE,
            unidade TEXT,
            categoria TEXT,
            volume REAL
        )
    """)

    # Tabela para cadastro de metas mensais por unidade e categoria
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metas_mensais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ano INTEGER,
            mes INTEGER,
            unidade TEXT,
            categoria TEXT,
            meta REAL
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# 3. BARRA LATERAL (SIDEBAR) - NAVEGAÇÃO
# ---------------------------------------------------------
st.sidebar.title("Grupo Lima")
st.sidebar.caption("Usuário: **admin** | Perfil: **Master**")

unidade_selecionada = st.sidebar.selectbox(
    "Unidade / Operação",
    ["Lima Rio Verde", "Lima Bahia (Barreiras)", "Samavi (São Félix)"],
)

st.sidebar.markdown("---")
st.sidebar.subheader("Departamentos Integrados")

departamento = st.sidebar.radio(
    "Selecione o Módulo:",
    [
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
        "Acesso Master (Gestão de Usuários)",
    ],
    index=2,  # Padrão selecionado em Ressuprimento
)

# ---------------------------------------------------------
# 4. MÓDULO DE RESSUPRIMENTO (Cesta e Acompanhamento)
# ---------------------------------------------------------
if departamento == "Ressuprimento":
    st.title("📈 Gestão de Ressuprimento & Acompanhamento de Cestas")

    # Navegação interna por abas
    aba_selecionada = st.radio(
        "",
        [
            "📊 Acompanhamento Mensal & Volume Total",
            "⚙️ Configuração de Metas Mensais",
            "📁 Upload & Atualização da Base Diária",
        ],
        horizontal=True,
    )

    # -----------------------------------------------------
    # ABA 1: Acompanhamento Mensal & Volume Total
    # -----------------------------------------------------
    if aba_selecionada == "📊 Acompanhamento Mensal & Volume Total":
        col_ano, col_mes = st.columns(2)
        with col_ano:
            ano = st.number_input(
                "Ano de Análise:",
                min_value=2020,
                max_value=2030,
                value=2026,
            )
        with col_mes:
            mes_nome = st.selectbox(
                "Mês de Análise:",
                [
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
                ],
                index=7,  # Agosto
            )

        # Mapeamento do mês selecionado e dias totais
        meses_map = {
            "Janeiro": 1,
            "Fevereiro": 2,
            "Março": 3,
            "Abril": 4,
            "Maio": 5,
            "Junho": 6,
            "Julho": 7,
            "Agosto": 8,
            "Setembro": 9,
            "Outubro": 10,
            "Novembro": 11,
            "Dezembro": 12,
        }
        mes_num = meses_map[mes_nome]
        _, dias_totais_mes = calendar.monthrange(int(ano), mes_num)

        # Dias já apurados no mês (ex: 24 dias preenchidos)
        dias_preenchidos = 24

        st.markdown("---")

        # -------------------------------------------------
        # BLOCO BARREIRAS (Valores e Tendência Corrigidos)
        # -------------------------------------------------
        st.subheader("🔵 Barreiras")
        st.caption(
            f"Detalhamento por indicador · {dias_preenchidos} dia(s) preenchido(s)"
        )

        # Base consolidada agrupada ajustada
        dados_barreiras = [
            {"INDICADOR": "Cerveja", "META": 0.0, "REAL": 19043.00},
            {"INDICADOR": "Nab", "META": 0.0, "REAL": 316.70},
            {"INDICADOR": "Match", "META": 0.0, "REAL": 31.05},
            {"INDICADOR": "Cerveja RGB", "META": 0.0, "REAL": 458.10},
            {"INDICADOR": "Nab Zero", "META": 0.0, "REAL": 17.33},
            {"INDICADOR": "Cerveja Zero Alcool", "META": 0.0, "REAL": 217.65},
            {"INDICADOR": "High End", "META": 0.0, "REAL": 3491.00},
        ]

        linhas_barreiras = []
        for item in dados_barreiras:
            ind = item["INDICADOR"]
            meta = item["META"]
            real = item["REAL"]

            # Tendência usando TODOS os dias do mês
            med_diaria = real / dias_preenchidos if dias_preenchidos > 0 else 0
            tend = med_diaria * dias_totais_mes

            # Atingimento Real (%): Volume acumulado puxado / Meta
            ating_real = (real / meta * 100) if meta > 0 else 0.0
            ating_tend = (tend / meta * 100) if meta > 0 else 0.0

            linhas_barreiras.append({
                "INDICADOR": ind,
                "META": meta,
                "REAL": real,
                "TEND.": tend,
                "ATING. REAL": ating_real,
                "ATING. TEND.": ating_tend,
            })

        df_b = pd.DataFrame(linhas_barreiras)

        # Linha Totalizadora
        tot_m = df_b["META"].sum()
        tot_r = df_b["REAL"].sum()
        tot_t = (
            (tot_r / dias_preenchidos) * dias_totais_mes
            if dias_preenchidos > 0
            else 0
        )
        tot_ar = (tot_r / tot_m * 100) if tot_m > 0 else 0.0
        tot_at = (tot_t / tot_m * 100) if tot_m > 0 else 0.0

        linha_tot_b = pd.DataFrame([{
            "INDICADOR": "Total Barreiras",
            "META": tot_m,
            "REAL": tot_r,
            "TEND.": tot_t,
            "ATING. REAL": tot_ar,
            "ATING. TEND.": tot_at,
        }])

        df_barreiras_final = pd.concat([df_b, linha_tot_b], ignore_index=True)

        # Renderização da Tabela no Streamlit com Formatação
        st.dataframe(
            df_barreiras_final.style.format({
                "META": "{:,.2f}",
                "REAL": "{:,.2f}",
                "TEND.": "{:,.2f}",
                "ATING. REAL": "{:.1f}%",
                "ATING. TEND.": "{:.1f}%",
            }),
            use_container_width=True,
            hide_index=True,
        )
