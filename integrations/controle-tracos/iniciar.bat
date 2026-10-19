@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   Controle de Traco - Iniciando...
echo ================================================
echo.

set "NODE_CMD="
set "NODE_LABEL="

call :find_node
if not defined NODE_CMD goto :node_missing

for /f "usebackq tokens=1" %%v in (`"%NODE_CMD%" -v`) do set "NODE_VERSION=%%v"
echo [Controle de Traco] Node.js detectado (%NODE_LABEL%): %NODE_VERSION%

set "NEED_INSTALL=0"
if not exist "node_modules" set "NEED_INSTALL=1"
if not exist "node_modules\.bin\vinext.cmd" set "NEED_INSTALL=1"
if not exist "node_modules\pdfjs-dist" set "NEED_INSTALL=1"
if not exist "node_modules\pdf-lib" set "NEED_INSTALL=1"
if not exist "node_modules\cross-env" set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="1" (
  echo [Controle de Traco] Instalando/atualizando dependencias...
  echo [Controle de Traco] Isso pode levar alguns minutos.
  call npm install
  if errorlevel 1 goto :erro_install
)

if not exist ".env.local" (
  echo [Controle de Traco] Sem .env.local - rodando em modo local, sem
  echo [Controle de Traco] PostgreSQL. Para ativar o banco, rode criar_banco.bat.
)

echo.
echo [Controle de Traco] O navegador vai abrir quando a interface e a API
echo [Controle de Traco] estiverem respondendo. Na primeira execucao isso
echo [Controle de Traco] pode levar ate 2 minutos. Deixe esta janela aberta
echo [Controle de Traco] enquanto estiver usando o sistema.
echo.
echo [Controle de Traco] Iniciando servidor local (feche esta janela para parar)...
echo.
"%NODE_CMD%" server\start-local.mjs
set "DEV_ERR=%ERRORLEVEL%"

if not "%DEV_ERR%"=="0" (
  echo.
  echo ================================================================
  echo O servidor encerrou com erro. Veja as mensagens acima.
  echo ================================================================
  pause
)
exit /b %DEV_ERR%

:find_node
where node >nul 2>nul
if not errorlevel 1 (
  set "NODE_CMD=node"
  set "NODE_LABEL=PATH"
  exit /b 0
)
if exist "%ProgramFiles%\nodejs\node.exe" (
  set "PATH=%ProgramFiles%\nodejs;%PATH%"
  set "NODE_CMD=node"
  set "NODE_LABEL=%ProgramFiles%\nodejs"
  exit /b 0
)
if exist "%LocalAppData%\Programs\nodejs\node.exe" (
  set "PATH=%LocalAppData%\Programs\nodejs;%PATH%"
  set "NODE_CMD=node"
  set "NODE_LABEL=%LocalAppData%\Programs\nodejs"
  exit /b 0
)
exit /b 1

:node_missing
echo.
echo ================================================================
echo Node.js 22.13 ou superior nao foi encontrado neste computador.
echo Baixe a versao LTS em https://nodejs.org/ , instale e execute
echo este arquivo novamente.
echo ================================================================
pause
exit /b 1

:erro_install
echo.
echo ================================================================
echo Falha ao instalar as dependencias (npm install).
echo Verifique sua conexao com a internet e tente novamente.
echo ================================================================
pause
exit /b 1
