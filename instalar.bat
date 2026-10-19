@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo [QualiMatch] Preparando instalacao limpa...
if exist ".venv" (
  rmdir /s /q ".venv" 2>nul
  if exist ".venv" (
    echo.
    echo Nao foi possivel apagar a pasta .venv.
    echo Feche qualquer janela/servidor do QualiMatch e tente novamente.
    pause
    exit /b 1
  )
)
call iniciar.bat
endlocal
