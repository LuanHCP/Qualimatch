@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Sistema ainda nao foi instalado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "backend\backup_database.py"
if errorlevel 1 (
  echo Falha ao gerar o backup.
  pause
  exit /b 1
)
echo.
echo O arquivo foi salvo na pasta backups.
pause
