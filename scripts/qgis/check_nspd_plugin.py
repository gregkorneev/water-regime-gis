#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("PROJ_DATA", "/Applications/QGIS.app/Contents/Resources/qgis/proj")

from qgis.core import Qgis, QgsApplication


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/project.example.json"


def main() -> int:
    QgsApplication.setPrefixPath("/Applications/QGIS.app", True)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    plugin_id = config["nspd"]["plugin_id"]
    plugin_name = config["nspd"]["plugin_name"]

    app = QgsApplication([], False)
    app.initQgis()
    try:
        plugin_paths = [Path(path) for path in QgsApplication.pluginPath().split(os.pathsep) if path]
        profile_plugins = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
        plugin_paths.append(profile_plugins)

        matches = []
        for plugins_dir in plugin_paths:
            for candidate in (plugins_dir / plugin_id, plugins_dir / plugin_name):
                if (candidate / "metadata.txt").exists():
                    matches.append(candidate)

        print("NSPD plugin check")
        print(f"QGIS version: {Qgis.QGIS_VERSION}")
        print(f"Expected plugin: {plugin_name}")
        print(f"Plugin page: {config['nspd']['plugin_url']}")
        if matches:
            print("Status: OK")
            for match in matches:
                print(f"Found: {match}")
            return 0

        print("Status: NOT INSTALLED")
        print("Install in QGIS: Plugins -> Manage and Install Plugins -> search 'rosreestr' -> install 'rosreestr-search-qgis-plugin'.")
        return 1
    finally:
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
