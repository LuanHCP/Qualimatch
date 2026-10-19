@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] Preparando Controle de Tracos...
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js/npm nao encontrado. Instale Node.js 22 ou superior e execute novamente.
  pause
  exit /b 1
)
pushd "integrations\controle-tracos"
call npm ci
if errorlevel 1 (popd & goto :erro)
call npm run build
if errorlevel 1 (popd & goto :erro)
popd

echo.
echo [2/2] Preparando Sistema de Nao Conformidades...
echo Criando banco demonstrativo isolado para o modulo NC...
set "NC_PY="
if exist ".venv\Scripts\python.exe" set "NC_PY=.venv\Scripts\python.exe"
if not defined NC_PY where py >nul 2>nul && set "NC_PY=py -3"
if not defined NC_PY where python >nul 2>nul && set "NC_PY=python"
if not defined NC_PY (
  echo Python 3 nao encontrado. Inicie primeiro o QualiMatch V2 para instalar o Python.
  goto :erro
)
call %NC_PY% tools\setup_nc_demo.py
if errorlevel 1 goto :erro

echo Integracoes preparadas.
exit /b 0

:erro
echo Nao foi possivel preparar todas as integracoes.
pause
exit /b 1
