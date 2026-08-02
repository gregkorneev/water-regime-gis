from __future__ import annotations

import json
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
    path = root / config["paths"]["test_aoi"]
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    feature = data["features"][0]
    coords = feature["geometry"]["coordinates"][0]
    lons = [point[0] for point in coords]
    lats = [point[1] for point in coords]
    return {
        "path": str(path),
        "name": feature["properties"].get("name", ""),
        "osm": f"{feature['properties'].get('source_osm_type')}/{feature['properties'].get('source_osm_id')}",
        "bbox": [min(lons), min(lats), max(lons), max(lats)],
        "analysis_crs": feature["properties"].get("analysis_crs", config["qgis"]["target_crs"]),
    }
