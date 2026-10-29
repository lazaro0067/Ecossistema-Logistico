"""Módulo Ressuprimento — cada aba (pasta) vive no seu próprio arquivo."""
from core import ui
from modules.puxada import pedidos_dia
from modules.ressuprimento import (bases, cestas, diario, estoque, gestao_dia, linear, metas, politica, risco_shelf,
                                   ruptura, sellin, sugestao)

ABAS = {
    "estoque": estoque.render,
    "sugestao": sugestao.render,
    "cestas": cestas.render,
    "sellin": sellin.render,
    "gestao_dia": gestao_dia.render,
    "diario": diario.render,
    "politica": politica.render,
    "metas": metas.render,
    "puxada_pedidos": pedidos_dia.tela_ressuprimento,
    "ruptura": ruptura.render,
    "risco_shelf": risco_shelf.render,
    "linear": linear.render,
}


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("ressuprimento")
    from modules.componentes.bases import barra_atualizar

    barra_atualizar("ressuprimento", operacao_id, usuario)
    from modules.componentes import carretas_fases

    carretas_fases.faixa(operacao_id, "ressuprimento")
    ui.abas_modulo(usuario, "ressuprimento", ABAS, usuario, operacao_id)
