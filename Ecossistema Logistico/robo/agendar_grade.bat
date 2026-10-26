@echo off
REM Agenda a GRADE CORA a cada 2 horas (todas as revendas do grupo "grade" no config.toml, uma depois da outra).
REM    agendar_grade.bat            -> das 06:00 as 22:00, de 2 em 2 horas
REM    agendar_grade.bat 05:00 18   -> comeca 05:00 e repete por 18 horas
set INICIO=%1
if "%INICIO%"=="" set INICIO=06:00
set HORAS=%2
if "%HORAS%"=="" set HORAS=16
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a = New-ScheduledTaskAction -Execute '%~dp0robo_agendado.bat' -Argument '--grupo grade' -WorkingDirectory '%~dp0'; $t = New-ScheduledTaskTrigger -Daily -At '%INICIO%'; $r = New-ScheduledTaskTrigger -Once -At '%INICIO%' -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Hours %HORAS%); $t.Repetition = $r.Repetition; $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 100); Register-ScheduledTask -TaskName 'EcoRobo_Grade' -Action $a -Trigger $t -Settings $s -Force | Out-Null; Get-ScheduledTask -TaskName 'EcoRobo_Grade' | Format-List TaskName, State"
echo.
echo Agendado: EcoRobo_Grade a partir das %INICIO%, de 2 em 2 horas por %HORAS% horas.
echo Para testar agora: schtasks /Run /TN EcoRobo_Grade
pause
