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
popd

echo.
echo [2/2] Preparando Sistema de Nao Conformidades...
echo O instalador solicitara a senha administrativa do PostgreSQL local.
call "integrations\sistema-nc\INSTALAR_E_INICIAR.bat"
if errorlevel 1 goto :erro

echo Integracoes preparadas.
exit /b 0

:erro
echo Nao foi possivel preparar todas as integracoes.
pause
exit /b 1
