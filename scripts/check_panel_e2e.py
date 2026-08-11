#!/usr/bin/env python3
from __future__ import annotations

import json
import io
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
URL_RE = re.compile(r"water-regime-gis app: (http://127\.0\.0\.1:\d+)")


def main() -> int:
    config = json.loads((ROOT / "configs/project.example.json").read_text(encoding="utf-8"))
    paths = snapshot_paths(config)
    env = os.environ.copy()
    env["WATER_REGIME_GIS_NO_BROWSER"] = "1"
    with tempfile.TemporaryDirectory(prefix="water-regime-gis-e2e-") as tmp:
        backup = backup_paths(paths, Path(tmp))
        process = subprocess.Popen(
            [sys.executable, "scripts/run_app.py"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            url = read_url(process)
            get_json(url, "/readiness.json")
            start_job(url, "/job/start?kind=repair-environment")
            start_job(url, "/job/start?kind=select-field&lon=38.1361306&lat=53.8413983")
            start_job(url, "/job/start?kind=prepare-result")
            for path in ("/download/preview.png", "/download/field.geojson", "/download/report.json", "/download/result.zip"):
                with urlopen(url + path, timeout=20) as response:
                    assert response.status == 200
                    body = response.read()
                    assert body
                    if path.endswith(".zip"):
                        names = set(zipfile.ZipFile(io.BytesIO(body)).namelist())
                        assert "water_regime_gis_preview.png" in names
                        assert "selected_field_area.geojson" in names
                        assert "latest_result.json" in names
                        assert any(name.startswith("rasters/") and name.endswith(".tif") for name in names)
            report = get_json(url, "/result.json")
            assert report["satellite"]["satellite_status"] in {"OK", "no_scene_found", "no_indices"}
            if report["satellite"]["satellite_status"] == "OK":
                ok_indices = {item["name"] for item in report["satellite"]["indices"] if item["status"] == "OK"}
                assert {"NDVI", "NDMI", "NDWI"}.issubset(ok_indices)
            print("panel e2e: OK")
            return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            restore_paths(backup)


def snapshot_paths(config: dict) -> list[Path]:
    return [
        ROOT / config["paths"]["selected_field_point"],
        ROOT / config["paths"]["selected_field_area"],
        ROOT / config["paths"]["latest_report"],
        ROOT / "outputs/maps/water_regime_gis_preview.png",
        ROOT / "outputs/maps/water_regime_gis.qgs",
        ROOT / "data/interim/satellite/latest_scene.json",
        ROOT / "outputs/rasters/ndvi.tif",
        ROOT / "outputs/rasters/ndmi.tif",
        ROOT / "outputs/rasters/ndwi.tif",
        ROOT / "outputs/rasters/mndwi.tif",
        ROOT / "outputs/rasters/savi.tif",
        ROOT / "outputs/rasters/ndre.tif",
    ]


def backup_paths(paths: list[Path], backup_dir: Path) -> dict[Path, Optional[Path]]:
    backup: dict[Path, Optional[Path]] = {}
    for index, path in enumerate(paths):
        if path.exists():
            copy = backup_dir / f"{index}-{path.name}"
            shutil.copy2(path, copy)
            backup[path] = copy
        else:
            backup[path] = None
    return backup


def restore_paths(backup: dict[Path, Optional[Path]]) -> None:
    for path, copy in backup.items():
        if copy is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(copy, path)


def read_url(process: subprocess.Popen) -> str:
    assert process.stdout is not None
    deadline = time.time() + 20
    while time.time() < deadline:
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                break
            continue
        match = URL_RE.search(line)
        if match:
            return match.group(1)
    raise RuntimeError("Panel URL was not printed.")


def get_json(url: str, path: str) -> dict:
    with urlopen(url + path, timeout=20) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def start_job(url: str, path: str) -> dict:
    payload = get_json(url, path)
    assert payload.get("started"), payload
    return wait_job(url)


def wait_job(url: str) -> dict:
    deadline = time.time() + 240
    while time.time() < deadline:
        payload = get_json(url, "/job/status")
        if not payload.get("running"):
            assert payload.get("status") == "OK", payload
            return payload
        time.sleep(1)
    raise TimeoutError("Panel job did not finish.")


if __name__ == "__main__":
    raise SystemExit(main())
