"""🏛️ Gestão Corporativa — visão por área.

Prontos: 💰 Financeiro › 🛒 Compras de Mercadoria · 🚚 Logística › Produtividade Entrega ·
📈 Vendas › 💵 Faturamento · 📥 Relatórios (uploads) · ⚙️ Cadastros (operações por setor).
As demais áreas mostram o que vai entrar e dão atalho para as pastas que já existem no sistema.
"""
import streamlit as st

from core import session, tema, ui
from core.auth import pode_acessar_modulo
from modules.corporativo import cadastros, estoque_dre, faturamento, prod_entrega, relatorios, remun_ambev

_PLANO = {
    "gente": ("👥 Gente", "Quadro, absenteísmo, turnover, horas extras e treinamentos por revenda.", "gente"),
    "seguranca": ("🦺 Segurança", "Acidentes, incidentes, DDS, inspeções e dias sem acidente.", "gente"),
}


def _planejamento(usuario: dict, operacao_id: int) -> None:
    """🗓️ Planejamento: capex do próximo ano e o orçamento (simulador OBZ)."""
    from modules.financeiro import capex, obz_sim

    tema.secao("🗓️ Planejamento do próximo ano",
               "Capex (investimentos) e orçamento OBZ — o capex aprovado entra no simulador como custo mensal.")
    aba = ui._escolha("corp_plan_aba", ["capex", "orcamento"], "capex", pills=True,
                      formatar={"capex": "🏗️ Gestão de Capex", "orcamento": "🧮 Orçamento (Simulador OBZ)"}.get)
    if aba == "capex":
        capex.render(usuario, operacao_id)
    else:
        obz_sim.render(usuario, operacao_id)


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


def _painel(usuario: dict, operacao_id: int) -> None:
    from modules.corporativo import painel_resultados

    painel_resultados.render(usuario, operacao_id)


def _agente(usuario: dict, operacao_id: int) -> None:
    from modules.corporativo import agente

    agente.render(usuario, operacao_id)


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("corporativo")
    abas = {a: (lambda u, o, a=a: _em_construcao(u, a)) for a in _PLANO}
    abas.update({"prod_entrega": prod_entrega.render, "remun_ambev": remun_ambev.render, "faturamento": faturamento.render_faturamento,
                 "compras": faturamento.render_compras, "margem": faturamento.render_margem,
                 "vendas_fin": lambda u, o: faturamento.render_faturamento(u, o, "💰 Financeiro › **💵 Vendas**"), "relatorios": relatorios.render, "cadastros": cadastros.render,
                 "estoque_valor": estoque_dre.render_estoque, "dre": estoque_dre.render_dre,
                 "planejamento": _planejamento, "gestao": _painel, "agente": _agente})
    ui.abas_modulo(usuario, "corporativo", abas, usuario, operacao_id)
