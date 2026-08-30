#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "water_regime_gis_plugin"
SOURCE = ROOT / "qgis_plugins" / PLUGIN_NAME
TARGET = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins" / PLUGIN_NAME


def main() -> int:
    if not SOURCE.exists():
        print(f"Plugin source is missing: {SOURCE}")
        return 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.is_symlink() or TARGET.exists():
        if TARGET.resolve() == SOURCE.resolve():
            print(f"QGIS plugin already installed: {TARGET}")
            return 0
        if TARGET.is_dir() and not TARGET.is_symlink():
            shutil.rmtree(TARGET)
        else:
            TARGET.unlink()
    if sys.platform == "win32":
        shutil.copytree(SOURCE, TARGET)
        print(f"QGIS plugin copied: {SOURCE} -> {TARGET}")
    else:
        TARGET.symlink_to(SOURCE, target_is_directory=True)
        print(f"QGIS plugin installed: {TARGET} -> {SOURCE}")
    print("Restart QGIS and enable 'Water Regime GIS' in Plugin Manager if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
