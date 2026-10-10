"""Início — painel executivo com os indicadores das pastas liberadas ao usuário."""
import streamlit as st

from config.settings import StatusFrete
from core import graficos, session, tema, ui
from core.auth import e_master, pode_acessar_aba, pode_acessar_modulo
from repositories import fretes_repo, ressuprimento_repo
from services import armazem_service, bases_service, fretes_service, ressuprimento_service


def _bloco_alertas(usuario: dict, operacao_id: int) -> None:
    """Bases vencidas = primeira coisa que o time precisa saber."""
    if not pode_acessar_modulo(usuario, "ressuprimento"):
        return
    nomes = {"estoque": "02.03.04 (estoque)", "pedidos_marcados": "Puxada marcada", "linear": "Linear",
             "produtos": "01.11 (cadastro)"}
    vencidas = []
    for base, nome in nomes.items():
        s = bases_service.situacao(base, operacao_id)
        if s["status"] in ("atencao", "critico"):
            vencidas.append(f"{nome}: {s['rotulo'].lower()} ({bases_service.idade_txt(s['idade_dias'])})")
    if vencidas:
        st.warning("**Bases para atualizar** — " + " · ".join(vencidas))


def _ir(pagina: str):
    """Card do Início leva direto para a pasta."""
    def acao():
        session.ir_para(pagina)
        st.rerun()
    return acao


