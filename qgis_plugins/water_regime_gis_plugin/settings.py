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
CHECK_CONTEXT_SCRIPT = PROJECT_ROOT / "scripts/qgis/check_qgis_context.py"
FIELD_ZONAL_MEANS_CSV = PROJECT_ROOT / "outputs/reports/field_zonal_means.csv"
DOUBLE_LOGISTIC_CHART_FIT = {
    "indices": {"NDVI", "NDRE", "SAVI"},
    "min_observations": 6,
    "loss": "soft_l1",
    "baseline_bounds": (-0.1, 0.5),
    "upper_bounds": (0.3, 1.0),
    "rate_bounds": (0.01, 0.35),
    "max_nfev": 800,
    "enforce_unimodal": True,
}
