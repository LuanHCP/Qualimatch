@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo O sistema ainda nao foi instalado. Execute INSTALAR_E_INICIAR.bat primeiro.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Configuracao .env nao encontrada. Execute INSTALAR_E_INICIAR.bat primeiro.
  pause
  exit /b 1
)
start "Sistema NC - Servidor" cmd /k "cd /d ""%~dp0"" && .venv\Scripts\python.exe backend\run_windows.py"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000"
exit /b 0
