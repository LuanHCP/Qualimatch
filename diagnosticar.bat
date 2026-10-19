@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [QualiMatch] Ambiente local ausente. Preparando...
  call iniciar_preparar.bat
  if errorlevel 1 goto :erro
)

".venv\Scripts\python.exe" tools\qualimatch_doctor.py
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%

:erro
echo Nao foi possivel preparar o ambiente para o diagnostico.
pause
exit /b 1
