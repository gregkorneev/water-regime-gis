#!/usr/bin/env python3
from __future__ import annotations

import configparser
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/project.example.json"

sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import qgis_profile_plugins


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    nspd = config["nspd"]
    plugin_dir = qgis_profile_plugins() / nspd["plugin_id"]
    metadata = plugin_dir / "metadata.txt"

    if metadata_valid(metadata, nspd["plugin_name"]):
        print("NSPD plugin: OK")
        print(f"Installed: {plugin_dir}")
        return 0

    if metadata.exists():
        print("NSPD plugin metadata is invalid. Reinstalling.")

    qgis_profile_plugins().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="water-regime-gis-nspd-") as tmp:
        archive = Path(tmp) / "nspd-plugin.zip"
        urlretrieve(nspd["plugin_download_url"], archive)
        with zipfile.ZipFile(archive) as file:
            file.extractall(qgis_profile_plugins())

    if not metadata_valid(metadata, nspd["plugin_name"]):
        print("NSPD plugin install: FAILED")
        print(f"Expected: {metadata}")
        return 1

    print("NSPD plugin install: OK")
    print(f"Installed: {plugin_dir}")
    return 0


def metadata_valid(path: Path, expected_name: str) -> bool:
    if not path.exists():
        return False
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return False
    return parser.has_section("general") and parser["general"].get("name") == expected_name


if __name__ == "__main__":
    raise SystemExit(main())
