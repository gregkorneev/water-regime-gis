from __future__ import annotations

import json
import math
from pathlib import Path


REQUIRED_DIRS = (
    "src",
    "scripts",
    "scripts/qgis",
    "notebooks",
    "configs",
    "data/aoi",
    "data/raw",
    "data/interim",
    "data/processed",
    "outputs/maps",
    "outputs/reports",
    "outputs/rasters",
    "docs/wiki",
)


def project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "pyproject.toml").exists():
            return path
    raise FileNotFoundError("pyproject.toml не найден")


def load_config(root: Path, config_path: str = "configs/project.example.json") -> dict:
    with (root / config_path).open(encoding="utf-8") as file:
        return json.load(file)


def missing_required_dirs(root: Path) -> list[str]:
    return [path for path in REQUIRED_DIRS if not (root / path).is_dir()]


def aoi_summary(root: Path, config: dict) -> dict:
    feature = load_aoi_feature(root, config)
    coords = feature["geometry"]["coordinates"][0]
    bbox = polygon_bbox(coords)
    return {
        "path": str(root / config["paths"]["test_aoi"]),
        "name": feature["properties"].get("name", ""),
        "osm": f"{feature['properties'].get('source_osm_type')}/{feature['properties'].get('source_osm_id')}",
        "bbox": bbox,
        "area_ha": polygon_area_ha(coords),
        "analysis_crs": feature["properties"].get("analysis_crs", config["qgis"]["target_crs"]),
    }


def selected_field_summary(root: Path, config: dict) -> dict:
    area_path = root / config["paths"]["selected_field_area"]
    point_path = root / config["paths"]["selected_field_point"]
    if not area_path.exists() or not point_path.exists():
        return {
            "selected": False,
            "name": "Поле не выбрано",
            "path": area_path,
            "point_path": point_path,
            "lon": "",
            "lat": "",
            "area_ha": "",
            "analysis_crs": config["qgis"]["target_crs"],
            "source": "",
        }

    feature = _first_feature(area_path)
    point = _first_feature(point_path)
    coords = feature["geometry"]["coordinates"][0]
    lon, lat = point["geometry"]["coordinates"]
    return {
        "selected": True,
        "name": feature["properties"].get("name", "Selected field"),
        "path": area_path,
        "point_path": point_path,
        "lon": lon,
        "lat": lat,
        "area_ha": polygon_area_ha(coords),
        "analysis_crs": feature["properties"].get("analysis_crs", config["qgis"]["target_crs"]),
        "source": feature["properties"].get("source", ""),
    }


def load_aoi_feature(root: Path, config: dict) -> dict:
    path = root / config["paths"]["test_aoi"]
    return _first_feature(path)


def _first_feature(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    features = data.get("features") or []
    if not features:
        raise ValueError(f"AOI file has no features: {path}")
    return features[0]


def polygon_bbox(coords: list[list[float]]) -> list[float]:
    lons = [point[0] for point in coords]
    lats = [point[1] for point in coords]
    return [min(lons), min(lats), max(lons), max(lats)]


def polygon_area_ha(coords: list[list[float]]) -> float:
    lat0 = math.radians(sum(point[1] for point in coords[:-1]) / (len(coords) - 1))
    meters = []
    for lon, lat in coords:
        x = math.radians(lon) * 6_378_137 * math.cos(lat0)
        y = math.radians(lat) * 6_378_137
        meters.append((x, y))
    area = 0.0
    for (x1, y1), (x2, y2) in zip(meters, meters[1:]):
        area += x1 * y2 - x2 * y1
    return round(abs(area) / 20_000, 2)


def validate_aoi(root: Path, config: dict) -> list[str]:
    feature = load_aoi_feature(root, config)
    geometry = feature.get("geometry", {})
    if geometry.get("type") != "Polygon":
        return [f"Expected Polygon, got {geometry.get('type')}"]
    coords = geometry.get("coordinates", [[]])[0]
    errors = []
    if len(coords) < 4:
        errors.append("Polygon has fewer than 4 coordinate pairs")
    if coords and coords[0] != coords[-1]:
        errors.append("Polygon ring is not closed")
    if errors:
        return errors
    bbox = polygon_bbox(coords)
    if not (36 <= bbox[0] <= bbox[2] <= 40 and 52 <= bbox[1] <= bbox[3] <= 55):
        errors.append(f"AOI bbox is outside expected Tula Oblast bounds: {bbox}")
    if polygon_area_ha(coords) <= 0:
        errors.append("Polygon area is zero")
    return errors
