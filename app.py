"""Ponto de entrada do Streamlit Cloud (raiz do repositório) — não precisa mexer aqui.

O sistema completo vem no arquivo  sistema.zip  (na raiz do repositório). Para atualizar,
basta subir um sistema.zip novo pelo GitHub (Add file → Upload files): um arquivo só, sem
risco de as subpastas se perderem no upload.

Se não houver sistema.zip, o sistema é lido da pasta "Ecossistema Logistico" (modo antigo).
"""
import hashlib
import os
import runpy
import sys
import tempfile
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(RAIZ, "sistema.zip")
PASTA_ANTIGA = os.path.join(RAIZ, "Ecossistema Logistico")


def _abrir_zip() -> str:
    """Extrai o sistema.zip uma vez por versão (pasta temporária com o hash do arquivo)."""
    with open(ZIP, "rb") as f:
        versao = hashlib.md5(f.read()).hexdigest()[:12]
    destino = os.path.join(tempfile.gettempdir(), f"eco_sistema_{versao}")
    if not os.path.exists(os.path.join(destino, "app.py")):
        temp = f"{destino}_{os.getpid()}"
        with zipfile.ZipFile(ZIP) as z:
            z.extractall(temp)
        # aceita zip com os arquivos na raiz ou dentro de uma pasta
        if not os.path.exists(os.path.join(temp, "app.py")):
            internas = [d for d in os.listdir(temp) if os.path.exists(os.path.join(temp, d, "app.py"))]
            if internas:
                temp = os.path.join(temp, internas[0])
        try:
            os.replace(temp, destino)
        except OSError:  # outra sessão extraiu ao mesmo tempo
            pass
    return destino


if os.path.exists(ZIP):
    PASTA = _abrir_zip()
    # o banco local (SQLite) e anexos ficam fora da pasta temporária
    os.environ.setdefault("ECO_DATA_DIR", os.path.join(PASTA_ANTIGA if os.path.isdir(PASTA_ANTIGA) else RAIZ, "data"))
else:
    PASTA = PASTA_ANTIGA

if PASTA not in sys.path:
    sys.path.insert(0, PASTA)
for antigo in (RAIZ, PASTA_ANTIGA):  # evita importar arquivos soltos de uploads antigos
    while antigo != PASTA and antigo in sys.path:
        sys.path.remove(antigo)


def _versao_codigo() -> float:
    maior = 0.0
    for raiz, _, arquivos in os.walk(PASTA):
        for a in arquivos:
            if a.endswith(".py"):
                maior = max(maior, os.path.getmtime(os.path.join(raiz, a)))
    return maior


PACOTES = {"config", "core", "database", "modules", "repositories", "services", "scripts"}

_versao = (PASTA, _versao_codigo())
mudou = getattr(sys, "_eco_versao", None) != _versao
for nome, mod in list(sys.modules.items()):
    if nome.split(".")[0] not in PACOTES:
        continue
    arquivo = getattr(mod, "__file__", None) or ""
    # descarta versões antigas: de outra pasta (deploy anterior) ou de antes da última atualização
    if mudou or not arquivo.startswith(PASTA):
        del sys.modules[nome]
sys._eco_versao = _versao

runpy.run_path(os.path.join(PASTA, "app.py"), run_name="__main__")
