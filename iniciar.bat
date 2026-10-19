@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem QualiMatch v3.8.17 - bootstrap Python Install Manager/CPython robusto.
rem Corrige deteccao quando 'py install 3.12' instala o runtime em
rem %%LocalAppData%%\Python\pythoncore-3.12-64, mas o alias python/py nao
rem consegue ser validado imediatamente no mesmo terminal.
set "VIRTUAL_ENV="
set "PYTHONHOME="
set "PYTHONPATH="
set "PY_CMD="
set "PY_LABEL="

rem Um ambiente local funcional deve ser suficiente para iniciar, mesmo quando
rem o Python global foi removido do PATH depois da instalacao.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    set "PY_LABEL=ambiente local existente"
    goto :dependencies
  )
)

call :find_python
if defined PY_CMD goto :python_ok

rem Python Install Manager existe, mas o runtime pode ainda nao existir.
where py >nul 2>nul
if not errorlevel 1 (
  echo.
  echo [QualiMatch] Python Launcher/Install Manager encontrado.
  echo [QualiMatch] Garantindo instalacao do Python 3.12...
  py install 3.12
  echo [QualiMatch] Procurando o runtime 3.12 instalado...
  call :find_python
  if defined PY_CMD goto :python_ok
)

goto :python_missing

:find_python
rem 1) NOVO Python Install Manager: usa primeiro o executavel REAL do runtime.
rem Ele normalmente fica em AppData\Local\Python\pythoncore-3.12-64\python.exe.
call :tryexe "%LocalAppData%\Python\pythoncore-3.12-64\python.exe" "Python Manager 3.12 (runtime direto)"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Python\pythoncore-3.12\python.exe" "Python Manager 3.12 (runtime direto)"
if defined PY_CMD exit /b 0
for /d %%D in ("%LocalAppData%\Python\pythoncore-3.12*") do (
  if not defined PY_CMD call :tryexe "%%~fD\python.exe" "Python Manager 3.12 (runtime direto)"
)
if defined PY_CMD exit /b 0

call :tryexe "%LocalAppData%\Python\pythoncore-3.11-64\python.exe" "Python Manager 3.11 (runtime direto)"
if defined PY_CMD exit /b 0
for /d %%D in ("%LocalAppData%\Python\pythoncore-3.11*") do (
  if not defined PY_CMD call :tryexe "%%~fD\python.exe" "Python Manager 3.11 (runtime direto)"
)
if defined PY_CMD exit /b 0

call :tryexe "%LocalAppData%\Python\pythoncore-3.13-64\python.exe" "Python Manager 3.13 (runtime direto)"
if defined PY_CMD exit /b 0
for /d %%D in ("%LocalAppData%\Python\pythoncore-3.13*") do (
  if not defined PY_CMD call :tryexe "%%~fD\python.exe" "Python Manager 3.13 (runtime direto)"
)
if defined PY_CMD exit /b 0

rem 2) Aliases versionados do novo manager. O usuario pode ter python3.12.exe
rem mesmo quando o alias generico python.exe nao esta configurado.
call :tryexe "%LocalAppData%\Python\bin\python3.12.exe" "Python Manager 3.12 (alias versionado)"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Python\bin\python3.11.exe" "Python Manager 3.11 (alias versionado)"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Python\bin\python3.13.exe" "Python Manager 3.13 (alias versionado)"
if defined PY_CMD exit /b 0

rem 3) Launcher: suporta sintaxe curta e -V:TAG.
call :trylauncher_short "3.12" "Python Launcher 3.12"
if defined PY_CMD exit /b 0
call :trylauncher_v "3.12" "Python Launcher -V:3.12"
if defined PY_CMD exit /b 0
call :trylauncher_short "3.11" "Python Launcher 3.11"
if defined PY_CMD exit /b 0
call :trylauncher_v "3.11" "Python Launcher -V:3.11"
if defined PY_CMD exit /b 0
call :trylauncher_short "3.13" "Python Launcher 3.13"
if defined PY_CMD exit /b 0
call :trylauncher_v "3.13" "Python Launcher -V:3.13"
if defined PY_CMD exit /b 0

rem 4) Instaladores classicos do python.org.
call :tryexe "%LocalAppData%\Programs\Python\Python312\python.exe" "Python 3.12 local"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Programs\Python\Python311\python.exe" "Python 3.11 local"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Programs\Python\Python313\python.exe" "Python 3.13 local"
if defined PY_CMD exit /b 0
call :tryexe "%ProgramFiles%\Python312\python.exe" "Python 3.12"
if defined PY_CMD exit /b 0
call :tryexe "%ProgramFiles%\Python311\python.exe" "Python 3.11"
if defined PY_CMD exit /b 0
call :tryexe "%ProgramFiles%\Python313\python.exe" "Python 3.13"
if defined PY_CMD exit /b 0

rem 5) PATH: procura primeiro aliases versionados, depois genericos.
for %%N in (python3.12.exe python3.11.exe python3.13.exe python.exe) do (
  for /f "delims=" %%P in ('where %%N 2^>nul') do (
    echo %%P | findstr /i /c:"\.venv\Scripts\python.exe" /c:"\venv\Scripts\python.exe" >nul
    if errorlevel 1 if not defined PY_CMD call :tryexe "%%P" "Python do PATH"
  )
)
exit /b 0

:trylauncher_short
set "_QM_VER=%~1"
set "_QM_PROBE=%TEMP%\qualimatch_py_probe_%RANDOM%_%RANDOM%.txt"
py -%_QM_VER% -c "import sys,venv; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13),(3,14),(3,15)); print('QUALIMATCH_BASE_OK' if ok else 'QUALIMATCH_BASE_BAD'); sys.exit(0 if ok else 3)" >"%_QM_PROBE%" 2>&1
findstr /x /c:"QUALIMATCH_BASE_OK" "%_QM_PROBE%" >nul 2>&1
if not errorlevel 1 (
  set "PY_CMD=py -%_QM_VER%"
  set "PY_LABEL=%~2"
)
del /q "%_QM_PROBE%" >nul 2>&1
exit /b 0

