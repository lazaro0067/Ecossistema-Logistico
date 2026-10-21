@echo off
REM Chamado pelo Agendador de Tarefas (nao precisa abrir). Guarda tudo em logs\agendador.log.
cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ==== %date% %time% inicio pelo agendador >> "logs\agendador.log"
".venv\Scripts\python.exe" "%~dp0robo.py" >> "logs\agendador.log" 2>&1
echo ==== %date% %time% fim (codigo %errorlevel%) >> "logs\agendador.log"
