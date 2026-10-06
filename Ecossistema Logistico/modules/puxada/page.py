"""Módulo Puxada — cada aba (pasta) vive no seu próprio arquivo."""
from core import ui
from modules.puxada import (aprovacoes, cadastros, carreteiro, cotacao, descarga, disp_motoristas, disponibilidade,
                            encerramento, obz,
                            painel, pedidos, pedidos_dia, remuneracao, tmv_tma, viagens, vinculos)

ABAS = {
    "cotacao": cotacao.render,
    "aprovacoes": aprovacoes.render,
    "encerramento": encerramento.render,
    "painel": painel.render,
    "obz": obz.render,
    "descarga": descarga.render,
    "vinculos": vinculos.render,
    "viagens": viagens.render,
    "pedidos": pedidos.render,
    "cadastros": cadastros.render,
    "carreteiro": carreteiro.render,
    "tmv_tma": tmv_tma.render,
    "remuneracao": remuneracao.render,
    "disponibilidade": disponibilidade.render,
    "pedidos_dia": pedidos_dia.render,
    "disp_motoristas": disp_motoristas.render,
}


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("puxada")
    from modules.componentes.bases import barra_atualizar

    barra_atualizar("puxada", operacao_id, usuario)
    ui.abas_modulo(usuario, "puxada", ABAS, usuario, operacao_id)
