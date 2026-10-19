@echo off
REM Atalho: roda o robo com o Python dele.  Ex.: robo.bat --testar vendas
cd /d "%~dp0"
".venv\Scripts\python.exe" "%~dp0robo.py" %*
