@echo off
REM Agenda o robo todo dia no horario informado. Pode rodar varias vezes, uma por horario.
REM Ex.: agendar_robo.bat 07:00   e depois   agendar_robo.bat 09:00
REM Roda com o seu usuario do Windows logado (as senhas ficam no cofre do seu usuario).
set HORA=%1
if "%HORA%"=="" set HORA=07:00
set NOME=EcoRobo_%HORA::=h%
schtasks /Create /TN "%NOME%" /TR "\"%~dp0robo.bat\"" /SC DAILY /ST %HORA% /F
echo Agendado: tarefa %NOME% todo dia as %HORA%. Para ver ou apagar: Agendador de Tarefas.
pause
