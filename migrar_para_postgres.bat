@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [QualiMatch] Verificando ambiente de migracao...
if not exist ".venv\Scripts\python.exe" (
  call iniciar_preparar.bat
  if errorlevel 1 goto :erro
)

".venv\Scripts\python.exe" -c "import psycopg, dotenv" >nul 2>nul
if errorlevel 1 (
  echo [QualiMatch] Dependencias ausentes. Instalando...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :erro
  echo ok>".venv\.deps_ok"
)

".venv\Scripts\python.exe" tools\migrar_para_postgres.py
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" echo A migracao nao foi concluida. Leia a mensagem acima antes de tentar novamente.
pause
exit /b %ERR%

:erro
echo.
echo Falha ao preparar o ambiente para a migracao.
pause
exit /b 1
