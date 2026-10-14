"""🏛️ Gestão Corporativa — visão por área.

Prontos: 💰 Financeiro › 🛒 Compras de Mercadoria · 🚚 Logística › Produtividade Entrega ·
📈 Vendas › 💵 Faturamento · 📥 Relatórios (uploads) · ⚙️ Cadastros (operações por setor).
As demais áreas mostram o que vai entrar e dão atalho para as pastas que já existem no sistema.
"""
import streamlit as st

from core import session, tema, ui
from core.auth import pode_acessar_modulo
from modules.corporativo import cadastros, faturamento, prod_entrega, relatorios

_PLANO = {
    "gente": ("👥 Gente", "Quadro, absenteísmo, turnover, horas extras e treinamentos por revenda.", "gente"),
    "seguranca": ("🦺 Segurança", "Acidentes, incidentes, DDS, inspeções e dias sem acidente.", "gente"),
    "gestao": ("📊 Gestão", "Painel único com os principais indicadores de todas as áreas (farol do grupo).", None),
    "planejamento": ("🗓️ Planejamento", "Orçamento, metas anuais e plano de ação por área.", None),
}


def _em_construcao(usuario: dict, aba: str) -> None:
    titulo, texto, atalho = _PLANO[aba]
    tema.secao(titulo, texto)
    st.info("🚧 Área em montagem. Envie os relatórios desta área e o que quer acompanhar que montamos a gestão aqui "
            "— igual à Produtividade Entrega e ao Faturamento.")
    if atalho and pode_acessar_modulo(usuario, atalho):
        from config.settings import MODULOS

        m = MODULOS[atalho]
        if st.button(f"Abrir {m['icone']} {m['rotulo']}", key=f"corp_ir_{aba}"):
            session.ir_para(atalho)
            st.rerun()


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("corporativo")
    abas = {a: (lambda u, o, a=a: _em_construcao(u, a)) for a in _PLANO}
    abas.update({"prod_entrega": prod_entrega.render, "faturamento": faturamento.render_faturamento,
                 "compras": faturamento.render_compras, "relatorios": relatorios.render, "cadastros": cadastros.render})
    ui.abas_modulo(usuario, "corporativo", abas, usuario, operacao_id)
