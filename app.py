# -----------------------------------------------------------------------------
# GESTÃO DE RESSUPRIMENTO (CESTAS, METAS, TENDÊNCIA & LAYOUT POR OPERAÇÃO)
# -----------------------------------------------------------------------------
def render_gestao_ressuprimento(operacao):
    st.subheader("📈 Gestão de Ressuprimento & Acompanhamento de Cestas")

    # Mapeamento da Operação Ativa para os nomes do Relatório Ambev
    # Rio Verde -> Lima - Rio Verde | Barreiras -> Lima Bahia | São Félix -> Lima Bahia Samavi
    mapa_op_sistema = {
        "Lima Rio Verde": ["Lima - Rio Verde", "Rio Verde", "Lima Rio Verde"],
        "Lima Barreiras": ["Lima Bahia", "Barreiras", "Lima Barreiras"],
        "Lima São Félix": ["Lima Bahia Samavi", "Samavi", "São Félix", "Lima São Félix"],
    }
    
    nombres_filtro = mapa_op_sistema.get(operacao, [operacao])
    nome_exibicao_op = operacao.replace("Lima ", "")

    tab_m1, tab_m2, tab_m3 = st.tabs([
        "📊 Acompanhamento Mensal & Volume Total",
        "⚙️ Configuração de Metas Mensais",
        "📁 Upload & Atualização da Base Diária",
    ])

    # Mapeamento amigável de Cestas
    cestas_map = {
        "CATEGORIA_AGRUPADO - CERVEJA": "Cerveja",
        "CATEGORIA_AGRUPADO - NAB": "Nab",
        "CATEGORIA - MATCH": "Match",
        "CATEGORIA_RETORNAVEL - CERVEJA RGB": "Cerveja RGB",
        "REFRIGERANTE_REGULAR_NAB - ZERO": "Nab Zero",
        "CERV_2 - Zero Alcool": "Cerveja Zero Alcool",
        "SEGMENTO - HIGH END": "High End",
    }

    cestas_ordenadas = [
        "CATEGORIA_AGRUPADO - CERVEJA",
        "CATEGORIA_AGRUPADO - NAB",
        "CATEGORIA - MATCH",
        "CATEGORIA_RETORNAVEL - CERVEJA RGB",
        "REFRIGERANTE_REGULAR_NAB - ZERO",
        "CERV_2 - Zero Alcool",
        "SEGMENTO - HIGH END",
    ]

    # TAB 1: VISUALIZAÇÃO NO LAYOUT IDENTICO AO PRINT
    with tab_m1:
        c_f1, c_f2 = st.columns(2)
        ano_sel = c_f1.number_input("Ano de Análise:", min_value=2024, max_value=2030, value=datetime.now().year)
        mes_sel = c_f2.selectbox(
            "Mês de Análise:",
            list(range(1, 13)),
            format_func=lambda x: [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ][x - 1],
            index=datetime.now().month - 1
        )

        mes_ano_str = f"{['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][mes_sel-1]}/{ano_sel}"

        conn = sqlite3.connect("puxada_ambev.db")
        # Filtra por operação do sistema
        df_diario = pd.read_sql_query(
            f"SELECT * FROM gestao_ressuprimento_diario WHERE operacao IN ({','.join(['?']*len(nombres_filtro))}) AND strftime('%Y', data_registro)='{ano_sel}'",
            conn,
            params=nombres_filtro
        )
        df_metas = pd.read_sql_query(
            f"SELECT * FROM metas_ressuprimento_mensal WHERE operacao IN ({','.join(['?']*len(nombres_filtro))}) AND ano={ano_sel} AND mes={mes_sel}",
            conn,
            params=nombres_filtro
        )
        conn.close()

        if not df_diario.empty:
            df_diario["data_dt"] = pd.to_datetime(df_diario["data_registro"], errors="coerce")
            df_diario_mes = df_diario[df_diario["data_dt"].dt.month == mes_sel]

            # Dicionário de dias preenchidos
            dias_preenchidos = df_diario_mes["data_dt"].dt.date.nunique()
            
            # Cálculo de dias totais no mês selecionado
            if mes_sel in [1, 3, 5, 7, 8, 10, 12]:
                dias_no_mes = 31
            elif mes_sel in [4, 6, 9, 11]:
                dias_no_mes = 30
            else:
                dias_no_mes = 29 if (ano_sel % 4 == 0 and (ano_sel % 100 != 0 or ano_sel % 400 == 0)) else 28

            # Agrupamento do Real por Cesta
            df_res_mes = df_diario_mes.groupby("cesta")["volume_sellin_hl"].sum().reset_index()

            # Merge com as Cestas Oficiais
            df_comp = pd.merge(
                pd.DataFrame({"cesta": cestas_ordenadas}),
                df_res_mes,
                on="cesta",
                how="left"
            ).fillna(0)

            # Merge com as Metas
            df_comp = pd.merge(
                df_comp,
                df_metas.groupby("cesta")["meta_volume_hl"].sum().reset_index(),
                on="cesta",
                how="left"
            ).fillna(0)

            # Cálculo da Tendência e Atingimentos
            fator_tend = (dias_no_mes / dias_preenchidos) if dias_preenchidos > 0 else 1.0

            df_comp["INDICADOR"] = df_comp["cesta"].map(cestas_map)
            df_comp["META"] = df_comp["meta_volume_hl"]
            df_comp["REAL"] = df_comp["volume_sellin_hl"]
            df_comp["TEND."] = df_comp["REAL"] * fator_tend

            df_comp["ATING. REAL"] = df_comp.apply(
                lambda r: (r["REAL"] / r["META"] * 100) if r["META"] > 0 else 0.0, axis=1
            )
            df_comp["ATING. TEND."] = df_comp.apply(
                lambda r: (r["TEND."] / r["META"] * 100) if r["META"] > 0 else 0.0, axis=1
            )

            # Linha de Totalização
            tot_meta = df_comp["META"].sum()
            tot_real = df_comp["REAL"].sum()
            tot_tend = df_comp["TEND."].sum()
            tot_ating_real = (tot_real / tot_meta * 100) if tot_meta > 0 else 0.0
            tot_ating_tend = (tot_tend / tot_meta * 100) if tot_meta > 0 else 0.0

            df_total = pd.DataFrame([{
                "INDICADOR": f"Total {nome_exibicao_op}",
                "META": tot_meta,
                "REAL": tot_real,
                "TEND.": tot_tend,
                "ATING. REAL": tot_ating_real,
                "ATING. TEND.": tot_ating_tend,
            }])

            # Header igual ao do Print
            st.markdown(
                f"""
                <div style="background-color: #0d2149; color: white; padding: 12px 20px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                    <h3 style="margin:0; font-size: 20px; color: white;">🔵 {nome_exibicao_op}</h3>
                    <span style="font-size: 13px; color: #b0c4de;">Detalhamento por indicador · {dias_preenchidos} dia(s) preenchido(s)</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Concatena a tabela de indicadores com o total
            df_final = pd.concat([
                df_comp[["INDICADOR", "META", "REAL", "TEND.", "ATING. REAL", "ATING. TEND."]],
                df_total
            ], ignore_index=True)

            # Estilização visual (Verde / Vermelho para atingimento)
            def style_ating_real(val):
                if isinstance(val, (int, float)):
                    color = "#28a745" if val >= 100 else "#dc3545"
                    return f"color: {color}; font-weight: bold;"
                return ""

            def style_ating_tend(val):
                if isinstance(val, (int, float)):
                    color = "#28a745" if val >= 100 else "#d97706"
                    return f"color: {color}; font-weight: bold;"
                return ""

            def style_real_val(val):
                if isinstance(val, (int, float)):
                    return "color: #28a745; font-weight: bold;"
                return ""

            def style_tend_val(val):
                if isinstance(val, (int, float)):
                    return "color: #8a2be2; font-weight: bold;"
                return ""

            format_dict = {
                "META": "{:,.0f}",
                "REAL": "{:,.2f}",
                "TEND.": "{:,.2f}",
                "ATING. REAL": "{:.1f}%",
                "ATING. TEND.": "{:.1f}%",
            }

            st.dataframe(
                df_final.style
                .format(format_dict)
                .map(style_real_val, subset=["REAL"])
                .map(style_tend_val, subset=["TEND."])
                .map(style_ating_real, subset=["ATING. REAL"])
                .map(style_ating_tend, subset=["ATING. TEND."]),
                use_container_width=True,
                height=(len(df_final) + 1) * 38 + 5
            )

        else:
            st.info(f"ℹ️ Nenhum dado diário encontrado para **{nome_exibicao_op}** neste mês ({mes_ano_str}). Faça o upload do relatório na aba 'Upload & Atualização'.")

    # TAB 2: CONFIGURAÇÃO DE METAS MENSAIS POR CESTA
    with tab_m2:
        st.markdown(f"### 🎯 Cadastrar / Ajustar Metas Mensais ({nome_exibicao_op})")
        c_m1, c_m2 = st.columns(2)
        ano_meta = c_m1.number_input("Ano da Meta:", min_value=2024, max_value=2030, value=datetime.now().year, key="ano_meta_key")
        mes_meta = c_m2.selectbox(
            "Mês da Meta:",
            list(range(1, 13)),
            format_func=lambda x: [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ][x - 1],
            index=datetime.now().month - 1,
            key="mes_meta_key"
        )

        mes_ano_meta_str = f"{['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][mes_meta-1]}/{ano_meta}"

        conn = sqlite3.connect("puxada_ambev.db")
        df_exist_metas = pd.read_sql_query(
            f"SELECT cesta, meta_volume_hl FROM metas_ressuprimento_mensal WHERE operacao IN ({','.join(['?']*len(nombres_filtro))}) AND ano={ano_meta} AND mes={mes_meta}",
            conn,
            params=nombres_filtro
        )
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
                for cst, m_val in input_metas.items():
                    cursor.execute("""
                    INSERT INTO metas_ressuprimento_mensal (operacao, ano, mes, mes_ano, cesta, meta_volume_hl, dt_atualizacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(operacao, ano, mes, cesta) DO UPDATE SET
                        meta_volume_hl=excluded.meta_volume_hl, dt_atualizacao=excluded.dt_atualizacao
                    """, (operacao, ano_meta, mes_meta, mes_ano_meta_str, cst, m_val, dt_now))
                conn.commit()
                conn.close()
                st.success(f"Metas de {mes_ano_meta_str} salvas com sucesso para {nome_exibicao_op}!")
                st.rerun()

    # TAB 3: UPLOAD E ATUALIZAÇÃO DA BASE DIÁRIA COM SUPORTE AOS NOMES AMBEV
    with tab_m3:
        st.markdown("### 📁 Upload do Relatório Diário de Ressuprimento")
        st.caption("Suba o arquivo consolidado contendo os volumes diários (.xlsx, .xls, .csv). O sistema mapeará automaticamente Samavi (São Félix), Lima Bahia (Barreiras) e Lima - Rio Verde (Rio Verde).")

        f_ress_daily = st.file_uploader(
            "Selecione o arquivo de relatório diário (.xlsx, .xls, .csv):",
            type=["xlsx", "xls", "csv"],
            key="up_ress_daily"
        )

        if f_ress_daily is not None and st.button("🚀 Processar e Atualizar Base de Dados"):
            try:
                df_up = robust_read_file(f_ress_daily)

                # Mapeamento por posição das colunas no arquivo Ambev:
                # Coluna A (0): Operação Antiga
                # Coluna C (2): Volume Sellin (hl) Real
                # Coluna E (4): Cesta
                # Coluna F (5): Data
                col_op = df_up.columns[0]
                col_sellin = df_up.columns[2]
                col_cesta = df_up.columns[4]
                col_data = df_up.columns[5]

                conn = sqlite3.connect("puxada_ambev.db")
                cursor = conn.cursor()
                dt_now = datetime.now().strftime("%d/%m/%Y %H:%M")

                registros_salvos = 0
                for _, r in df_up.dropna(subset=[col_cesta, col_data]).iterrows():
                    raw_op = str(r[col_op]).strip() if pd.notna(r[col_op]) else operacao

                    # Mapeia o nome bruto do arquivo Ambev para o nome da operação
                    if "Samavi" in raw_op:
                        op_salvar = "Lima Bahia Samavi"
                    elif "Lima Bahia" in raw_op:
                        op_salvar = "Lima Bahia"
                    elif "Rio Verde" in raw_op:
                        op_salvar = "Lima - Rio Verde"
                    else:
                        op_salvar = raw_op

                    cst_val = str(r[col_cesta]).strip()
                    dt_val = str(pd.to_datetime(r[col_data]).strftime("%Y-%m-%d"))
                    mes_ano_val = str(pd.to_datetime(r[col_data]).strftime("%b/%Y"))

                    s_hl = parse_br_float(r[col_sellin])

                    cursor.execute("""
                    INSERT INTO gestao_ressuprimento_diario (operacao, data_registro, mes_ano, cesta, volume_sellin_hl, volume_real_hl, dt_atualizacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(operacao, data_registro, cesta) DO UPDATE SET
                        volume_sellin_hl=excluded.volume_sellin_hl,
                        volume_real_hl=excluded.volume_sellin_hl,
                        dt_atualizacao=excluded.dt_atualizacao
                    """, (op_salvar, dt_val, mes_ano_val, cst_val, s_hl, s_hl, dt_now))
                    registros_salvos += 1

                conn.commit()
                conn.close()
                st.success(f"Base de dados atualizada! **{registros_salvos}** registros diários sincronizados para todas as unidades.")
                st.rerun()

            except Exception as e:
                st.error(f"Erro ao processar o arquivo: {e}")
