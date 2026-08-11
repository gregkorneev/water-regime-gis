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
cd "$APP_DIR"

if ! command -v docker >/dev/null 2>&1; then
  osascript -e 'display alert "Water Regime GIS" message "Docker Desktop не найден. Установите Docker Desktop и запустите приложение снова."'
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  open -a Docker || true
  osascript -e 'display alert "Water Regime GIS" message "Docker Desktop запускается. Повторите запуск через минуту, когда Docker будет готов."'
  exit 1
fi

if ! docker image inspect water-regime-gis:release >/dev/null 2>&1; then
  docker load -i water-regime-gis-image.tar
fi

docker compose up -d
open http://127.0.0.1:8765
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_windows_launcher() -> None:
    (RELEASE / "Water Regime GIS.bat").write_text(
        """@echo off
setlocal

cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop не найден. Установите Docker Desktop и запустите файл снова.
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop не запущен. Запустите Docker Desktop и повторите запуск.
  pause
  exit /b 1
)

docker image inspect water-regime-gis:release >nul 2>nul
if errorlevel 1 (
  docker load -i water-regime-gis-image.tar
)

docker compose up -d
start http://127.0.0.1:8765
""",
        encoding="utf-8",
    )


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
    executable.write_text(
        """#!/bin/zsh
set -e

APP_EXEC_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_DIR="$(cd "$APP_EXEC_DIR/../../.." && pwd)"
exec "$RELEASE_DIR/Water Regime GIS.command"
""",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_readme() -> None:
    (RELEASE / "README_RU.txt").write_text(
        """Water Regime GIS

Требование: установленный Docker Desktop.

macOS:
1. Откройте Water Regime GIS.app или Water Regime GIS.command.
2. Панель откроется в браузере: http://127.0.0.1:8765

Windows:
1. Откройте Water Regime GIS.bat.
2. Панель откроется в браузере: http://127.0.0.1:8765

Папки рядом с launcher-ами:
- data: пользовательские входные геоданные;
- outputs: результаты;
- configs: конфигурация проекта.

QGIS находится внутри Docker-образа и не открывается пользователем.
Файл water-regime-gis-image.tar содержит готовый Docker-образ приложения.
""",
        encoding="utf-8",
    )


def build_image() -> None:
    subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", IMAGE, "."], cwd=ROOT, check=True)
    subprocess.run(["docker", "save", "-o", str(RELEASE / IMAGE_TAR), IMAGE], cwd=ROOT, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
