#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import json
import os
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
    nspd_plugin_metadata,
    system_status,
)
from water_regime_gis.qgis_runtime import qgis_install_hint


def main() -> int:
    html = page(ROOT)
    assert "water-regime-gis" in html
    assert "EPSG:32637" in html
    assert "NDVI" in html
    assert "Выбор поля" in html
    assert "Сохранить выбранное поле" in html
    assert "Подготовить результат" in html
    assert "Проверить систему" in html
    assert "Восстановить среду" in html
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
    assert 'data-job="repair-environment"' in html
    assert 'kind: "select-field"' in html
    assert "/nspd/wms" in html
    assert "World_Imagery" in html
    assert "World_Boundaries_and_Places" in html
    assert "L.control.layers" in html
    assert "Кадастровый слой" in html
    assert "/satellite-overlay.json" in html
    assert "Последний Sentinel-2" in html
    assert "/selected-field-area.geojson" in html
    assert "/download/rasters/" in html or "Спутниковые индексы" in html
    if "Результаты" in html:
        assert "/download/result.zip" in html
    assert (ROOT / "launch_panel.command").exists()
    assert (ROOT / "scripts/build_macos_app.py").exists()
    assert (ROOT / "scripts/check_macos_app.py").exists()
    assert (ROOT / "scripts/check_panel_e2e.py").exists()
    assert (ROOT / "scripts/check_docker_app.py").exists()
    assert (ROOT / "scripts/check_distribution.py").exists()
    assert (ROOT / "scripts/check_satellite_pipeline.py").exists()
    assert (ROOT / "scripts/qgis/process_satellite_indices.py").exists()
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / "launch_panel.bat").exists()
    assert (ROOT / "launch_docker.command").exists()
    assert (ROOT / "launch_docker.bat").exists()
    config = load_config(ROOT)
    status = system_status(ROOT, config)
    assert "steps" in status
    assert status["steps"]
    environment = environment_status(ROOT, config)
    assert environment["runtime"]["mode"] in {"local", "docker"}
    assert "Режим запуска" in html
    assert "qgis" in environment
    assert environment["qgis"]["download_url"] == QGIS_DOWNLOAD_URL
    assert "nspd_plugin" in environment
    assert "version" in environment["nspd_plugin"]
    assert "artifacts" in environment
    assert "rasters" in environment["artifacts"]
    assert config["satellite"]["provider"] == "planetary-computer-stac"
    assert config["satellite"]["collection"] == "sentinel-2-l2a"
    assert config["qgis"]["satellite_indices_script"] == "scripts/qgis/process_satellite_indices.py"
    readiness = readiness_status(ROOT, config)
    assert "can_select_field" in readiness
    assert "can_prepare_result" in readiness
    assert "reasons" in readiness
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        (temp_root / "configs").mkdir()
        temp_config = json.loads((ROOT / "configs/project.example.json").read_text(encoding="utf-8"))
        (temp_root / "configs/project.example.json").write_text(json.dumps(temp_config), encoding="utf-8")
        temp_readiness = readiness_status(temp_root, load_config(temp_root))
        assert not temp_readiness["can_prepare_result"]
        assert "Сначала выберите точку поля" in temp_readiness["reasons"]["prepare_result"] or not temp_readiness["can_select_field"]
        assert "btn disabled" in page(temp_root)
        temp_config["qgis"]["python_executable"] = "/tmp/water-regime-gis-missing-qgis-python"
        (temp_root / "configs/project.example.json").write_text(json.dumps(temp_config), encoding="utf-8")
        missing_qgis = load_config(temp_root)
        assert qgis_python(missing_qgis) == ""
        missing_environment = environment_status(temp_root, missing_qgis)
        assert not missing_environment["qgis"]["found"]
        assert missing_environment["qgis"]["download_url"] == QGIS_DOWNLOAD_URL
        assert missing_environment["qgis"]["install_hint"] == qgis_install_hint()
        assert not readiness_status(temp_root, missing_qgis)["can_select_field"]
        assert "Скачать QGIS" in page(temp_root)
        old_runtime = os.environ.get("WATER_REGIME_GIS_RUNTIME")
        try:
            os.environ["WATER_REGIME_GIS_RUNTIME"] = "docker"
            docker_environment = environment_status(temp_root, missing_qgis)
            assert docker_environment["runtime"]["mode"] == "docker"
            assert "Docker-контейнер" in page(temp_root)
        finally:
            if old_runtime is None:
                os.environ.pop("WATER_REGIME_GIS_RUNTIME", None)
            else:
                os.environ["WATER_REGIME_GIS_RUNTIME"] = old_runtime
        assert "/Applications/QGIS.app" in qgis_install_hint("Darwin")
        assert "OSGeo4W" in qgis_install_hint("Windows")
        assert "Docker" in qgis_install_hint("Linux")
        plugin_dir = temp_root / "plugin"
        plugin_dir.mkdir()
        assert not nspd_plugin_metadata(plugin_dir)["valid"]
        (plugin_dir / "metadata.txt").write_text("[general]\nname=test\nversion=1.2\n", encoding="utf-8")
        assert nspd_plugin_metadata(plugin_dir)["valid"]
        assert not nspd_plugin_metadata(plugin_dir, "other-plugin")["valid"]
        assert nspd_plugin_metadata(plugin_dir, "test")["valid"]
        assert nspd_plugin_metadata(plugin_dir)["version"] == "1.2"
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
