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
    imagery_script = ROOT / "scripts/qgis/download_field_imagery.py"
    analysis_script = ROOT / "scripts/qgis/download_field_analysis.py"
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
    if not imagery_script.exists():
        print(f"Field imagery script is missing: {imagery_script}")
        return 1
    if not analysis_script.exists():
        print(f"Field analysis script is missing: {analysis_script}")
        return 1
    imagery_text = imagery_script.read_text(encoding="utf-8")
    for marker in ("KAA.gpkg", "SP.gpkg", "sentinel_true_color.tif", "download_manifest.json"):
        if marker not in imagery_text:
            print(f"Field imagery marker is missing: {marker}")
            return 1
    analysis_text = analysis_script.read_text(encoding="utf-8")
    for marker in ("sentinel_analysis.tif", "cloud_mask.tif", "analysis_manifest.json", '"SCL"'):
        if marker not in analysis_text:
            print(f"Field analysis marker is missing: {marker}")
            return 1
    script_text = script.read_text(encoding="utf-8")
    for option in ("--area", "--rasters", "--report", "--indices", "--date-from", "--scene-id"):
        if option not in script_text:
            print(f"Satellite script option is missing: {option}")
            return 1
    missing = sorted(REQUIRED - indices)
    if missing:
        print(f"Required indices are missing: {', '.join(missing)}")
        return 1
    if config.get("paths", {}).get("metrics_report") != "outputs/reports/latest_metrics.json":
        print("Metrics report path is not configured.")
        return 1
    print("Satellite pipeline: OK")
    print(f"Provider: {satellite['provider']}")
    print(f"Collection: {satellite['collection']}")
    print(f"Indices: {', '.join(satellite['indices'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
