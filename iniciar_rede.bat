@echo off
chcp 65001 >nul
cd /d "%~dp0"
set HOST=0.0.0.0
call iniciar.bat
