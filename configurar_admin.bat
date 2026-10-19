@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [QualiMatch] Preparando autenticacao...
if not exist ".venv\Scripts\python.exe" (
  call iniciar_preparar.bat
  if errorlevel 1 goto :erro
)

".venv\Scripts\python.exe" -c "import argon2, dotenv" >nul 2>nul
if errorlevel 1 (
  echo [QualiMatch] Instalando dependencias de seguranca...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :erro
)

".venv\Scripts\python.exe" tools\configurar_admin.py
set ERR=%ERRORLEVEL%
echo.
pause
exit /b %ERR%

:erro
echo Falha ao preparar o ambiente. Execute instalar.bat e tente novamente.
pause
exit /b 1
