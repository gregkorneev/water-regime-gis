from __future__ import annotations

import os
import sys
from pathlib import Path

QGIS_PREFIX = Path("/Applications/QGIS.app")
QGIS_PROFILE_PLUGINS = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"

def qgis_prefix_path() -> Path:
    return Path(os.environ.get("QGIS_PREFIX_PATH", QGIS_PREFIX))


def qgis_project_data_path() -> Path:
    return Path(os.environ.get("PROJ_DATA", QGIS_PREFIX / "Contents/Resources/qgis/proj"))


def qgis_profile_plugins() -> Path:
    return QGIS_PROFILE_PLUGINS


def configure_qgis_environment() -> None:
    os.environ.setdefault("PROJ_DATA", str(qgis_project_data_path()))
    os.environ.setdefault("QGIS_PREFIX_PATH", str(qgis_prefix_path()))
    root = Path(__file__).resolve().parents[2]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