:trylauncher_v
set "_QM_VER=%~1"
set "_QM_PROBE=%TEMP%\qualimatch_py_probe_%RANDOM%_%RANDOM%.txt"
py -V:%_QM_VER% -c "import sys,venv; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13),(3,14),(3,15)); print('QUALIMATCH_BASE_OK' if ok else 'QUALIMATCH_BASE_BAD'); sys.exit(0 if ok else 3)" >"%_QM_PROBE%" 2>&1
findstr /x /c:"QUALIMATCH_BASE_OK" "%_QM_PROBE%" >nul 2>&1
if not errorlevel 1 (
  set "PY_CMD=py -V:%_QM_VER%"
  set "PY_LABEL=%~2"
)
del /q "%_QM_PROBE%" >nul 2>&1
exit /b 0

:tryexe
if not exist "%~1" exit /b 0
set "_QM_PROBE=%TEMP%\qualimatch_py_probe_%RANDOM%_%RANDOM%.txt"
"%~1" -c "import sys,venv; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13),(3,14),(3,15)); print('QUALIMATCH_BASE_OK' if ok else 'QUALIMATCH_BASE_BAD'); sys.exit(0 if ok else 3)" >"%_QM_PROBE%" 2>&1
findstr /x /c:"QUALIMATCH_BASE_OK" "%_QM_PROBE%" >nul 2>&1
if not errorlevel 1 (
  set PY_CMD="%~1"
  set "PY_LABEL=%~2"
)
del /q "%_QM_PROBE%" >nul 2>&1
exit /b 0

:python_missing
echo.
echo ================================================================
echo Python 3.11+ funcional nao foi localizado pelo instalador.
echo.
echo O Python Install Manager pode ter instalado o runtime, mas os aliases
echo do Windows ainda nao foram atualizados. Esta versao procura tambem o
echo executavel real em:
echo   %%LocalAppData%%\Python\pythoncore-3.12-64\python.exe
echo.
echo Diagnostico:
where py 2>nul
where python 2>nul
where python3.12 2>nul
if exist "%LocalAppData%\Python" dir /b "%LocalAppData%\Python" 2>nul
echo.
echo Se ainda falhar, execute e envie a saida destes dois comandos:
echo   py -3.12 --version
echo   "%LocalAppData%\Python\pythoncore-3.12-64\python.exe" --version
echo ================================================================
pause
exit /b 1

:python_ok
echo [QualiMatch] Python base validado: %PY_LABEL%

rem Remove SOMENTE o .venv local se estiver quebrado/incompleto.
if exist ".venv" if not exist ".venv\pyvenv.cfg" (
  echo [QualiMatch] Ambiente virtual incompleto detectado. Recriando...
  rmdir /s /q ".venv" 2>nul
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if errorlevel 1 (
    echo [QualiMatch] Ambiente virtual invalido detectado. Recriando...
    rmdir /s /q ".venv" 2>nul
  )
)
if exist ".venv" if not exist ".venv\Scripts\python.exe" rmdir /s /q ".venv" 2>nul
if exist ".venv" if not exist ".venv\pyvenv.cfg" (
  echo [QualiMatch] Nao foi possivel remover o .venv antigo.
  echo Feche outros terminais/servidores do QualiMatch e tente novamente.
  goto :erro
)

if not exist ".venv\Scripts\python.exe" (
  echo [QualiMatch] Criando ambiente virtual novo...
  call %PY_CMD% -m venv ".venv"
  if errorlevel 1 goto :erro_python
)
if not exist ".venv\pyvenv.cfg" goto :erro_python
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 goto :erro_python

:dependencies
rem Valida todas as dependencias usadas na inicializacao e nas ferramentas.
rem Testar apenas parte delas pode deixar um .venv antigo parecer completo.
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, pydantic, multipart, pypdf, reportlab, openpyxl, argon2, dotenv, psycopg, psycopg_pool, email_validator" >nul 2>nul
if errorlevel 1 (
  echo [QualiMatch] Instalando dependencias...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :erro
  if exist "requirements.lock" (
    ".venv\Scripts\python.exe" -m pip install -r requirements.lock
  ) else (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  )
  if errorlevel 1 goto :erro
  echo ok>".venv\.deps_ok"
)

rem Nao inicia parcialmente caso o arquivo lock esteja desatualizado.
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, pydantic, multipart, pypdf, reportlab, openpyxl, argon2, dotenv, psycopg, psycopg_pool, email_validator" >nul 2>nul
if errorlevel 1 (
  echo [QualiMatch] A instalacao terminou, mas ainda existem dependencias ausentes.
  echo [QualiMatch] Atualize a pasta pelo GitHub e execute novamente.
  goto :erro
)

echo [QualiMatch] Iniciando servidor local...
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto :erro_runtime
goto :fim

:erro_python
echo.
echo ================================================================
echo Nao foi possivel criar o ambiente virtual Python.
echo Python detectado: %PY_LABEL%
echo Comando usado: %PY_CMD%
echo ================================================================
pause
exit /b 1

:erro_runtime
echo.
echo ================================================
echo O servidor encerrou com erro.
echo A mensagem acima foi mantida na tela para diagnostico.
echo ================================================
pause
exit /b 1

:erro
echo.
echo Falha ao preparar o QualiMatch.
echo Feche qualquer terminal/servidor antigo e execute instalar.bat novamente.
pause
exit /b 1

:fim
endlocal
