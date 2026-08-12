#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE = DIST / "water-regime-gis-release"
APP_NAME = "Water Regime GIS"
IMAGE = "water-regime-gis:release"
IMAGE_TAR = "water-regime-gis-image.tar"


def main() -> int:
    if RELEASE.exists():
        for path in (
            RELEASE / "Water Regime GIS.app",
            RELEASE / "Water Regime GIS.command",
            RELEASE / "Water Regime GIS.bat",
            RELEASE / "README_RU.txt",
            RELEASE / "docker-compose.yml",
            RELEASE / "windows-shell",
            RELEASE / IMAGE_TAR,
        ):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
    else:
        RELEASE.mkdir(parents=True)
    for name in (
        "configs",
        "data/aoi",
        "data/raw",
        "data/interim",
        "data/processed",
        "outputs/maps",
        "outputs/reports",
        "outputs/rasters",
    ):
        (RELEASE / name).mkdir(parents=True, exist_ok=True)
    release_config = RELEASE / "configs/project.example.json"
    if not release_config.exists():
        shutil.copy2(ROOT / "configs/project.example.json", release_config)
    write_compose()
    write_macos_launcher()
    write_windows_launcher()
    copy_windows_shell()
    write_macos_app()
    write_readme()
    build_image()
    print(f"Release package: {RELEASE}")
    return 0


def write_compose() -> None:
    (RELEASE / "docker-compose.yml").write_text(
        """services:
  water-regime-gis:
    image: water-regime-gis:release
    platform: linux/amd64
    ports:
      - "8765:8765"
    environment:
      WATER_REGIME_GIS_RUNTIME: docker
      WATER_REGIME_GIS_HOST: 0.0.0.0
      WATER_REGIME_GIS_PORT: 8765
      WATER_REGIME_GIS_NO_BROWSER: "1"
    volumes:
      - ./data:/app/data
      - ./outputs:/app/outputs
      - ./configs:/app/configs:ro
""",
        encoding="utf-8",
    )


def write_macos_launcher() -> None:
    path = RELEASE / "Water Regime GIS.command"
    path.write_text(
        """#!/bin/zsh
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
open "$APP_DIR/Water Regime GIS.app"
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_windows_launcher() -> None:
    (RELEASE / "Water Regime GIS.bat").write_text(
        """@echo off
setlocal

cd /d "%~dp0"

if exist "Water Regime GIS.exe" (
  start "" "Water Regime GIS.exe"
  exit /b 0
)

where dotnet >nul 2>nul
if errorlevel 1 (
  echo .NET SDK не найден. Установите .NET SDK 8 или соберите Water Regime GIS.exe из windows-shell.
  pause
  exit /b 1
)

dotnet run --project windows-shell\\WaterRegimeGIS.csproj
""",
        encoding="utf-8",
    )


def copy_windows_shell() -> None:
    target = RELEASE / "windows-shell"
    shutil.copytree(ROOT / "packaging/windows", target)


def write_macos_app() -> None:
    app_dir = RELEASE / f"{APP_NAME}.app"
    contents = app_dir / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    plist = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "local.water-regime-gis.docker",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "water-regime-gis",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as file:
        plistlib.dump(plist, file)
    executable = macos / "water-regime-gis"
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise RuntimeError("swiftc not found. macOS release app requires Swift toolchain.")
    subprocess.run([swiftc, str(ROOT / "packaging/macos/WaterRegimeGIS.swift"), "-o", str(executable)], cwd=ROOT, check=True)
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_readme() -> None:
    (RELEASE / "README_RU.txt").write_text(
        """Water Regime GIS

Требование: установленный Docker Desktop.

macOS:
1. Откройте Water Regime GIS.app.
2. Приложение само запустит Docker-контейнер и откроет интерфейс внутри окна приложения.

Windows:
1. Если рядом есть Water Regime GIS.exe, откройте его.
2. Если exe еще не собран, откройте Water Regime GIS.bat или windows-shell\\Build Windows App.bat.
3. Приложение само запустит Docker-контейнер и откроет интерфейс внутри окна приложения.

Папки рядом с launcher-ами:
- data: пользовательские входные геоданные;
- outputs: результаты;
- configs: конфигурация проекта.

QGIS находится внутри Docker-образа и не открывается пользователем.
Пользовательский интерфейс открывается в desktop-окне, а не в системном браузере.
Файл water-regime-gis-image.tar содержит готовый Docker-образ приложения.
""",
        encoding="utf-8",
    )


def build_image() -> None:
    subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", IMAGE, "."], cwd=ROOT, check=True)
    subprocess.run(["docker", "save", "-o", str(RELEASE / IMAGE_TAR), IMAGE], cwd=ROOT, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
