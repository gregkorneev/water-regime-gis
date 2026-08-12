@echo off
setlocal
cd /d "%~dp0"

where dotnet >nul 2>nul
if errorlevel 1 (
  echo .NET SDK 8 не найден. Установите .NET SDK 8 и повторите сборку.
  pause
  exit /b 1
)

dotnet publish WaterRegimeGIS.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o ".."
echo Готово: ..\Water Regime GIS.exe
pause
