"""Ponto de entrada do Streamlit Cloud.

O sistema fica separado na pasta "Ecossistema Logistico". Este arquivo, na raiz
do repositório, só aponta para ele — não precisa mexer aqui.
"""
import os
import runpy
import sys

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ecossistema Logistico")
if PASTA not in sys.path:
    sys.path.insert(0, PASTA)

runpy.run_path(os.path.join(PASTA, "app.py"), run_name="__main__")
