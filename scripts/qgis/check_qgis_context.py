#!/usr/bin/env python3
from __future__ import annotations

try:
    from qgis.core import QgsApplication
except Exception as exc:
    print("PyQGIS is not available in this Python environment.")
    print(f"Error: {exc}")
    raise SystemExit(1)

print("PyQGIS: OK")
print(f"QGIS version: {QgsApplication.qgisVersion()}")
