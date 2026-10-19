@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "VIRTUAL_ENV="
set "PYTHONHOME="
set "PYTHONPATH="
set "PY_CMD="
set "PY_LABEL="

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 goto :install_dependencies
)

call :find_python
if not defined PY_CMD (
  where py >nul 2>nul
  if not errorlevel 1 (
    py install 3.12
    call :find_python
  )
)
if not defined PY_CMD exit /b 1

if exist ".venv" if not exist ".venv\pyvenv.cfg" rmdir /s /q ".venv" 2>nul
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if errorlevel 1 rmdir /s /q ".venv" 2>nul
)
if exist ".venv" if not exist ".venv\Scripts\python.exe" rmdir /s /q ".venv" 2>nul
if not exist ".venv\Scripts\python.exe" call %PY_CMD% -m venv ".venv"
if errorlevel 1 exit /b 1
if not exist ".venv\pyvenv.cfg" exit /b 1

:install_dependencies
if exist "requirements.lock" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.lock
) else (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 exit /b 1
echo ok>".venv\.deps_ok"
exit /b 0

:find_python
call :tryexe "%LocalAppData%\Python\pythoncore-3.12-64\python.exe" "Python Manager 3.12 runtime"
if defined PY_CMD exit /b 0
for /d %%D in ("%LocalAppData%\Python\pythoncore-3.12*") do if not defined PY_CMD call :tryexe "%%~fD\python.exe" "Python Manager 3.12 runtime"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Python\bin\python3.12.exe" "Python Manager 3.12 alias"
if defined PY_CMD exit /b 0
call :trylauncher_short "3.12" "Python Launcher 3.12"
if defined PY_CMD exit /b 0
call :trylauncher_v "3.12" "Python Launcher -V:3.12"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Programs\Python\Python312\python.exe" "Python 3.12 local"
if defined PY_CMD exit /b 0
call :tryexe "%LocalAppData%\Programs\Python\Python311\python.exe" "Python 3.11 local"
if defined PY_CMD exit /b 0
for %%N in (python3.12.exe python3.11.exe python3.13.exe python.exe) do (
  for /f "delims=" %%P in ('where %%N 2^>nul') do if not defined PY_CMD call :tryexe "%%P" "Python PATH"
)
exit /b 0

:trylauncher_short
set "_QM_PROBE=%TEMP%\qualimatch_py_probe_%RANDOM%_%RANDOM%.txt"
py -%~1 -c "import sys,venv; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13),(3,14),(3,15)); print('QUALIMATCH_BASE_OK' if ok else 'QUALIMATCH_BASE_BAD'); sys.exit(0 if ok else 3)" >"%_QM_PROBE%" 2>&1
findstr /x /c:"QUALIMATCH_BASE_OK" "%_QM_PROBE%" >nul 2>&1
if not errorlevel 1 (
  set "PY_CMD=py -%~1"
  set "PY_LABEL=%~2"
)
del /q "%_QM_PROBE%" >nul 2>&1
exit /b 0

:trylauncher_v
set "_QM_PROBE=%TEMP%\qualimatch_py_probe_%RANDOM%_%RANDOM%.txt"
py -V:%~1 -c "import sys,venv; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13),(3,14),(3,15)); print('QUALIMATCH_BASE_OK' if ok else 'QUALIMATCH_BASE_BAD'); sys.exit(0 if ok else 3)" >"%_QM_PROBE%" 2>&1
findstr /x /c:"QUALIMATCH_BASE_OK" "%_QM_PROBE%" >nul 2>&1
if not errorlevel 1 (
  set "PY_CMD=py -V:%~1"
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
