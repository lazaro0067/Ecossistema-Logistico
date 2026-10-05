"""App Carreteiro publicado como um app separado (link próprio para os motoristas).

No Streamlit Cloud: Create app → mesmo repositório → Main file path: app_carreteiro.py
Copie os mesmos Secrets do sistema principal (DATABASE_URL é obrigatório, para os dois
apps usarem o mesmo banco). Os motoristas das três operações usam este mesmo link;
cada um entra com o próprio CPF/celular e vê só as placas e viagens da sua operação.
"""
import os
import runpy

os.environ["ECO_MODO"] = "carreteiro"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"), run_name="__main__")
