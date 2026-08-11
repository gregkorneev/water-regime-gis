@echo off
setlocal

cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker не найден. Установите Docker Desktop и запустите файл снова.
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop не запущен. Запустите Docker Desktop и повторите запуск.
  pause
  exit /b 1
)

docker compose up --build -d
start http://127.0.0.1:8765
