#!/usr/bin/env python3
from __future__ import annotations

try:
    from qgis.core import Qgis, QgsApplication
except Exception as exc:
    print("PyQGIS is not available in this Python environment.")
    print(f"Error: {exc}")
    raise SystemExit(1)

if not QgsApplication.prefixPath():
    QgsApplication.setPrefixPath("/Applications/QGIS.app/Contents/MacOS", True)

print("PyQGIS: OK")
print(f"QGIS version: {Qgis.QGIS_VERSION}")
print(f"QGIS prefix path: {QgsApplication.prefixPath()}")
