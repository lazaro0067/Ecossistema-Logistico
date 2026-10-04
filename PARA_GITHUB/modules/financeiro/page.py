"""Módulo Financeiro — OBZ por pacote (orçado x realizado)."""
from core import graficos, ui
from modules.componentes.registro_generico import Campo, Indicador, tela_registros

PACOTES = ["Frete Puxada", "Frete Distribuição", "Manutenção Frota", "Combustível",
           "Pessoal", "Armazém", "Utilidades", "TI", "Outros"]

CAMPOS = [
    Campo("mes_ano", "Mês (AAAA-MM)", obrigatorio=True),
    Campo("pacote", "Pacote", "opcao", PACOTES),
    Campo("orcado", "Orçado (R$)", "numero"),
    Campo("realizado", "Realizado (R$)", "numero"),
]


def _calcular(df):
    df = df.copy()
    df["desvio"] = df["realizado"] - df["orcado"]
    df["desvio_%"] = (df["desvio"] / df["orcado"].where(df["orcado"] > 0) * 100).round(1)
    return df


def _grafico(df):
    por_pacote = df.groupby("pacote", as_index=False)[["realizado", "orcado"]].sum()
    graficos.mostrar(graficos.real_x_meta(por_pacote, "pacote", "realizado", "orcado",
                                          "Realizado x orçado por pacote (R$)", "R$", invertido=True), key="g_fin")


def _status_desvio(v):
    return "bom" if v <= 0 else "atencao" if v < 5000 else "critico"


INDICADORES = [
    Indicador("Orçado", lambda d: d["orcado"].sum(), ui.moeda, "📒"),
    Indicador("Realizado", lambda d: d["realizado"].sum(), ui.moeda, "💸"),
    Indicador("Desvio (real − orçado)", lambda d: d["realizado"].sum() - d["orcado"].sum(), ui.moeda, "⚖️",
              _status_desvio),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("financeiro")
    CAMPOS[0].padrao = ui.mes_atual()
    tela_registros(modulo="financeiro", usuario=usuario, tabela="financeiro_obz", operacao_id=operacao_id,
                   campos=CAMPOS, coluna_data="mes_ano", indicadores=INDICADORES, calculados=_calcular,
                   grafico_extra=_grafico)
