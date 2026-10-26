@echo off
REM Gera robo_servidor.zip (so o robo: robo.py, receitas e config, SEM senhas, logs nem login salvo)
REM para levar ao servidor Linux da empresa. Depois: scp robo_servidor.zip instalar_robo_linux.sh USUARIO@IP:/tmp/
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t = Join-Path $env:TEMP 'eco_robo_pkg'; if (Test-Path $t) { Remove-Item $t -Recurse -Force }; New-Item -ItemType Directory -Path (Join-Path $t 'robo\receitas') -Force | Out-Null; Copy-Item 'robo.py','config.exemplo.toml','LEIA-ME.md','__init__.py' -Destination (Join-Path $t 'robo'); if (Test-Path 'config.toml') { Copy-Item 'config.toml' (Join-Path $t 'robo') }; Get-ChildItem 'receitas' -Filter *.py | Where-Object { $_.Name -notlike '_gravado*' -and $_.Name -notmatch '_v[0-9]+\.py$' } | Copy-Item -Destination (Join-Path $t 'robo\receitas'); $z = Join-Path (Get-Location) 'servidor\robo_servidor.zip'; if (Test-Path $z) { Remove-Item $z -Force }; Compress-Archive -Path (Join-Path $t 'robo') -DestinationPath $z; Remove-Item $t -Recurse -Force; Write-Host ('Gerado: ' + $z)"
echo.
echo Agora copie para o servidor (troque USUARIO e IP):
echo   scp "%~dp0robo_servidor.zip" "%~dp0instalar_robo_linux.sh" USUARIO@IP:/tmp/
pause
