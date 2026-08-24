import calendar
import datetime
from datetime import datetime
import io
import re
import sqlite3
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
import streamlit as st

# Importação condicional do docx para evitar falha no Streamlit Cloud
try:
    import docx

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# =========================================================
# 1. FUNÇÕES DE PROCESSAMENTO E MAPEAMENTO DE COLUNAS (A, C, E, F)
# =========================================================


def processar_base_ressuprimento(uploaded_file, ano=2026, mes=8):
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith(".xls"):
        df = pd.read_excel(uploaded_file, engine="xlrd")
    else:
        df = pd.read_excel(uploaded_file, engine="openpyxl")

    # Mapeamento estrito por posição de coluna:
    # Coluna A (índice 0) = Operação / Unidade
    # Coluna C (índice 2) = Volume em HL Puxado
    # Coluna E (índice 4) = Cesta / Indicador
    # Coluna F (índice 5) = Data do Movimento
    df_mapped = pd.DataFrame({
        "operacao": df.iloc[:, 0].astype(str).str.strip(),
        "hl_puxado": pd.to_numeric(df.iloc[:, 2], errors="coerce").fillna(0),
        "indicador": df.iloc[:, 4].astype(str).str.strip(),
        "data": pd.to_datetime(df.iloc[:, 5], errors="coerce"),
    })

    # Filtrar apenas dados do Mês e Ano selecionados
    df_filtrado = df_mapped[
        (df_mapped["data"].dt.month == mes)
        & (df_mapped["data"].dt.year == ano)
    ].copy()

    return df_filtrado


