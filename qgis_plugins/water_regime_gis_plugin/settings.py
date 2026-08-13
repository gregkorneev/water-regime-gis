from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path("/Users/korneev/Desktop/water-regime-gis")
QGIS_PREFIX = Path("/Applications/QGIS.app")
QGIS_PYTHON = QGIS_PREFIX / "Contents/MacOS/python"
QGIS_PROFILE_PLUGINS = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"

CONFIG_PATH = PROJECT_ROOT / "configs/project.example.json"
SELECT_FIELD_SCRIPT = PROJECT_ROOT / "scripts/qgis/select_field_point.py"
RESOLVE_BOUNDARY_SCRIPT = PROJECT_ROOT / "scripts/qgis/resolve_field_boundary.py"
SATELLITE_INDICES_SCRIPT = PROJECT_ROOT / "scripts/qgis/process_satellite_indices.py"
CREATE_PROJECT_SCRIPT = PROJECT_ROOT / "scripts/qgis/create_demo_project.py"
CHECK_CONTEXT_SCRIPT = PROJECT_ROOT / "scripts/qgis/check_qgis_context.py"
