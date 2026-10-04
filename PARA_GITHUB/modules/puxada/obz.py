"""Puxada › OBZ de frete (Real x Meta) — a meta salva automaticamente."""
import streamlit as st

from core import graficos, tema, ui
from core.auth import e_master
from repositories import fretes_repo
from services import fretes_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    c1, c2 = st.columns([1, 1])
    mes = c1.text_input("Mês (AAAA-MM)", value=ui.mes_atual(), key="obz_mes")
    r = svc.resumo_obz(operacao_id, mes)

    pode_editar = e_master(usuario) or usuario.get("perfil") == "Gestor"
    if pode_editar:
        chave = f"obz_meta_{operacao_id}_{mes}"

        def _salvar_meta():
            fretes_repo.salvar_meta(operacao_id, mes, float(st.session_state[chave] or 0))
            ui.avisar(f"Meta de {ui.nome_mes(mes)} salva automaticamente")

        c2.number_input(f"🎯 Meta OBZ de {ui.nome_mes(mes)} (R$) — salva ao sair do campo", min_value=0.0,
                        value=r["meta"], step=1000.0, key=chave, on_change=_salvar_meta)

    comprometido = r["realizado"] + r["pendente"]
    tema.kpis([
        {"titulo": "Meta OBZ", "valor": ui.moeda(r["meta"]) if r["meta"] else "Sem meta", "icone": "🎯",
         "status": "info" if r["meta"] else "neutro"},
        {"titulo": "Realizado (aprovado + finalizado)", "valor": ui.moeda(r["realizado"]), "icone": "💸",
         "detalhe": f"{ui.pct(r['pct'])} da meta" if r["meta"] else "",
         "status": tema.status_atingimento(r["pct"], invertido=True) if r["meta"] else "info"},
        {"titulo": "Saldo disponível", "valor": ui.moeda(r["saldo"]), "icone": "💰",
         "status": ("bom" if r["saldo"] > 0 else "critico") if r["meta"] else "neutro",
         "selo": None if not r["meta"] else ("Dentro do orçamento" if r["saldo"] > 0 else "Estourado")},
        {"titulo": "Em aprovação", "valor": ui.moeda(r["pendente"]), "icone": "⏳",
         "detalhe": "se aprovado, estoura a meta" if r["meta"] and comprometido > r["meta"] else "",
         "status": "serio" if r["meta"] and comprometido > r["meta"] else "info"},
    ])

    hist = svc.historico_obz(operacao_id).tail(12)
    if not hist.empty:
        graficos.mostrar(graficos.real_x_meta(hist, "mes_ano", "realizado", "meta", "Frete realizado x meta OBZ (R$)",
                                              "R$", invertido=True, rotulos_x=[ui.nome_mes(m) for m in hist["mes_ano"]]),
                         key="g_obz")
        st.caption("Cor da barra: 🟢 até 90% da meta · 🟡 até 100% · 🟠 até 110% · 🔴 acima de 110%.")
    ui.tabela(hist, column_config={"mes_ano": "Mês", "meta": st.column_config.NumberColumn("Meta", format="R$ %.0f"),
                                   "realizado": st.column_config.NumberColumn("Realizado", format="R$ %.0f"),
                                   "saldo": st.column_config.NumberColumn("Saldo", format="R$ %.0f")})
