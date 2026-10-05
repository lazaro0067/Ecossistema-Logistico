"""Estrutura do Book DPO (pilares e subblocos), igual ao sistema original.

A chave de cada subbloco é a mesma usada no sistema antigo (para migrar os
padrões já escritos); o rótulo é o que aparece na tela.
"""

ARMAZEM = {
    "fundamentos": {
        "1 - Layout e Capacidade": [
            ("1.1 - Otimização do Layout", "1.1 - Otimização do Layout (plantas)"),
            ("1.2 - Layout Reflete ABC", "1.2 - O Layout Reflete a Curva ABC"),
            ("1.3 - Gestão de Capacidade", "1.3 - Gestão de Capacidade do Armazém"),
        ],
        "2 - Qualidade": [
            ("2.1 - Treinamentos de Qualidade", "2.1 - Treinamentos de Qualidade"),
            ("2.2 - Padrões Globais Qualidade", "2.2 - Padrões Globais de Qualidade"),
            ("2.3 - Gestão de Validade", "2.3 - Gestão de Validade"),
            ("2.4 - Políticas de Bloqueio", "2.4 - Políticas de Bloqueio no Armazém"),
            ("2.5 - Devoluções e Qualidade", "2.5 - Políticas de Devolução e Qualidade"),
        ],
        "3 - Acuracidade": [
            ("3.1 - Pacote Prejuízo", "3.1 - Pacote Prejuízo"),
            ("3.2 - Qualidade no Armazém", "3.2 - Qualidade no Armazém"),
            ("3.3 - Inventário e IRA", "3.3 - Contagem de Inventário e Resultados (IRA)"),
            ("3.4 - Gestão de Ativos", "3.4 - Gestão de Ativos"),
        ],
    },
    "manter": {
        "4 - Gerenciar para Manter": [
            ("4.1 - Política de Descarte", "4.1 - Política de Descarte"),
            ("4.2 - Repack", "4.2 - Repack"),
            ("4.3 - Qualidade da Puxada", "4.3 - Gestão de Qualidade da Puxada"),
        ],
    },
    "melhorar": {
        "5 - Gerenciar para Melhorar": [
            ("5.1 - Eficiência Carga e Descarga", "5.1 - Eficiência de Carga e Descarga"),
            ("5.2 - Processo de Picking", "5.2 - Processo de Picking"),
            ("5.3 - Gestão do WLP", "5.3 - Gestão do WLP"),
            ("5.4 - Ciclo das Carretas", "5.4 - Ciclo das Carretas"),
        ],
    },
}

ENTREGA = {
    "fundamentos": {
        "1 - Processo de Execução da Entrega": [
            ("1.1 - Pré-rota", "1.1 - Pré-rota"),
            ("1.2 - Entrega em Rota", "1.2 - Entrega em Rota"),
            ("1.3 - Pós-rota", "1.3 - Pós-rota"),
            ("1.4 - Jornada", "1.4 - Jornada"),
        ],
        "2 - Qualidade na Entrega": [("2 - Qualidade na Entrega", "2 - Qualidade na Entrega")],
        "3 - Equipes Empoderadas": [("3 - Equipes Empoderadas", "3 - Equipes Empoderadas")],
        "4 - Satisfação do Cliente": [("4 - Satisfação do Cliente", "4 - Satisfação do Cliente")],
    },
    "manter": {"5 - Gerenciar para Manter": [("5.1 - SAC/SAV", "5.1 - SAC / SAV")]},
    "melhorar": {"6 - Gerenciar para Melhorar": [("6.1 - NPS", "6.1 - NPS")]},
}

STATUS_PADRAO = ["Em elaboração", "Implementado", "Auditado"]


def todos_subblocos(book: dict) -> list[tuple[str, str]]:
    return [sb for grupo in book.values() for itens in grupo.values() for sb in itens]
