"""📥 Atualizar relatórios — um lugar só para subir todas as bases (Ambev, vendas e financeiro).

As outras telas mostram se a base está em dia e trazem um botão que abre esta página.
"""
import streamlit as st

from core import session, tema
from core.auth import pode_acessar_modulo
from modules.componentes.bases import card_base

# (layout, título, frequência, módulos que usam a base)
GRUPOS = [
    ("📦 Estoque, Puxada & Ressuprimento", [
        ("produtos", "1. Relatório 01.11", "Cadastro · quando mudar", ("ressuprimento", "armazem", "puxada")),
        ("linear", "2. Relatório Linear", "A cada 3 meses · embalagem e venda/dia", ("ressuprimento", "armazem", "vendas")),
        ("estoque", "3. Relatório 02.03.04", "Diário · posição de estoque", ("ressuprimento", "armazem", "puxada", "vendas")),
        ("pedidos_marcados", "4. Puxada Marcada", "Diário · um arquivo só (D0, D1, D2 pela data)",
         ("ressuprimento", "armazem", "puxada")),
        ("ressuprimento", "5. Ressuprimento diário", "Diário · todas as filiais (A, C, E, F)", ("ressuprimento", "puxada")),
        ("politica", "6. Política de estoque", "Semanal · mín/obj/máx", ("ressuprimento",)),
        ("metas_doi", "7. Metas de DOI por SKU", "Quando revisar", ("ressuprimento",)),
    ]),
    ("📈 Vendas", [
        ("curva_abc", "Curva ABC", "Mensal · volume por SKU", ("vendas",)),
    ]),
    ("💰 Financeiro", [
        ("financeiro", "Relatório diário de pagamentos", "Diário · substitui os dados da filial", ("financeiro",)),
    ]),
]
MODULOS_COM_BASE = {m for _, itens in GRUPOS for *_, ms in itens for m in ms}


def pode_ver(usuario: dict) -> bool:
    return any(pode_acessar_modulo(usuario, m) for m in MODULOS_COM_BASE)


def ir() -> None:
    """Abre a central de relatórios (usado pelos botões das outras telas)."""
    session.ir_para("bases")
    st.rerun()


def botao_ir(chave: str, rotulo: str = "📥 Abrir a central de relatórios") -> None:
    if st.button(rotulo, key=f"ir_bases_{chave}", type="primary"):
        ir()


def render(usuario: dict, operacao_id: int) -> None:
    tema.cabecalho("Atualizar relatórios", "Todas as bases do sistema em um lugar só — envie o arquivo e o sistema "
                   "reconhece as colunas e grava sozinho.", "📥",
                   [f"🏢 {session.operacao_nome()}", "🟢 em dia · 🟡 atualizar · 🔴 desatualizada"])
    algum = False
    for titulo, itens in GRUPOS:
        visiveis = [i for i in itens if any(pode_acessar_modulo(usuario, m) for m in i[3])]
        if not visiveis:
            continue
        algum = True
        tema.secao(titulo)
        for ini in range(0, len(visiveis), 4):
            for col, (lay, tit, freq, _) in zip(st.columns(4), visiveis[ini:ini + 4]):
                with col:
                    card_base(lay, operacao_id, usuario, tit, freq, prefixo="central_")
    if not algum:
        st.info("Você não tem acesso a nenhuma pasta que use relatórios.")
    st.caption("O Ressuprimento diário traz todas as filiais num arquivo só. As demais bases são da revenda "
               "escolhida no menu ao lado.")
