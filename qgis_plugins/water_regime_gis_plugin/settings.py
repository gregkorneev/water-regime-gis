from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QGIS_PREFIX = Path(os.environ.get("QGIS_PREFIX_PATH", "/Applications/QGIS.app"))
QGIS_PYTHON = Path(
    os.environ.get(
        "QGIS_PYTHON",
        QGIS_PREFIX / "bin/python-qgis.bat" if sys.platform == "win32" else QGIS_PREFIX / "Contents/MacOS/python",
    )
)
QGIS_PROFILE_PLUGINS = (
    Path(os.environ["APPDATA"]) / "QGIS/QGIS3/profiles/default/python/plugins"
    if sys.platform == "win32"
    else Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
)

CONFIG_PATH = PROJECT_ROOT / "configs/project.example.json"
SELECT_FIELD_SCRIPT = PROJECT_ROOT / "scripts/qgis/select_field_point.py"
RESOLVE_BOUNDARY_SCRIPT = PROJECT_ROOT / "scripts/qgis/resolve_field_boundary.py"
SATELLITE_INDICES_SCRIPT = PROJECT_ROOT / "scripts/qgis/process_satellite_indices.py"
EXTERNAL_TIMESERIES_SCRIPT = PROJECT_ROOT / "scripts/qgis/download_external_timeseries.py"
REFRESH_TIMESERIES_SCRIPT = PROJECT_ROOT / "scripts/qgis/refresh_field_timeseries.py"
CHECK_CONTEXT_SCRIPT = PROJECT_ROOT / "scripts/qgis/check_qgis_context.py"
FIELD_ZONAL_MEANS_CSV = PROJECT_ROOT / "outputs/reports/field_zonal_means.csv"
SP_ZONAL_MEANS_CSV = PROJECT_ROOT / "outputs/reports/sp_zonal_means.csv"
SENTINEL1_ZONAL_MEANS_CSV = PROJECT_ROOT / "outputs/reports/sentinel1_zonal_means.csv"
EXPERIMENT_FIGURES_DIR = PROJECT_ROOT / "results/figures"
KORNIX_BY_FIELD_DIR = PROJECT_ROOT / "data/interim/kornix_timeseries/sp_all_calculation_timeseries_20260401_20260827_v006/by_field"
KORNIX_METHOD = "ivanov_n4l_meteo_soil"
KORNIX_ROW_SPACING_VARIANTS = ("65", "90")
ANALYSIS_EXCLUDED_FIELDS = {"SP_7_3"}
AVERAGE_CHART_EXCLUDED_FIELDS = ANALYSIS_EXCLUDED_FIELDS | {"SP_2_7", "SP_4_3", "SP_6_6", "SP_6_7"}
RADAR_MOISTURE_RANGE = (0.153527, 0.367581)
CHART_INDICES = {"NDVI", "NDMI", "SAVI", "NDRE", "FCOVER"}
FCOVER_COLOR = "#2ca02c"
CHART_INDEX_COLORS = {
    "FCOVER": FCOVER_COLOR,
    "NDMI": "#1f77b4",
    "NDRE": "#ff7f0e",
    "NDVI": "#d62728",
    "SAVI": "#9467bd",
}
RADAR_CHART_SERIES = {"VV", "VH"}
KORNIX_CHART_SERIES = {
    "Покрытие рядов": "ground_cover_fraction_row_geometry",
    "FCover expected (КОРНИКС)": "satellite_fcover_expected",
    "Ks": "water_stress_coefficient_ks",
    "Влага 0–10 см": "soil_surface_0_10_theta",
    "ET/PET": "actual_to_potential_et_ratio",
}
AVERAGE_CHART_KORNIX_SERIES = {
    label: column
    for label, column in KORNIX_CHART_SERIES.items()
    if column not in {"ground_cover_fraction_row_geometry", "soil_surface_0_10_theta"}
}
AVERAGE_CHART_RADAR_KORNIX_SERIES = {"Влага КОРНИКС 0–10 см": "soil_surface_0_10_theta"}
AVERAGE_CHART_DATE_OFFSETS = {"satellite_fcover_expected": 12}
KORNIX_CHART_COLORS = {
    "ground_cover_fraction_row_geometry": "#1f77b4",
    "satellite_fcover_expected": FCOVER_COLOR,
    "water_stress_coefficient_ks": "#ff7f0e",
    "soil_surface_0_10_theta": "#d62728",
    "actual_to_potential_et_ratio": "#9467bd",
    "precipitation": "#17becf",
    "irrigation": "#8c564b",
}
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
