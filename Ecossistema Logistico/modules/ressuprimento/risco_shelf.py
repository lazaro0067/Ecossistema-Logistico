"""Ressuprimento › 🧊 Risco de Shelf — produtos que vão vencer no armazém (não comprar mais)."""
from modules.armazem import idade


def render(usuario: dict, operacao_id: int) -> None:
    idade.render_risco_shelf(usuario, operacao_id)
