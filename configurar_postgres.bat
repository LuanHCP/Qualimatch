@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [QualiMatch] Preparando ambiente para PostgreSQL...

if not exist ".venv\Scripts\python.exe" (
  call iniciar_preparar.bat
  if errorlevel 1 goto :erro
)

".venv\Scripts\python.exe" -c "import psycopg, dotenv" >nul 2>nul
if errorlevel 1 (
  echo [QualiMatch] Dependencias PostgreSQL ausentes. Instalando...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :erro
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :erro
  echo ok>".venv\.deps_ok"
)

".venv\Scripts\python.exe" -c "import psycopg; print('[QualiMatch] psycopg OK - versao', psycopg.__version__)"
if errorlevel 1 goto :erro

echo.
".venv\Scripts\python.exe" tools\configurar_postgres.py
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo A configuracao nao foi concluida. Leia a mensagem acima.
)
pause
exit /b %ERR%

:erro
echo.
echo Falha ao preparar as dependencias do PostgreSQL.
echo Tente executar instalar.bat ou verifique sua conexao com a internet.
pause
exit /b 1
