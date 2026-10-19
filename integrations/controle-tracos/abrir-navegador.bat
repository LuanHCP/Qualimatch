@echo off
rem Espera o servidor local (porta 3000) comecar a responder antes de abrir
rem o navegador, em vez de abrir depois de um tempo fixo - o site pode
rem demorar bem mais que alguns segundos para iniciar na primeira vez, ou
rem quando ha dependencias novas para o npm instalar. So usa comandos
rem nativos do Windows (sem PowerShell), para nao ser barrado por
rem antivirus/politicas de seguranca corporativas. Espera no maximo 3
rem minutos.
setlocal EnableExtensions
set /a tries=0

:loop
netstat -ano | findstr /r /c:":3000 .*LISTENING" >nul 2>nul
if not errorlevel 1 goto :abrir

set /a tries+=1
if %tries% GEQ 180 exit /b 1
timeout /t 1 >nul
goto :loop

:abrir
start "" http://localhost:3000
exit /b 0
