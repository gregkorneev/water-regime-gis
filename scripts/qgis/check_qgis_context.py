#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import configure_qgis_environment, qgis_prefix_path

configure_qgis_environment()

try:
    from qgis.core import Qgis, QgsApplication
except Exception as exc:
    print("PyQGIS is not available in this Python environment.")
    print(f"Error: {exc}")
    raise SystemExit(1)

if not QgsApplication.prefixPath():
    QgsApplication.setPrefixPath(str(qgis_prefix_path()), True)

print("PyQGIS: OK")
print(f"QGIS version: {Qgis.QGIS_VERSION}")
print(f"QGIS prefix path: {QgsApplication.prefixPath()}")
