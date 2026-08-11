#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import load_config


REQUIRED = {"NDVI", "NDMI", "NDWI"}


def main() -> int:
    config = load_config(ROOT)
    satellite = config.get("satellite", {})
    script = ROOT / config["qgis"]["satellite_indices_script"]
    indices = set(satellite.get("indices", []))
    if satellite.get("provider") != "planetary-computer-stac":
        print("Unexpected satellite provider.")
        return 1
    if satellite.get("collection") != "sentinel-2-l2a":
        print("Unexpected satellite collection.")
        return 1
    if not script.exists():
        print(f"Satellite script is missing: {script}")
        return 1
    missing = sorted(REQUIRED - indices)
    if missing:
        print(f"Required indices are missing: {', '.join(missing)}")
        return 1
    print("Satellite pipeline: OK")
    print(f"Provider: {satellite['provider']}")
    print(f"Collection: {satellite['collection']}")
    print(f"Indices: {', '.join(satellite['indices'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
