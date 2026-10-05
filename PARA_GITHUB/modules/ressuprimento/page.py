"""Módulo Ressuprimento — cada aba (pasta) vive no seu próprio arquivo."""
from core import ui
from modules.ressuprimento import bases, cestas, diario, estoque, metas, politica, sugestao

ABAS = {
    "bases": bases.render,
    "estoque": estoque.render,
    "sugestao": sugestao.render,
    "cestas": cestas.render,
    "diario": diario.render,
    "politica": politica.render,
    "metas": metas.render,
}


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("ressuprimento")
    ui.abas_modulo(usuario, "ressuprimento", ABAS, usuario, operacao_id)
