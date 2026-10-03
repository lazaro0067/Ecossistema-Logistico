"""Tela inicial — resumo rápido dos módulos liberados ao usuário."""
import streamlit as st

from config.settings import StatusFrete
from core import session, ui
from core.auth import e_master, pode_acessar_modulo
from repositories import fretes_repo
from services import armazem_service, fretes_service


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho(f"Olá, {usuario['nome'].split()[0]} 👋", f"Resumo de {session.operacao_nome()} · {ui.mes_atual()}")

    if pode_acessar_modulo(usuario, "puxada"):
        st.subheader("🚚 Puxada")
        r = fretes_service.resumo_obz(operacao_id, ui.mes_atual())
        pend = fretes_repo.listar_df(operacao_id, [StatusFrete.PENDENTE],
                                     aprovador_id=None if e_master(usuario) else usuario["id"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Aguardando sua aprovação", len(pend))
        c2.metric("Frete do mês", ui.moeda(r["realizado"]))
        c3.metric("Meta OBZ", ui.moeda(r["meta"]))
        c4.metric("% da meta", ui.pct(r["pct"]) if r["meta"] else "—")

    if pode_acessar_modulo(usuario, "armazem"):
        st.subheader("📦 Armazém")
        a = armazem_service.resumo(operacao_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("SKUs em estoque", a["skus"])
        c2.metric("DOI médio", f"{ui.numero(a['doi_medio'], 1)} dias")
        c3.metric("Rupturas", a["rupturas"])
        c4.metric("Ocupação (paletes)", ui.pct(a["ocup_paletes"]) if a["cap_paletes"] else "—")
