@echo off
REM Agenda o robo todo dia no horario informado (padrao 06:30). Ex.: agendar_robo.bat 06:30
REM Roda com o seu usuario do Windows logado (as senhas ficam no cofre do seu usuario).
set HORA=%1
if "%HORA%"=="" set HORA=06:30
schtasks /Create /TN "EcoRobo" /TR "\"%~dp0robo.bat\"" /SC DAILY /ST %HORA% /F
echo Agendado para %HORA%. Para ver: Agendador de Tarefas, tarefa EcoRobo.
pause
