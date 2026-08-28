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

            df_cerveja_nab = df_comp[
                df_comp["INDICADOR"].isin(["Cerveja", "Nab"])
            ]
            tot_meta = df_cerveja_nab["META"].sum()
            tot_real = df_cerveja_nab["REAL"].sum()
            tot_tend = df_cerveja_nab["TEND."].sum()
            tot_pend = tot_real - tot_meta

            tot_ating_real = (
                (tot_real / tot_meta * 100) if tot_meta > 0 else 0.0
            )
            tot_ating_tend = (
                (tot_tend / tot_meta * 100) if tot_meta > 0 else 0.0
            )

            df_total = pd.DataFrame([{
                "INDICADOR": f"Total {nome_exibicao_op} (Cerveja + Nab)",
                "META": tot_meta,
                "REAL": tot_real,
                "TEND.": tot_tend,
                "ATING. REAL": tot_ating_real,
                "ATING. TEND.": tot_ating_tend,
                "PENDÊNCIA PERÍODO": tot_pend,
            }])

            meses_str = ", ".join([
                meses_nomes[m - 1] for m in meses_selecionados
            ])
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
            # Ajuste aplicado para trazer os números inteiros formatados no padrão ex: 25.786
            df_view["META"] = df_view["META"].apply(formatar_inteiro_br)
            df_view["REAL"] = df_view["REAL"].apply(formatar_inteiro_br)
            df_view["TEND."] = df_view["TEND."].apply(formatar_inteiro_br)
            df_view["ATING. REAL"] = df_view["ATING. REAL"].apply(
                format_atingimento_com_condicional
            )
            df_view["ATING. TEND."] = df_view["ATING. TEND."].apply(
                format_atingimento_com_condicional
            )
            df_view["PENDÊNCIA PERÍODO"] = df_view["PENDÊNCIA PERÍODO"].apply(
                formatar_inteiro_br
            )

            st.dataframe(
                df_view,
                use_container_width=True,
                height=(len(df_view) + 1) * 38 + 5,
            )

            st.markdown("##### 📥 Opções de Download do Relatório Mensal")
            render_botoes_download(df_final, f"Acompanhamento_Mensal_{operacao}")

        else:
            st.info(
                f"ℹ️ Verifique se há dados diários cadastrados para **{nome_exibicao_op}** no ano de {ano_sel}."
            )
