from __future__ import annotations

import json
from pathlib import Path


REQUIRED_DIRS = (
    "src",
    "scripts",
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
