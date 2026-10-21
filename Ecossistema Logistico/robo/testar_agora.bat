@echo off
REM Teste: cria as tarefas 07:00 e 09:00 e dispara agora pelo Agendador do Windows (igual ao horario).
cd /d "%~dp0"
if not exist logs mkdir logs
for %%H in (07:00 09:00) do call :agendar %%H
echo.
echo Disparando agora a tarefa EcoRobo_09h00 pelo Agendador...
schtasks /Run /TN EcoRobo_09h00
echo Aguarde: o robo roda sozinho (Edge abre escondido). Acompanhe em logs\agendador.log
timeout /t 20 >nul
call "%~dp0ver_agendamento.bat" < nul
exit /b

:agendar
set HORA=%1
set NOME=EcoRobo_%HORA::=h%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a = New-ScheduledTaskAction -Execute '%~dp0robo_agendado.bat' -WorkingDirectory '%~dp0'; $t = New-ScheduledTaskTrigger -Daily -At '%HORA%'; $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 1); Register-ScheduledTask -TaskName '%NOME%' -Action $a -Trigger $t -Settings $s -Force | Out-Null; 'Agendado: %NOME%'"
exit /b
