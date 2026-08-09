#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import shutil
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "Water Regime GIS"
APP_DIR = ROOT / "dist" / f"{APP_NAME}.app"
CONTENTS = APP_DIR / "Contents"
MACOS = CONTENTS / "MacOS"
RESOURCES = CONTENTS / "Resources"
EXECUTABLE = MACOS / "water-regime-gis"


def main() -> int:
    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    MACOS.mkdir(parents=True)
    RESOURCES.mkdir(parents=True)
    write_info_plist()
    write_executable()
    print(f"macOS app: {APP_DIR}")
    return 0


def write_info_plist() -> None:
    plist = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "local.water-regime-gis.panel",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": EXECUTABLE.name,
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    with (CONTENTS / "Info.plist").open("wb") as file:
        plistlib.dump(plist, file)


def write_executable() -> None:
    script = """#!/bin/zsh
set -e

APP_EXEC_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$APP_EXEC_DIR/../../../.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display alert "Water Regime GIS" message "Python 3 не найден. Установите Python 3 и запустите приложение снова."'
  exit 1
fi

python3 scripts/run_app.py
"""
    EXECUTABLE.write_text(script, encoding="utf-8")
    EXECUTABLE.chmod(EXECUTABLE.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


if __name__ == "__main__":
    raise SystemExit(main())
