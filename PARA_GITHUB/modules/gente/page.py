"""Módulo Gente & Gestão — SSMA, absenteísmo e turnover."""
from core import ui
from modules.componentes.registro_generico import Campo, Grafico, Indicador, tela_registros

CAMPOS = [
    Campo("data", "Data", "data"),
    Campo("dds_tema", "Tema do DDS", obrigatorio=True),
    Campo("incidentes_qtd", "Incidentes", "inteiro"),
    Campo("absenteismo_percent", "Absenteísmo (%)", "percentual"),
    Campo("turnover_percent", "Turnover (%)", "percentual"),
]

INDICADORES = [
    Indicador("DDS realizados", len, icone="🗣️"),
    Indicador("Incidentes", lambda d: d["incidentes_qtd"].sum(), icone="🚑",
              status=lambda v: "bom" if v == 0 else "critico"),
    Indicador("Absenteísmo médio", lambda d: d["absenteismo_percent"].mean(), ui.pct, "📅",
              lambda v: "bom" if v <= 3 else "atencao" if v <= 5 else "critico"),
    Indicador("Turnover médio", lambda d: d["turnover_percent"].mean(), ui.pct, "🔁",
              lambda v: "bom" if v <= 2 else "atencao" if v <= 4 else "critico"),
]

GRAFICOS = [Grafico("Incidentes por dia", "data", "incidentes_qtd", horizontal=False)]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("gente")
    tela_registros(modulo="gente", usuario=usuario, tabela="gente_ssma", operacao_id=operacao_id,
                   campos=CAMPOS, indicadores=INDICADORES, graficos_=GRAFICOS)
