"""Módulo Segurança & Frota — manutenção de veículos."""
from core import ui
from modules.componentes.registro_generico import Campo, Grafico, Indicador, tela_registros

CAMPOS = [
    Campo("data", "Data", "data"),
    Campo("placa", "Placa", obrigatorio=True),
    Campo("tipo_servico", "Tipo de serviço", "opcao",
          ["Preventiva", "Corretiva", "Pneus", "Elétrica", "Funilaria", "Outros"]),
    Campo("valor", "Valor (R$)", "numero"),
    Campo("km_atual", "KM atual", "inteiro"),
    Campo("status", "Status", "opcao", ["Finalizado", "Em andamento", "Agendado"]),
]

INDICADORES = [
    Indicador("Serviços", len, icone="🔧"),
    Indicador("Custo total", lambda d: d["valor"].sum(), ui.moeda, "💸"),
    Indicador("Veículos atendidos", lambda d: d["placa"].nunique(), icone="🚛"),
    Indicador("Corretivas", lambda d: (d["tipo_servico"] == "Corretiva").sum(), icone="⚠️",
              status=lambda v: "bom" if v == 0 else "atencao" if v < 5 else "critico"),
]

GRAFICOS = [
    Grafico("Custo por placa (R$)", "placa", "valor"),
    Grafico("Custo por tipo de serviço (R$)", "tipo_servico", "valor"),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho_modulo("frota")
    tela_registros(modulo="frota", usuario=usuario, tabela="frota_manutencao", operacao_id=operacao_id,
                   campos=CAMPOS, indicadores=INDICADORES, graficos_=GRAFICOS)
