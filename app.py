"""Ponto de entrada do Streamlit Cloud.

O sistema fica separado na pasta "Ecossistema Logistico". Este arquivo, na raiz
do repositório, só aponta para ele — não precisa mexer aqui.

Quando algum arquivo do sistema é atualizado no GitHub, os módulos antigos que
ficaram na memória são descartados automaticamente (sem precisar de Reboot).
"""
import os
import runpy
import sys

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ecossistema Logistico")
if PASTA not in sys.path:
    sys.path.insert(0, PASTA)


def _versao_codigo() -> float:
    maior = 0.0
    for raiz, _, arquivos in os.walk(PASTA):
        for a in arquivos:
            if a.endswith(".py"):
                maior = max(maior, os.path.getmtime(os.path.join(raiz, a)))
    return maior


_versao = _versao_codigo()
if getattr(sys, "_eco_versao", None) != _versao:
    for nome, mod in list(sys.modules.items()):
        arquivo = getattr(mod, "__file__", None) or ""
        if arquivo.startswith(PASTA):
            del sys.modules[nome]
    sys._eco_versao = _versao

runpy.run_path(os.path.join(PASTA, "app.py"), run_name="__main__")
