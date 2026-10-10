"""Registro de páginas: chave da página -> função render(usuario, operacao_id).

Para criar um módulo novo: crie modules/<nome>/page.py com `render`,
adicione a chave em config.settings.MODULOS e registre aqui.
"""
from modules.admin import page as admin
from modules.armazem import page as armazem
from modules.bases import page as bases
from modules.compras import page as compras
from modules.conta import page as conta
from modules.distribuicao import page as distribuicao
from modules.financeiro import page as financeiro
from modules.frota import page as frota
from modules.gente import page as gente
from modules.inicio import page as inicio
from modules.notificacoes import page as notificacoes
from modules.puxada import page as puxada
from modules.relatorios import page as relatorios
from modules.ressuprimento import page as ressuprimento
from modules.vendas import page as vendas

PAGINAS = {
    "inicio": inicio.render,
    "bases": bases.render,
    "puxada": puxada.render,
    "ressuprimento": ressuprimento.render,
    "armazem": armazem.render,
    "distribuicao": distribuicao.render,
    "frota": frota.render,
    "gente": gente.render,
    "vendas": vendas.render,
    "financeiro": financeiro.render,
    "compras": compras.render,
    "relatorios": relatorios.render,
    "admin": admin.render,
    "conta": conta.render,
    "notificacoes": notificacoes.render,
}
