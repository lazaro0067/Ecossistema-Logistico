@echo off
REM Mostra as tarefas do robo no Agendador do Windows (ultima vez que rodou, resultado, proxima vez)
REM e salva em logs\agendamento.txt.
cd /d "%~dp0"
if not exist logs mkdir logs
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r = Get-ScheduledTask -TaskName 'EcoRobo_*' -ErrorAction SilentlyContinue; if (-not $r) { 'NENHUMA tarefa EcoRobo agendada - rode agendar_robo.bat 07:00 e agendar_robo.bat 09:00' } else { $r | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; [pscustomobject]@{Tarefa=$_.TaskName; Estado=$_.State; Executa=$_.Actions.Execute; UltimaVez=$i.LastRunTime; Resultado=$i.LastTaskResult; ProximaVez=$i.NextRunTime; Bateria=(-not $_.Settings.DisallowStartIfOnBatteries); AtrasadaRodaDepois=$_.Settings.StartWhenAvailable; Usuario=$_.Principal.UserId} } | Format-List }; 'Agora: ' + (Get-Date)" > "logs\agendamento.txt" 2>&1
type "logs\agendamento.txt"
pause
