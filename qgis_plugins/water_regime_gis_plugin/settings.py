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
CHART_INDICES = {"NDVI", "NDMI", "SAVI", "NDRE"}
SEASONAL_CHART_FIT = {
    "loss": "soft_l1",
    "robust_f_scale": 0.12,
    "amplitude_floor": 0.03,
    "baseline_bounds": (-0.5, 0.8),
    "amplitude_bounds": (0.15, 2.5),
    "maximum_plateau_fraction": 0.45,
    "plateau_slope_bounds": (0.0, 0.004),
    "maximum_growth_midpoint_fraction": 0.8,
    "minimum_width_days": 7.0,
    "minimum_width_fraction": 0.15,
    "width_extra_days": 90.0,
    "rate_bounds": (0.01, 0.35),
    "downward_dip_threshold": 0.12,
    "minimum_dip_weight": 0.2,
    "metric_residual_cap": 0.35,
    "plateau_penalty": 0.05,
    "multi_starts": ((0.0, 0.05), (0.12, 0.07), (0.25, 0.1), (0.4, 0.15)),
    "max_nfev": 900,
}
