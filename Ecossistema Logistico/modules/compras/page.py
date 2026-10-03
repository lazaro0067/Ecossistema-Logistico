"""Módulo Compras — pedidos de compra."""
from core import session, ui
from modules.componentes.registro_generico import Campo, Indicador, tela_registros

CAMPOS = [
    Campo("data", "Data", "data"),
    Campo("item", "Item", obrigatorio=True),
    Campo("quantidade", "Quantidade", "numero"),
    Campo("valor_unitario", "Valor unitário (R$)", "numero"),
    Campo("fornecedor", "Fornecedor"),
    Campo("status", "Status", "opcao", ["Pendente", "Aprovado", "Comprado", "Recebido", "Cancelado"]),
]


def _calcular(df):
    return df.assign(valor_total=df["quantidade"] * df["valor_unitario"])


INDICADORES = [
    Indicador("Pedidos", len),
    Indicador("Valor total", lambda d: d["valor_total"].sum(), ui.moeda),
    Indicador("Pendentes", lambda d: (d["status"] == "Pendente").sum()),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("🛒 Compras", session.operacao_nome())
    campos = CAMPOS + [Campo("solicitante", "Solicitante", padrao=usuario["nome"])]
    tela_registros(tabela="compras_pedidos", operacao_id=operacao_id, campos=campos,
                   titulo_form="Novo pedido", indicadores=INDICADORES, calculados=_calcular)
