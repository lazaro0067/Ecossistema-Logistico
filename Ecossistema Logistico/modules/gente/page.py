"""Módulo Gente & Gestão — SSMA, absenteísmo e turnover."""
from core import session, ui
from modules.componentes.registro_generico import Campo, Indicador, tela_registros

CAMPOS = [
    Campo("data", "Data", "data"),
    Campo("dds_tema", "Tema do DDS", obrigatorio=True),
    Campo("incidentes_qtd", "Incidentes", "inteiro"),
    Campo("absenteismo_percent", "Absenteísmo (%)", "percentual"),
    Campo("turnover_percent", "Turnover (%)", "percentual"),
]

INDICADORES = [
    Indicador("DDS realizados", len),
    Indicador("Incidentes", lambda d: d["incidentes_qtd"].sum()),
    Indicador("Absenteísmo médio", lambda d: d["absenteismo_percent"].mean(), ui.pct),
    Indicador("Turnover médio", lambda d: d["turnover_percent"].mean(), ui.pct),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("👥 Gente & Gestão", session.operacao_nome())
    tela_registros(tabela="gente_ssma", operacao_id=operacao_id, campos=CAMPOS,
                   titulo_form="Lançar registro", indicadores=INDICADORES)
