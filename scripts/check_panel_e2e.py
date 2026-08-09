#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
URL_RE = re.compile(r"water-regime-gis app: (http://127\.0\.0\.1:\d+)")


def main() -> int:
    env = os.environ.copy()
    env["WATER_REGIME_GIS_NO_BROWSER"] = "1"
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
        for path in ("/download/preview.png", "/download/field.geojson", "/download/report.json"):
            with urlopen(url + path, timeout=20) as response:
                assert response.status == 200
                assert response.read(1)
        print("panel e2e: OK")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


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
