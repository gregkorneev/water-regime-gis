#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import load_config
from water_regime_gis.webapp import find_available_port, page, qgis_python, system_status


def main() -> int:
    html = page(ROOT)
    assert "water-regime-gis" in html
    assert "EPSG:32637" in html
    assert "NDVI" in html
    assert "Выбор поля" in html
    assert "Сохранить выбранное поле" in html
    assert "Подготовить результат" in html
    assert "Проверить систему" in html
    assert "Готовность системы" in html
    assert 'id="system-status"' in html
    assert 'id="run-log"' in html
    assert "/status.json" in html
    assert "/job/start" in html
    assert "/job/status" in html
    assert "/nspd/wms" in html
    assert "/selected-field-area.geojson" in html
    assert (ROOT / "launch_panel.command").exists()
    assert (ROOT / "scripts/build_macos_app.py").exists()
    config = load_config(ROOT)
    status = system_status(ROOT, config)
    assert "steps" in status
    assert status["steps"]
    assert isinstance(find_available_port(start=8765, attempts=2), int)
    qgis = qgis_python(config)
    if qgis:
        assert Path(qgis).exists()
    print("Web app render: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
