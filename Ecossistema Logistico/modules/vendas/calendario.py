"""Vendas › 📅 Calendário de Vendas — os dias em que a revenda vende no mês. A tendência do Acompanhamento Sell-out
= real ÷ dias de venda já feitos × dias de venda do mês."""
import datetime as dt

import streamlit as st

from core import tema, tempo, ui
from repositories import operacoes_repo
from services import gestao_metas_service as gm
from services.erros import RegraNegocioError

_SEM = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
          "novembro", "dezembro"]


def render(usuario: dict, operacao_id: int) -> None:
    hoje = tempo.hoje()
    opcoes = []
    a, m = hoje.year, hoje.month
    for k in range(-2, 4):
        mm, aa = m + k, a
        while mm < 1:
            mm, aa = mm + 12, aa - 1
        while mm > 12:
            mm, aa = mm - 12, aa + 1
        opcoes.append(f"{aa}-{mm:02d}")
    c1, _ = st.columns([1, 3])
    mes = c1.selectbox("Mês", opcoes, index=2, key="vcal_mes",
                       format_func=lambda x: f"{_MESES[int(x[5:]) - 1].capitalize()}/{x[:4]}")
    dias, salvo = gm.calendario_vendas(operacao_id, mes)
    marcados = set(dias)
    feitos = [d for d in dias if d <= hoje]
    restantes = [d for d in dias if d > hoje]
    fator = len(dias) / len(feitos) if feitos and len(feitos) < len(dias) else 1.0
    tema.kpis([
        {"titulo": "Dias de venda no mês", "valor": str(len(dias)), "icone": "📅", "status": "info",
         "detalhe": "calendário salvo" if salvo else "padrão: segunda a sábado (ainda não salvo)"},
        {"titulo": "Já vendidos", "valor": str(len(feitos)), "icone": "✅", "status": "bom",
         "detalhe": f"até {hoje:%d/%m}" if mes == hoje.strftime("%Y-%m") else ""},
        {"titulo": "Restantes", "valor": str(len(restantes)), "icone": "⏳",
         "status": "atencao" if restantes else "bom"},
        {"titulo": "Fator da tendência", "valor": f"× {fator:.2f}".replace(".", ","), "icone": "🔮", "status": "info",
         "detalhe": "dias do mês ÷ dias já vendidos"},
    ], key="kp_vcal")
    consolidada = operacoes_repo.e_consolidada(operacao_id)
    if consolidada:
        st.info("Visão consolidada: mostrando o calendário da primeira filial. Escolha uma filial para marcar.")
    st.caption("Marque os dias em que há venda (feriados, domingos e dias sem rota ficam desmarcados). O "
               "📈 Acompanhamento Sell-out usa estes dias para a tendência de fechamento.")
    b1, b2, b3, _ = st.columns([1, 1, 1, 2])
    todos = gm.dias_do_mes(mes)
    preset = None
    if b1.button("Seg a sáb", key="vcal_p1"):
        preset = {d for d in todos if d.weekday() < 6}
    if b2.button("Seg a sex", key="vcal_p2"):
        preset = {d for d in todos if d.weekday() < 5}
    if b3.button("Todos os dias", key="vcal_p3"):
        preset = set(todos)
    if preset is not None:
        for d in todos:
            st.session_state[f"vcal_{operacao_id}_{d.isoformat()}"] = d in preset
    with st.form(f"vcal_form_{operacao_id}_{mes}", border=True):
        cols = st.columns(7)
        for i, s in enumerate(_SEM):
            cols[i].markdown(f"**{s}**")
        semana = [None] * todos[0].weekday() + todos
        for i in range(0, len(semana), 7):
            linha = st.columns(7)
            for j, d in enumerate(semana[i:i + 7]):
                if d is None:
                    continue
                k = f"vcal_{operacao_id}_{d.isoformat()}"
                st.session_state.setdefault(k, d in marcados)
                rot = f"{d.day:02d}" + (" 🔵" if d == hoje else "")
                linha[j].checkbox(rot, key=k, disabled=consolidada)
        if st.form_submit_button("💾 Salvar calendário", type="primary", disabled=consolidada):
            sel = [d for d in todos if st.session_state.get(f"vcal_{operacao_id}_{d.isoformat()}")]
            try:
                gm.salvar_calendario_vendas(operacao_id, mes, sel)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(f"Calendário salvo: {len(sel)} dia(s) de venda.")
                st.rerun()
