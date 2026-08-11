@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите Python 3 и запустите панель снова.
  pause
  exit /b 1
)

python scripts\run_app.py
