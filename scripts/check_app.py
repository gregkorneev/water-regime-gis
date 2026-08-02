#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.app import status_lines
from water_regime_gis.project import load_config


def main() -> int:
    lines = status_lines(ROOT, load_config(ROOT))
    assert any("water-regime-gis" in line for line in lines)
    assert any("EPSG:32637" in line for line in lines)
    assert any("NDVI" in line for line in lines)
    print("App status model: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
