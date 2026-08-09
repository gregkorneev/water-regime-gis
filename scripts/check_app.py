#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import load_config
import water_regime_gis.webapp as webapp
from water_regime_gis.webapp import (
    COMMAND_TIMEOUT_SECONDS,
    QGIS_DOWNLOAD_URL,
    environment_status,
    find_available_port,
    format_job_steps,
    job_status,
    page,
    qgis_python,
    readiness_status,
    system_status,
)


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
    assert "Среда" in html
    assert 'id="system-status"' in html
    assert 'id="environment-table"' in html
    assert 'id="environment-action"' in html
    assert 'id="select-field-button"' in html
    assert 'id="prepare-action"' in html
    assert 'id="run-log"' in html
    assert "/status.json" in html
    assert "/environment.json" in html
    assert "/readiness.json" in html
    assert "/job/start" in html
    assert "/job/status" in html
    assert "refreshPanelState" in html
    assert 'kind: "select-field"' in html
    assert "/nspd/wms" in html
    assert "/selected-field-area.geojson" in html
    assert (ROOT / "launch_panel.command").exists()
    assert (ROOT / "scripts/build_macos_app.py").exists()
    config = load_config(ROOT)
    status = system_status(ROOT, config)
    assert "steps" in status
    assert status["steps"]
    environment = environment_status(ROOT, config)
    assert "qgis" in environment
    assert environment["qgis"]["download_url"] == QGIS_DOWNLOAD_URL
    assert "nspd_plugin" in environment
    assert "artifacts" in environment
    readiness = readiness_status(ROOT, config)
    assert "can_select_field" in readiness
    assert "can_prepare_result" in readiness
    assert "reasons" in readiness
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        (temp_root / "configs").mkdir()
        (temp_root / "configs/project.example.json").write_text(
            (ROOT / "configs/project.example.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        temp_readiness = readiness_status(temp_root, load_config(temp_root))
        assert not temp_readiness["can_prepare_result"]
        assert "Сначала выберите точку поля" in temp_readiness["reasons"]["prepare_result"] or not temp_readiness["can_select_field"]
        assert "btn disabled" in page(temp_root)
    job = job_status()
    assert "steps" in job
    assert "current_step" in job
    assert "Шаг: RUNNING" in format_job_steps([{"label": "Шаг", "status": "RUNNING", "message": "Выполняется."}])
    assert COMMAND_TIMEOUT_SECONDS > 0
    old_timeout = webapp.COMMAND_TIMEOUT_SECONDS
    try:
        webapp.COMMAND_TIMEOUT_SECONDS = 0.01
        code, output = webapp.run_command(ROOT, [sys.executable, "-c", "import time; time.sleep(1)"])
        assert code == 124
        assert "timed out" in output
    finally:
        webapp.COMMAND_TIMEOUT_SECONDS = old_timeout
    assert isinstance(find_available_port(start=8765, attempts=2), int)
    qgis = qgis_python(config)
    if qgis:
        assert Path(qgis).exists()
    print("Web app render: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
