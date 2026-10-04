"""Módulo Puxada — cada aba (pasta) vive no seu próprio arquivo."""
from core import ui
from modules.puxada import aprovacoes, cadastros, cotacao, encerramento, obz, painel, pedidos

ABAS = {
    "cotacao": cotacao.render,
    "aprovacoes": aprovacoes.render,
    "painel": painel.render,
    "encerramento": encerramento.render,
    "obz": obz.render,
    "pedidos": pedidos.render,
    "cadastros": cadastros.render,
}


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("puxada")
    ui.abas_modulo(usuario, "puxada", ABAS, usuario, operacao_id)
