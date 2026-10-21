@echo off
REM Agenda o robo todo dia no horario informado. Rode uma vez por horario:
REM    agendar_robo.bat 07:00     e depois     agendar_robo.bat 09:00
REM Roda com o seu usuario do Windows logado (as senhas ficam no cofre do seu usuario).
REM Funciona na bateria, acorda o PC da suspensao e, se o PC estava desligado no horario, roda assim que ligar.
set HORA=%1
if "%HORA%"=="" set HORA=07:00
set NOME=EcoRobo_%HORA::=h%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a = New-ScheduledTaskAction -Execute '%~dp0robo_agendado.bat' -WorkingDirectory '%~dp0'; $t = New-ScheduledTaskTrigger -Daily -At '%HORA%'; $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 1); Register-ScheduledTask -TaskName '%NOME%' -Action $a -Trigger $t -Settings $s -Force | Out-Null; Get-ScheduledTask -TaskName '%NOME%' | Format-List TaskName, State"
echo.
echo Agendado: tarefa %NOME% todo dia as %HORA%.
echo Para conferir: ver_agendamento.bat   ^|   Para testar agora: schtasks /Run /TN %NOME%
pause
