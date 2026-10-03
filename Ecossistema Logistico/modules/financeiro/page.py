"""Módulo Financeiro — OBZ por pacote (orçado x realizado)."""
from core import session, ui
from modules.componentes.registro_generico import Campo, Indicador, tela_registros

PACOTES = ["Frete Puxada", "Frete Distribuição", "Manutenção Frota", "Combustível",
           "Pessoal", "Armazém", "Utilidades", "TI", "Outros"]

CAMPOS = [
    Campo("mes_ano", "Mês (AAAA-MM)", padrao=ui.mes_atual(), obrigatorio=True),
    Campo("pacote", "Pacote", "opcao", PACOTES),
    Campo("orcado", "Orçado (R$)", "numero"),
    Campo("realizado", "Realizado (R$)", "numero"),
]


def _calcular(df):
    df = df.copy()
    df["desvio"] = df["realizado"] - df["orcado"]
    df["desvio_%"] = (df["desvio"] / df["orcado"].where(df["orcado"] > 0) * 100).round(1)
    return df


INDICADORES = [
    Indicador("Orçado", lambda d: d["orcado"].sum(), ui.moeda),
    Indicador("Realizado", lambda d: d["realizado"].sum(), ui.moeda),
    Indicador("Desvio", lambda d: d["realizado"].sum() - d["orcado"].sum(), ui.moeda),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("💰 Financeiro — OBZ", session.operacao_nome())
    tela_registros(tabela="financeiro_obz", operacao_id=operacao_id, campos=CAMPOS,
                   titulo_form="Lançar pacote", coluna_data="mes_ano",
                   indicadores=INDICADORES, calculados=_calcular)
