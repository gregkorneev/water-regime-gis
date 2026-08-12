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
RELEASE_ARCHIVE = DIST / "water-regime-gis-release.zip"


def main() -> int:
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE_ARCHIVE.unlink(missing_ok=True)
    RELEASE.mkdir(parents=True)
    for name in (
        "notebooks",
        "src",
        "scripts/qgis",
        "docs/wiki",
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
    copy_runtime_sources()
    write_compose()
    write_macos_launcher()
    write_windows_launcher()
    copy_windows_shell()
    write_macos_app()
    write_readme()
    build_archive()
    print(f"Release package: {RELEASE}")
    print(f"Release archive: {RELEASE_ARCHIVE}")
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
QGIS_PYTHON="${WATER_REGIME_GIS_QGIS_PYTHON:-/Applications/QGIS.app/Contents/MacOS/python}"

if [ -x "$APP_DIR/Water Regime GIS.app/Contents/MacOS/water-regime-gis" ]; then
  open "$APP_DIR/Water Regime GIS.app"
  exit 0
fi

if [ ! -x "$QGIS_PYTHON" ]; then
  echo "QGIS не найден. Установите QGIS с официального сайта в /Applications/QGIS.app."
  exit 1
fi

cd "$APP_DIR"
WATER_REGIME_GIS_RUNTIME=local-release "$QGIS_PYTHON" scripts/run_app.py
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
        "CFBundleIdentifier": "local.water-regime-gis",
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

Release-пакет для GitHub.

Что должен установить пользователь:
- Water Regime GIS из этого архива;
- чистый QGIS с официального сайта.

Пользователю не нужно устанавливать Python, GDAL, плагины QGIS, Docker Desktop, .NET SDK или исходный код проекта.
Приложение запускает backend через Python, который входит в QGIS.
Кадастровый модуль и рабочие папки готовятся автоматически при запуске.

macOS:
1. Откройте Water Regime GIS.app.
2. Приложение само найдет /Applications/QGIS.app, запустит локальный backend и откроет интерфейс внутри окна приложения.

Windows:
1. Если рядом есть Water Regime GIS.exe, откройте его.
2. Если exe еще не собран, откройте Water Regime GIS.bat или windows-shell\\Build Windows App.bat.
3. Приложение само найдет установленный QGIS/OSGeo4W, запустит локальный backend и откроет интерфейс внутри окна приложения.

Папки рядом с launcher-ами:
- data: пользовательские входные геоданные;
- outputs: результаты;
- configs: конфигурация проекта.

QGIS не открывается пользователем: он используется как скрытый геодвижок.
Пользовательский интерфейс открывается в desktop-окне, а не в системном браузере.
""",
        encoding="utf-8",
    )


def copy_runtime_sources() -> None:
    shutil.copy2(ROOT / "pyproject.toml", RELEASE / "pyproject.toml")
    shutil.copy2(ROOT / "LICENSE", RELEASE / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", RELEASE / "THIRD_PARTY_NOTICES.md")
    shutil.copytree(ROOT / "src", RELEASE / "src", ignore=ignore_generated, dirs_exist_ok=True)
    shutil.copytree(ROOT / "docs/wiki", RELEASE / "docs/wiki", ignore=ignore_generated, dirs_exist_ok=True)
    for script in (
        "run_app.py",
        "check_project.py",
        "check_satellite_pipeline.py",
        "install_nspd_plugin.py",
    ):
        shutil.copy2(ROOT / "scripts" / script, RELEASE / "scripts" / script)
    shutil.copytree(ROOT / "scripts/qgis", RELEASE / "scripts/qgis", ignore=ignore_generated, dirs_exist_ok=True)


def ignore_generated(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in {"__pycache__", ".DS_Store"} or name.endswith((".pyc", ".pyo"))}


def build_archive() -> None:
    archive_base = RELEASE_ARCHIVE.with_suffix("")
    shutil.make_archive(str(archive_base), "zip", root_dir=DIST, base_dir=RELEASE.name)


if __name__ == "__main__":
    raise SystemExit(main())
