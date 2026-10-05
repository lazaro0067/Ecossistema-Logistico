"""Módulo Distribuição (Entrega) — Book DPO de entrega, rotas, OTIF e devoluções."""
import streamlit as st

from config import dpo
from core import ui
from modules.componentes import padrao_dpo
from repositories import operacoes_repo
from modules.componentes.registro_generico import Campo, Grafico, Indicador, tela_registros

CAMPOS = [
    Campo("data", "Data", "data"),
    Campo("rota", "Rota", obrigatorio=True),
    Campo("motorista", "Motorista", obrigatorio=True),
    Campo("placa", "Placa"),
    Campo("otif_percent", "OTIF (%)", "percentual"),
    Campo("devolucao_caixas", "Devolução (caixas)", "inteiro"),
    Campo("status", "Status", "opcao", ["Concluída", "Em rota", "Cancelada"]),
]

INDICADORES = [
    Indicador("Rotas", len, icone="🛣️"),
    Indicador("OTIF médio", lambda d: d["otif_percent"].mean(), ui.pct, "🎯",
              lambda v: "bom" if v >= 95 else "atencao" if v >= 90 else "serio" if v >= 80 else "critico"),
    Indicador("Devoluções (cx)", lambda d: d["devolucao_caixas"].sum(), icone="↩️",
              status=lambda v: "bom" if v == 0 else "atencao"),
]

GRAFICOS = [
    Grafico("OTIF médio por motorista (%)", "motorista", "otif_percent", "mean", sufixo="%"),
    Grafico("Devoluções por rota (cx)", "rota", "devolucao_caixas"),
]


def _book(usuario: dict, operacao_id: int) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        st.info("O Book DPO é por filial. Escolha uma filial no menu.")
        return
    padrao_dpo.progresso_book(operacao_id, "Entrega", dpo.ENTREGA)
    blocos = {"📘 Fundamentos": "fundamentos", "🔄 Gerenciar para Manter": "manter",
              "🚀 Gerenciar para Melhorar": "melhorar"}
    chave = blocos[st.radio("Bloco", list(blocos), horizontal=True, key="ent_bloco")]
    padrao_dpo.book(operacao_id, usuario, "Entrega", dpo.ENTREGA[chave], f"ent_{chave}")


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("distribuicao")
    tela_registros(modulo="distribuicao", usuario=usuario, tabela="distribuicao_rotas", operacao_id=operacao_id,
                   campos=CAMPOS, indicadores=INDICADORES, graficos_=GRAFICOS,
                   extras={"book": lambda: _book(usuario, operacao_id)})
