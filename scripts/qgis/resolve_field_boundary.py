#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import configure_qgis_environment, qgis_prefix_path

configure_qgis_environment()

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsPointXY, QgsProject


CONFIG = ROOT / "configs/project.example.json"


def main() -> int:
    QgsApplication.setPrefixPath(str(qgis_prefix_path()), True)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    point_path = ROOT / config["paths"]["selected_field_point"]
    area_path = ROOT / config["paths"]["selected_field_area"]

    if not point_path.exists():
        print("Boundary source: none")
        print("Selected point does not exist yet.")
        return 1

    app = QgsApplication([], False)
    app.initQgis()
    try:
        lon, lat = selected_point(point_path)
        response = request_feature_info(config, lon, lat)
        feature = first_polygon_feature(response)
        if not feature:
            print("Boundary source: map_point_buffer")
            print("NSPD did not return a polygon for the selected point.")
            return 0

        feature["geometry"] = geometry_to_wgs84(feature["geometry"])
        properties = feature.setdefault("properties", {})
        properties["name"] = properties.get("descr") or properties.get("label") or "NSPD selected parcel"
        properties["analysis_crs"] = config["qgis"]["target_crs"]
        properties["source"] = "nspd_getfeatureinfo"
        properties["selected_lon"] = lon
        properties["selected_lat"] = lat
        write_geojson(area_path, feature)

        print("Boundary source: nspd_getfeatureinfo")
        print(f"Boundary layer: {area_path}")
        print(f"Feature name: {properties['name']}")
        return 0
    except Exception as exc:
        print("Boundary source: map_point_buffer")
        print(f"NSPD boundary lookup failed: {exc}")
        return 0
    finally:
        app.exitQgis()


def selected_point(path: Path) -> tuple[float, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    feature = data["features"][0]
    lon, lat = feature["geometry"]["coordinates"]
    return float(lon), float(lat)


def request_feature_info(config: dict, lon: float, lat: float) -> dict:
    source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    web_mercator = QgsCoordinateReferenceSystem("EPSG:3857")
    to_web = QgsCoordinateTransform(source_crs, web_mercator, QgsProject.instance())
    point = to_web.transform(QgsPointXY(lon, lat))
    span = float(config["nspd"].get("feature_info_span_meters", 500))
    size = 101
    layer_id = str(config["nspd"].get("parcels_wms_layer_id", 36048))
    bbox = f"{point.x() - span},{point.y() - span},{point.x() + span},{point.y() + span}"
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": layer_id,
        "QUERY_LAYERS": layer_id,
        "CRS": "EPSG:3857",
        "BBOX": bbox,
        "WIDTH": str(size),
        "HEIGHT": str(size),
        "I": str(size // 2),
        "J": str(size // 2),
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": "10",
        "STYLES": "",
        "FORMAT": "image/png",
    }
    proxy = os.environ.get("WATER_REGIME_GIS_APP_URL", "").rstrip("/")
    if proxy:
        proxy = f"{proxy}/nspd/wms"
    else:
        proxy = config["nspd"].get("local_wms_proxy_url", "")
    if proxy:
        parsed = urlparse(proxy)
        url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(params)}"
    else:
        url = f"https://nspd.gov.ru/api/aeggis/v3/{layer_id}/wms?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
            "Referer": "https://nspd.gov.ru/map?active_layers=%E8%B3%90",
        },
    )
    with urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def first_polygon_feature(data: dict) -> dict | None:
    features = data.get("features") or data.get("data", {}).get("features") or []
    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") in {"Polygon", "MultiPolygon"}:
            return feature
    return None


def geometry_to_wgs84(geometry: dict) -> dict:
    if not geometry_needs_web_mercator_transform(geometry):
        return geometry
    source_crs = QgsCoordinateReferenceSystem("EPSG:3857")
    target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
    qgis_geometry = QgsGeometry.fromJson(json.dumps(geometry))
    qgis_geometry.transform(transform)
    return json.loads(qgis_geometry.asJson())


def geometry_needs_web_mercator_transform(geometry: dict) -> bool:
    coordinate = first_coordinate(geometry.get("coordinates", []))
    if not coordinate:
        return False
    x, y = coordinate[:2]
    return abs(float(x)) > 180 or abs(float(y)) > 90


def first_coordinate(value: object) -> list[float] | None:
    if not isinstance(value, list) or not value:
        return None
    if isinstance(value[0], (int, float)):
        return value
    return first_coordinate(value[0])


def write_geojson(path: Path, feature: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