def render(usuario: dict, operacao_id: int) -> None:
    primeiro = usuario["nome"].split()[0]
    ui.cabecalho(f"Olá, {primeiro}!", "Resumo do dia das suas pastas", "👋")
    operacao_id = ui.visao_acompanhamento(usuario, operacao_id, "inicio")
    _bloco_alertas(usuario, operacao_id)
    from repositories import motoristas_repo

    avisos = motoristas_repo.notificacoes(usuario["id"], apenas_nao_lidas=True, limite=5)
    if avisos:
        with st.container(border=True):
            a, b = st.columns([5, 1.2])
            a.markdown(f"**🔔 {len(avisos)} aviso(s) para você** — " + " · ".join(n["titulo"] for n in avisos[:3]))
            if b.button("Ver avisos ›", key="ini_notif", **ui.LARGURA):
                session.ir_para("notificacoes")
                st.rerun()
    mes = ui.mes_atual()
    cards, mostrou = [], False

    if pode_acessar_modulo(usuario, "puxada"):
        r = fretes_service.resumo_obz(operacao_id, mes)
        pend = fretes_repo.listar_df(operacao_id, [StatusFrete.PENDENTE],
                                     aprovador_id=None if e_master(usuario) else usuario["id"])
        cards += [
            {"titulo": "Fretes aguardando aprovação", "valor": len(pend), "icone": "⏳",
             "status": "atencao" if len(pend) else "bom", "selo": "fila vazia" if not len(pend) else "aprovar",
             "dados": pend[["id", "data_frete", "origem", "destino", "transportadora", "valor_negociado",
                            "solicitante", "aprovador"]] if not pend.empty else pend,
             "colunas": {"valor_negociado": st.column_config.NumberColumn("Valor", format="R$ %.2f")}},
            {"titulo": f"Frete de {ui.nome_mes(mes)}", "valor": ui.moeda(r["realizado"]), "icone": "🚚",
             "detalhe": f"{ui.pct(r['pct'])} da meta OBZ" if r["meta"] else "sem meta OBZ",
             "status": tema.status_atingimento(r["pct"], invertido=True) if r["meta"] else "neutro",
             "ao_clicar": _ir("puxada"), "ver": "Puxada"},
        ]
        if pode_acessar_aba(usuario, "puxada", "carreteiro"):
            from repositories import carreteiro_repo
            from services import carreteiro_service

            v = carreteiro_repo.viagens_df(operacao_id)
            ativas = v[v["status"] == carreteiro_repo.EM_VIAGEM] if not v.empty else v
            cards.append({
                "titulo": "Carretas em viagem (App)", "valor": len(ativas), "icone": "🚛", "status": "info",
                "detalhe": f"{len(carreteiro_service.placas_na_revenda(operacao_id))} placa(s) parada(s) na revenda",
                "ao_clicar": _ir("puxada"), "ver": "Puxada"})
    if pode_acessar_modulo(usuario, "ressuprimento") or pode_acessar_modulo(usuario, "armazem"):
        a = armazem_service.resumo(operacao_id)
        cards += [
            {"titulo": "DOI médio", "valor": f"{ui.numero(a['doi_medio'], 1)} dias", "icone": "⏱️", "status": "info",
             "ao_clicar": _ir("ressuprimento" if pode_acessar_modulo(usuario, "ressuprimento") else "armazem"),
             "ver": "estoque"},
            {"titulo": "Rupturas", "valor": a["rupturas"], "icone": "⛔", "status": tema.status_contagem(a["rupturas"], 1, 3),
             "selo": "sem ruptura" if not a["rupturas"] else "agir hoje",
             "ao_clicar": _ir("ressuprimento" if pode_acessar_modulo(usuario, "ressuprimento") else "armazem"),
             "ver": "estoque"},
            {"titulo": "Ocupação do armazém", "valor": ui.pct(a["ocup_paletes"]) if a["cap_paletes"] else "—",
             "icone": "🧱", "status": tema.status_ocupacao(a["ocup_paletes"]) if a["cap_paletes"] else "neutro",
             **({"ao_clicar": _ir("armazem"), "ver": "Armazém"} if pode_acessar_modulo(usuario, "armazem") else {})},
        ]
    if pode_acessar_aba(usuario, "puxada", "descarga") or pode_acessar_aba(usuario, "armazem", "patio"):
        from repositories import logistica_repo
        hoje = ui.hoje()
        ag = logistica_repo.agendamentos_df(operacao_id, hoje, hoje)
        pend = int((~ag["status"].isin(["Descarregado", "Cancelado", "No-show"])).sum()) if not ag.empty else 0
        cards.append({"titulo": "Descargas hoje", "valor": len(ag), "icone": "🅿️", "status": "info",
                      "detalhe": f"{pend} ainda não descarregada(s)" if len(ag) else "nenhuma agendada",
                      "dados": ag.drop(columns=["id", "viagem_id"]) if not ag.empty else ag})
    if pode_acessar_aba(usuario, "financeiro", "contas"):
        from services import financeiro_service
        from repositories import operacoes_repo
        d = {} if operacoes_repo.e_consolidada(operacao_id) else financeiro_service.diagnostico(operacao_id)
        if d:
            cards.append({"titulo": "Contas vencidas", "valor": ui.moeda(d["vencidos"]), "icone": "⏰",
                          "detalhe": f"{ui.moeda(d['prox7'])} vencem em 7 dias",
                          "status": "critico" if d["vencidos"] else "bom", "ao_clicar": _ir("financeiro"),
                          "ver": "Financeiro"})
    if pode_acessar_modulo(usuario, "ressuprimento"):
        meses = ressuprimento_repo.meses_disponiveis(operacao_id)
        mes_r = mes if mes in meses else (meses[0] if meses else mes)
        ad = ressuprimento_service.aderencia_mensal(operacao_id, mes_r)
        meta, proj = ad["meta_hl"].sum(), ad["projecao_hl"].sum()
        cards.append({"titulo": f"Ressuprimento {ui.nome_mes(mes_r)}", "valor": f"{ui.compacto(ad['real_hl'].sum())} HL",
                      "icone": "🔄", "detalhe": f"projeção {ui.pct(proj / meta * 100)} da meta" if meta else "sem metas",
                      "status": tema.status_atingimento(proj / meta * 100 if meta else None),
                      "dados": ad, "ver": "cestas"})
    if cards:
        tema.kpis(cards, key="kp_inicio")

    g1, g2 = st.columns(2)
    if pode_acessar_aba(usuario, "puxada", "obz") or pode_acessar_aba(usuario, "puxada", "painel"):
        hist = fretes_service.historico_obz(operacao_id).tail(6)
        if not hist.empty:
            with g1:
                graficos.mostrar(graficos.real_x_meta(hist, "mes_ano", "realizado", "meta", "Frete x meta OBZ — 6 meses (R$)",
                                                      "R$", invertido=True,
                                                      rotulos_x=[ui.nome_mes(m) for m in hist["mes_ano"]]), key="g_ini_obz")
                mostrou = True
    if pode_acessar_aba(usuario, "ressuprimento", "estoque"):
        pos = armazem_service.posicao_com_indicadores(operacao_id)
        if not pos.empty:
            with g2:
                ordem = ["Ruptura", "Crítico", "Abaixo da meta", "OK", "Excesso", "Sem giro"]
                cont = pos["situacao"].value_counts().reindex(ordem).dropna()
                graficos.mostrar(graficos.barras_h(cont.index, cont.values,
                                                   cores=[graficos.COR_SITUACAO[s] for s in cont.index],
                                                   titulo="Saúde do estoque — SKUs por situação"), key="g_ini_est",
                                 detalhe=(pos, "situacao"), titulo="Situação")
                mostrou = True
    if pode_acessar_aba(usuario, "ressuprimento", "cestas"):
        meses = ressuprimento_repo.meses_disponiveis(operacao_id)
        if meses:
            ad = ressuprimento_service.aderencia_mensal(operacao_id, meses[0])
            com_meta = ad[ad["meta_hl"] > 0].sort_values("atingimento_proj")
            if not com_meta.empty:
                graficos.mostrar(graficos.barras_h(
                    com_meta["cesta"], com_meta["atingimento_proj"].fillna(0), sufixo="%",
                    cores=[tema.STATUS[tema.status_atingimento(p)][0] for p in com_meta["atingimento_proj"]],
                    titulo=f"Ressuprimento {ui.nome_mes(meses[0])} — projeção de atingimento por cesta"), key="g_ini_ces",
                    detalhe=(com_meta, "cesta"), titulo="Cesta")
                mostrou = True
    if not cards and not mostrou:
        st.info("Escolha uma pasta no menu ao lado para começar.")
