@echo off
REM Instala o robo neste computador (uma vez). Precisa do Python 3.12 instalado (python.org, marque "Add to PATH").
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
if not exist ".venv\Scripts\python.exe" (echo Nao achei o Python. Instale o Python 3.12 e rode de novo. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r "..\requirements.txt" playwright keyring
".venv\Scripts\python.exe" -m playwright install chromium
if not exist "config.toml" copy "config.exemplo.toml" "config.toml" >nul
echo.
echo Pronto. Agora:
echo  1. Abra o config.toml e preencha os enderecos, usuarios e a pasta.
echo  2. robo.bat --senha promax   (e --senha wms, --senha banco)
echo  3. robo.bat --gravar vendas  (um por relatorio)
echo  4. agendar_robo.bat 06:30
pause
