"""Módulo Segurança & Frota — manutenção de veículos."""
from core import session, ui
from modules.componentes.registro_generico import Campo, Indicador, tela_registros

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
    Indicador("Serviços", len),
    Indicador("Custo total", lambda d: d["valor"].sum(), ui.moeda),
    Indicador("Veículos atendidos", lambda d: d["placa"].nunique()),
    Indicador("Em andamento", lambda d: (d["status"] == "Em andamento").sum()),
]


def render(usuario: dict, operacao_id: int) -> None:
    ui.cabecalho("🛡️ Segurança & Frota", session.operacao_nome())
    tela_registros(tabela="frota_manutencao", operacao_id=operacao_id, campos=CAMPOS,
                   titulo_form="Lançar manutenção", indicadores=INDICADORES)
