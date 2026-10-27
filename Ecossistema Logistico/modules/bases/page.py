"""📥 Atualizar relatórios — um lugar só para subir todas as bases (Ambev, vendas e financeiro).

As outras telas mostram se a base está em dia e trazem um botão que abre esta página.
"""
import streamlit as st

from core import session, tema
from core.auth import pode_acessar_modulo
from modules.componentes.bases import card_base

# frequência de cada base na central (📅 diário · 🗓️ mensal · 1️⃣ uma vez / quando mudar)
FREQ = {"estoque": "dia", "pedidos_marcados": "dia", "ressuprimento": "dia", "financeiro": "dia", "politica": "dia",
        "linear": "mes", "curva_abc": "mes", "produtos": "uma", "metas_doi": "uma"}
NOTAS_FREQ = {"dia": {"vendas", "compra", "pcd"}, "mes": {"estoque", "contab"}, "uma": {"operacoes"}}
ABAS_FREQ = {"dia": "📅 Diário (e semanal)", "mes": "🗓️ Mensal (e trimestral)", "uma": "1️⃣ Uma vez / quando mudar"}

# (layout, título, frequência, módulos que usam a base)
GRUPOS = [
    ("📦 Estoque, Puxada & Ressuprimento", [
        ("produtos", "1. Relatório 01.11", "Cadastro · quando mudar", ("ressuprimento", "armazem", "puxada")),
        ("linear", "2. Relatório Linear", "A cada 3 meses · embalagem e venda/dia", ("ressuprimento", "armazem", "vendas")),
        ("estoque", "3. Grade Cora", "A cada 2 h · entrada (grade) e disponível (DOI)", ("ressuprimento", "armazem", "puxada", "vendas")),
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


MODULOS_NOTAS = ("corporativo", "distribuicao", "puxada", "financeiro")  # PCD, 03.02.37, 02.05.02, contabilidade


def pode_ver(usuario: dict) -> bool:
    return any(pode_acessar_modulo(usuario, m) for m in (*MODULOS_COM_BASE, *MODULOS_NOTAS))


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
    _robo(operacao_id)
    from modules.corporativo import relatorios

    escolhida = relatorios.seletor_revenda(usuario, operacao_id, "central_op")
    if escolhida:
        operacao_id = escolhida
    from core import ui

    aba_freq = ui._escolha("central_freq", list(ABAS_FREQ), "dia", pills=True, formatar=ABAS_FREQ.get)
    algum = False
    for titulo, itens in GRUPOS:
        visiveis = [i for i in itens if any(pode_acessar_modulo(usuario, m) for m in i[3])
                    and FREQ.get(i[0], "uma") == aba_freq]
        if not visiveis:
            continue
        algum = True
        tema.secao(titulo)
        for ini in range(0, len(visiveis), 4):
            for col, (lay, tit, freq, _) in zip(st.columns(4), visiveis[ini:ini + 4]):
                with col:
                    card_base(lay, operacao_id, usuario, tit, freq, prefixo="central_")
    if escolhida and any(pode_acessar_modulo(usuario, m) for m in MODULOS_NOTAS):
        algum = True
        tema.secao("🚚 Entrega, Faturamento & DRE",
                   {"dia": "PCD e 03.02.37 vendas e compra — suba o mês corrente todo dia (substitui o mês inteiro).",
                    "mes": "02.05.02 (saldo inicial e final) e financeiro da contabilidade — no fechamento do mês.",
                    "uma": "Relatório de operações — quando entrar operação nova no Promax."}[aba_freq])
        relatorios.cartoes(usuario, operacao_id, "todos", so=NOTAS_FREQ[aba_freq])
    if not algum:
        st.info("Você não tem acesso a nenhuma pasta que use relatórios.")
    st.caption("O Ressuprimento diário traz todas as filiais num arquivo só. As demais bases são da revenda "
               "escolhida no menu ao lado.")


def _robo(operacao_id: int) -> None:
    """🤖 O que o robô de relatórios baixou e importou (ele roda no computador da empresa)."""
    import pandas as pd

    from core import ui
    from services import robo_service as rs

    from services import robo_nuvem as rn

    sit = rs.situacao(operacao_id)
    if sit.empty and not rn.configurado():
        return
    tema.secao("🤖 Robô de relatórios", "Baixa os relatórios dos sites e importa sozinho. Última execução de cada um:")
    c1, c2 = st.columns([1, 2.4])
    if c1.button("☁️ Buscar agora o que o robô enviou", key="robo_buscar"):
        with st.spinner("Importando os arquivos do robô…"):
            res = rn.processar()
        for linha in res or ["Nada novo: o robô não enviou arquivo desde a última busca."]:
            (st.error if linha.startswith("❌") else st.success if linha.startswith("✅") else st.info)(linha)
        sit = rs.situacao(operacao_id)
    ult = rn.ultimo_resultado()
    c2.caption("O sistema também busca sozinho a cada 10 minutos enquanto estiver aberto."
               + (f" Última busca: {ult[0]}." if ult else ""))
    if sit.empty:
        return
    icone = {"ok": "🟢", "erro": "🔴", "rodando": "🔄"}

    def quando(v):
        try:
            return pd.to_datetime(v).strftime("%d/%m %H:%M")
        except Exception:  # noqa: BLE001
            return "—"
    cards = []
    for r in sit.itertuples():
        cards.append({"titulo": rs.NOMES.get(r.relatorio, r.relatorio), "valor": f"{icone.get(r.status, '⚪')} "
                      f"{quando(r.fim or r.inicio)}", "icone": "🤖",
                      "status": "bom" if r.status == "ok" else "critico" if r.status == "erro" else "info",
                      "detalhe": str(r.mensagem or "")[:90]})
    tema.kpis(cards, key="kp_robo")
    with st.expander("Histórico do robô"):
        h = rs.ultimas(operacao_id, 100)
        ui.tabela(pd.DataFrame({"Início": h["inicio"].map(quando), "Fim": h["fim"].map(quando),
                                "Relatório": h["relatorio"].map(lambda x: rs.NOMES.get(x, x)),
                                "Situação": h["status"].map(lambda x: f"{icone.get(x, '⚪')} {x}"),
                                "Resultado": h["mensagem"].fillna(""), "Arquivo": h["arquivo"].fillna(""),
                                "Computador": h["maquina"].fillna("")}), baixar="robo_historico")

