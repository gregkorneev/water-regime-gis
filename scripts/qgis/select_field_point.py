#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import configure_qgis_environment, qgis_prefix_path

configure_qgis_environment()

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsPointXY, QgsProject


CONFIG = ROOT / "configs/project.example.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create selected field layers from a map point.")
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--buffer-meters", type=float)
    args = parser.parse_args()

    QgsApplication.setPrefixPath(str(qgis_prefix_path()), True)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    target_crs = QgsCoordinateReferenceSystem(config["qgis"]["target_crs"])
    if not target_crs.isValid():
        print(f"CRS is not valid: {config['qgis']['target_crs']}")
        return 1

    app = QgsApplication([], False)
    app.initQgis()
    try:
        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        to_target = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        to_source = QgsCoordinateTransform(target_crs, source_crs, QgsProject.instance())
        center = to_target.transform(QgsPointXY(args.lon, args.lat))
        buffer_meters = args.buffer_meters or config["qgis"].get("field_buffer_meters", 500)
        area = QgsGeometry.fromPointXY(center).buffer(float(buffer_meters), 64)
        area.transform(to_source)

        point_path = ROOT / config["paths"]["selected_field_point"]
        area_path = ROOT / config["paths"]["selected_field_area"]
        point_path.parent.mkdir(parents=True, exist_ok=True)
        write_geojson(
            point_path,
            {
                "type": "Feature",
                "properties": {"name": "Selected field point", "analysis_crs": target_crs.authid()},
                "geometry": {"type": "Point", "coordinates": [args.lon, args.lat]},
            },
        )
        write_geojson(
            area_path,
            {
                "type": "Feature",
                "properties": {
                    "name": "Selected field working area",
                    "analysis_crs": target_crs.authid(),
                    "source": "map_point_buffer",
                    "buffer_meters": buffer_meters,
                },
                "geometry": json.loads(area.asJson()),
            },
        )
        print("Selected field: OK")
        print(f"Point EPSG:4326: {args.lon}, {args.lat}")
        print(f"Working buffer: {buffer_meters} m")
        print(f"Point layer: {point_path}")
        print(f"Area layer: {area_path}")
        return 0
    finally:
        app.exitQgis()


def write_geojson(path: Path, feature: dict) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
