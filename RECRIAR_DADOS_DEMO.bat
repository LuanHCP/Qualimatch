@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INICIAR_V2_DEMO.bat pelo menos uma vez antes de recriar a base.
  pause
  exit /b 1
)
set "QUALIMATCH_DEMO=true"
".venv\Scripts\python.exe" tools\seed_demo.py --reset
if errorlevel 1 (
  echo Falha ao recriar os dados ficticios.
) else (
  echo Base ficticia recriada com sucesso.
)
pause
endlocal
