#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import load_config
from water_regime_gis.webapp import page, qgis_python


def main() -> int:
    html = page(ROOT)
    assert "water-regime-gis" in html
    assert "EPSG:32637" in html
    assert "NDVI" in html
    assert "Проверить AOI" in html
    qgis = qgis_python(load_config(ROOT))
    if qgis:
        assert Path(qgis).exists()
    print("Web app render: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
