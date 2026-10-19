@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   TracoMatch - Configurar PostgreSQL (pgAdmin 4)
echo ============================================
echo.
echo Este script cria o banco "tracos_teste", as tabelas e os
echo usuarios de teste, e grava o arquivo .env.local.
echo.
echo Use a senha do usuario "postgres" do seu PostgreSQL local
echo (a mesma que voce usa para abrir o pgAdmin 4).
echo.

set "PSQL=psql"
where psql >nul 2>nul
if errorlevel 1 (
  for /d %%d in ("C:\Program Files\PostgreSQL\*") do set "PSQL=%%d\bin\psql.exe"
)

if not exist "%PSQL%" (
  if "%PSQL%"=="psql" (
    echo Nao encontrei o psql automaticamente.
    echo Abra o pgAdmin 4, menu Ferramentas ^> "SQL Shell (psql)" para
    echo confirmar que o PostgreSQL esta instalado, ou informe abaixo
    echo o caminho completo do psql.exe ^(ex.: C:\Program Files\PostgreSQL\16\bin\psql.exe^).
    set /p PSQL=Caminho do psql.exe:
  )
)

set /p PGPWD=Senha do usuario postgres:
set "PGPASSWORD=%PGPWD%"

echo.
echo [1/2] Criando banco "tracos_teste" ^(ignora aviso se ja existir^)...
"%PSQL%" -U postgres -h 127.0.0.1 -f "database\create-database.sql"

echo.
echo [2/2] Criando tabelas e usuarios de teste...
"%PSQL%" -U postgres -h 127.0.0.1 -d tracos_teste -f "database\setup.sql"
set "SETUP_ERR=%ERRORLEVEL%"

rem Codifica a senha para uso dentro da URL (essencial se a senha tiver
rem caracteres como @, :, / ou espaco - sem isso o Node entende a URL
rem errada e o site fica preso em "Modo local de demonstracao" mesmo com
rem o PostgreSQL funcionando normalmente).
for /f "usebackq delims=" %%E in (`powershell -NoProfile -Command "[uri]::EscapeDataString($env:PGPWD)"`) do set "PGPWD_ENC=%%E"

echo.
echo Gravando .env.local...
> .env.local echo DATABASE_URL=postgresql://postgres:%PGPWD_ENC%@127.0.0.1:5432/tracos_teste
>> .env.local echo API_PORT=3001
>> .env.local echo APP_ORIGIN=http://localhost:3000

set "PGPASSWORD="
set "PGPWD="
set "PGPWD_ENC="

echo.
if "%SETUP_ERR%"=="0" (
  echo Concluido! Rode "npm run dev" e a tela de login vai mostrar
  echo "PostgreSQL conectado" em vez de "Modo local de demonstracao".
) else (
  echo Terminou com avisos/erros acima ^(comuns se o banco ja existia^).
  echo Confira as mensagens do psql. Se "tracos_teste" e as tabelas
  echo ja existirem, pode rodar "npm run dev" normalmente.
)
pause
