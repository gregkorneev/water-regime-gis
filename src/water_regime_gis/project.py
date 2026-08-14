from __future__ import annotations

import json
import math
from pathlib import Path


REQUIRED_DIRS = (
    "src",
    "scripts",
    "scripts/qgis",
    "configs",
    "data/aoi",
    "data/interim",
    "data/processed",
    "outputs/maps",
    "outputs/rasters",
    "outputs/imagery",
    "outputs/reports",
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


def utm_crs_for_lon_lat(lon: float, lat: float) -> str:
    zone = max(1, min(60, int((lon + 180) // 6) + 1))
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def selected_area_crs(root: Path, config: dict) -> str:
    area_path = root / config["paths"]["selected_field_area"]
    if not area_path.exists():
        return config["qgis"]["target_crs"]
    feature = _first_feature(area_path)
    return feature.get("properties", {}).get("analysis_crs") or config["qgis"]["target_crs"]


def _first_feature(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    features = data.get("features") or []
    if not features:
        raise ValueError(f"AOI file has no features: {path}")
    return features[0]


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
