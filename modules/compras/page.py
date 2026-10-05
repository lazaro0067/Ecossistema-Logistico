"""Módulo Compras — pedidos de compra."""
from core import ui
from modules.componentes.registro_generico import Campo, Grafico, Indicador, tela_registros

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
    Indicador("Pedidos", len, icone="🧾"),
    Indicador("Valor total", lambda d: d["valor_total"].sum(), ui.moeda, "💸"),
    Indicador("Pendentes", lambda d: (d["status"] == "Pendente").sum(), icone="⏳",
              status=lambda v: "bom" if v == 0 else "atencao"),
]

GRAFICOS = [
    Grafico("Valor por fornecedor (R$)", "fornecedor", "valor_total"),
    Grafico("Valor por status (R$)", "status", "valor_total"),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("compras")
    campos = CAMPOS + [ui_campo_solicitante(usuario)]
    tela_registros(modulo="compras", usuario=usuario, tabela="compras_pedidos", operacao_id=operacao_id,
                   campos=campos, indicadores=INDICADORES, graficos_=GRAFICOS, calculados=_calcular)


def ui_campo_solicitante(usuario):
    return Campo("solicitante", "Solicitante", padrao=usuario["nome"])
