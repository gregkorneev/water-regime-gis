#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import aoi_summary, load_aoi_feature, load_config, validate_aoi


def main() -> int:
    parser = argparse.ArgumentParser(description="Check test AOI GeoJSON.")
    parser.add_argument("--write-normalized", action="store_true", help="write a normalized QGIS-ready GeoJSON copy")
    args = parser.parse_args()

    config = load_config(ROOT)
    errors = validate_aoi(ROOT, config)
    summary = aoi_summary(ROOT, config)

    print(f"AOI: {summary['name']}")
    print(f"File: {summary['path']}")
    print(f"Source: OpenStreetMap {summary['osm']}")
    print(f"BBox EPSG:4326: {summary['bbox']}")
    print(f"Area approximate: {summary['area_ha']} ha")
    print(f"Analysis CRS: {summary['analysis_crs']}")

    if errors:
        print("AOI check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("AOI check: OK")
    if args.write_normalized:
        output = ROOT / "data/interim/tula_test_field.normalized.geojson"
        feature = load_aoi_feature(ROOT, config)
        output.write_text(
            json.dumps({"type": "FeatureCollection", "features": [feature]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Normalized AOI written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
