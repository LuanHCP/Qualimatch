@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "QUALIMATCH_DEMO=true"
call iniciar.bat
endlocal
