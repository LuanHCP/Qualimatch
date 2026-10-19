@echo off
setlocal
cd /d "%~dp0"
title Instalacao - Sistema de Nao Conformidades
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 backend\setup_windows.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERRO: Python 3 nao foi encontrado. Instale o Python e marque "Add Python to PATH".
    pause
    exit /b 1
  )
  python backend\setup_windows.py
)
if errorlevel 1 (
  echo.
  echo A instalacao nao foi concluida. Leia a mensagem acima.
  pause
  exit /b 1
)
call INICIAR_SISTEMA.bat
