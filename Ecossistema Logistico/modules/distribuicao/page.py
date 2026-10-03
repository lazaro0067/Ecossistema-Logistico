"""Módulo Distribuição — rotas, OTIF e devoluções."""
from core import session, ui
from modules.componentes.registro_generico import Campo, Indicador, tela_registros

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
    Indicador("Rotas", len),
    Indicador("OTIF médio", lambda d: d["otif_percent"].mean(), ui.pct),
    Indicador("Devoluções (cx)", lambda d: d["devolucao_caixas"].sum()),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("🚛 Distribuição", session.operacao_nome())
    tela_registros(tabela="distribuicao_rotas", operacao_id=operacao_id, campos=CAMPOS,
                   titulo_form="Lançar rota", indicadores=INDICADORES)