def gerar_relatorio_puxada(df_filtrado, ano=2026, mes=8):
    _, dias_totais_mes = calendar.monthrange(ano, mes)
    dias_preenchidos = df_filtrado["data"].dt.day.nunique()

    # Agrupa por Operação e Indicador somando o HL (Coluna C)
    df_agrupado = (
        df_filtrado.groupby(["operacao", "indicador"])["hl_puxado"]
        .sum()
        .reset_index()
    )

    def calcular_tabela_op(df_op, nome_op):
        indicadores = [
            "Cerveja",
            "Nab",
            "Match",
            "Cerveja RGB",
            "Nab Zero",
            "Cerveja Zero Alcool",
            "High End",
        ]
        linhas = []

        for ind in indicadores:
            real = df_op[df_op["indicador"] == ind]["hl_puxado"].sum()
            meta = 0.0

            media_diaria = (
                real / dias_preenchidos if dias_preenchidos > 0 else 0.0
            )
            tendencia = media_diaria * dias_totais_mes

            ating_real = (real / meta * 100) if meta > 0 else 0.0
            ating_tend = (tendencia / meta * 100) if meta > 0 else 0.0

            linhas.append({
                "INDICADOR": ind,
                "META": meta,
                "REAL": real,
                "TEND.": tendencia,
                "ATING. REAL": ating_real,
                "ATING. TEND.": ating_tend,
            })

        df_res = pd.DataFrame(linhas)

        tot_m = df_res["META"].sum()
        tot_r = df_res["REAL"].sum()
        tot_t = (
            (tot_r / dias_preenchidos) * dias_totais_mes
            if dias_preenchidos > 0
            else 0.0
        )
        tot_ar = (tot_r / tot_m * 100) if tot_m > 0 else 0.0
        tot_at = (tot_t / tot_m * 100) if tot_m > 0 else 0.0

        linha_tot = pd.DataFrame([{
            "INDICADOR": f"Total {nome_op}",
            "META": tot_m,
            "REAL": tot_r,
            "TEND.": tot_t,
            "ATING. REAL": tot_ar,
            "ATING. TEND.": tot_at,
        }])

        return pd.concat([df_res, linha_tot], ignore_index=True)

    df_barreiras = df_agrupado[
        df_agrupado["operacao"].str.contains("Barreiras", case=False, na=False)
    ]
    df_samavi = df_agrupado[
        df_agrupado["operacao"].str.contains(
            "São Félix|Samavi", case=False, na=False
        )
    ]

    # Consolidado BAHIA (Somatório Barreiras + São Félix)
    df_bahia_raw = pd.concat([df_barreiras, df_samavi], ignore_index=True)

    tabela_barreiras = calcular_tabela_op(df_barreiras, "Barreiras")
    tabela_samavi = calcular_tabela_op(df_samavi, "São Félix")
    tabela_bahia = calcular_tabela_op(df_bahia_raw, "Bahia")

    tabela_diaria = (
        df_filtrado.pivot_table(
            index="data",
            columns="operacao",
            values="hl_puxado",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )

    if not tabela_diaria.empty:
        tabela_diaria["data"] = tabela_diaria["data"].dt.strftime("%d/%m/%Y")

    return (
        tabela_barreiras,
        tabela_samavi,
        tabela_bahia,
        tabela_diaria,
        dias_preenchidos,
    )


# =========================================================
# 2. CONFIGURAÇÃO DA INTERFACE & NAVEGAÇÃO LATERAL
# =========================================================
st.set_page_config(
    page_title="Gestão DPO & Distribuição - Grupo Lima",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Grupo Lima")
st.sidebar.caption("Usuário: **admin** | Perfil: **Master**")

unidade_selecionada = st.sidebar.selectbox(
    "Unidade / Operação",
    ["Lima Rio Verde", "Lima Bahia (Barreiras)", "Samavi (São Félix)"],
)

st.sidebar.markdown("---")

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
    "Acesso Master (Gestão de Usuários)",
]

departamento = st.sidebar.radio(
    "Departamentos Integrados", DEPARTAMENTOS_DISPONIVEIS, index=2
)# =========================================================
# 3. MÓDULO DE RESSUPRIMENTO & EXIBIÇÃO DE TABELAS
# =========================================================
if departamento == "Ressuprimento":
    st.title("📈 Gestão de Ressuprimento & Acompanhamento de Cestas")

    sub_ress = st.tabs([
        "📊 Estoque Geral",
        "📦 Estoque do Dia",
        "🛒 Sugestão de Compra",
        "📈 Puxada, Consolidado Bahia & Dia a Dia",
    ])

    with sub_ress[3]:
        st.subheader("📁 Upload Base Diária & Processamento Automático")
        st.write(
            "Selecione o arquivo da base de ressuprimento (.xlsx, .xls ou .csv). "
            "O sistema fará a leitura automática mapeando as colunas **A (Operação)**, **C (HL Puxado)**, **E (Indicador)** e **F (Data)**."
        )

        f_ped = st.file_uploader(
            "Upload Base Ressuprimento / Puxada (.xlsx, .xls, .csv)",
            type=["xlsx", "xls", "csv"],
            key="up_ped_d012",
        )

        if f_ped is not None:
            try:
                # 1. Processamento e Mapeamento por Posição de Coluna
                df_base = processar_base_ressuprimento(f_ped, ano=2026, mes=8)

                # 2. Cálculo dos Indicadores por Unidade, Bahia e Dia a Dia
                (
                    tab_barreiras,
                    tab_samavi,
                    tab_bahia,
                    tab_diaria,
                    dias_preenchidos,
                ) = gerar_relatorio_puxada(df_base, ano=2026, mes=8)

                st.success(
                    f"Base processada com sucesso! **{dias_preenchidos} dia(s)** com movimentação apurada no mês."
                )

                # Visão 1: Consolidado Bahia (Barreiras + São Félix)
                st.subheader(
                    "🔴 Consolidado Bahia (Barreiras + São Félix - Samavi)"
                )
                st.dataframe(
                    tab_bahia.style.format({
                        "META": "{:,.2f}",
                        "REAL": "{:,.2f}",
                        "TEND.": "{:,.2f}",
                        "ATING. REAL": "{:.1f}%",
                        "ATING. TEND.": "{:.1f}%",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

                # Visão 2: Detalhamento Barreiras
                st.subheader("🔵 Detalhamento Barreiras")
                st.dataframe(
                    tab_barreiras.style.format({
                        "META": "{:,.2f}",
                        "REAL": "{:,.2f}",
                        "TEND.": "{:,.2f}",
                        "ATING. REAL": "{:.1f}%",
                        "ATING. TEND.": "{:.1f}%",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

                # Visão 3: Detalhamento São Félix (Samavi)
                st.subheader("🟢 Detalhamento São Félix (Samavi)")
                st.dataframe(
                    tab_samavi.style.format({
                        "META": "{:,.2f}",
                        "REAL": "{:,.2f}",
                        "TEND.": "{:,.2f}",
                        "ATING. REAL": "{:.1f}%",
                        "ATING. TEND.": "{:.1f}%",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

                # Visão 4: Acompanhamento Dia a Dia
                st.subheader("📅 Acompanhamento da Puxada Dia a Dia (HL)")
                st.dataframe(
                    tab_diaria, use_container_width=True, hide_index=True
                )

            except Exception as e:
                st.error(f"Erro ao processar a base de dados: {e}")

else:
    st.title(f"📌 Módulo: {departamento}")
    st.info(
        f"Módulo **{departamento}** ativado e vinculado à operação **{unidade_selecionada}**."
    )
