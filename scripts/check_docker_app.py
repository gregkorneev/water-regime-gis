#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "water-regime-gis:docker-check"
CONTAINER = "water-regime-gis-docker-check"


def main() -> int:
    port = find_available_port()
    run(["docker", "build", "--platform", "linux/amd64", "-t", IMAGE, "."])
    run(["docker", "rm", "-f", CONTAINER], check=False, quiet=True)
    run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--platform",
            "linux/amd64",
            "--name",
            CONTAINER,
            "-p",
            f"{port}:8765",
            "-e",
            "WATER_REGIME_GIS_HOST=0.0.0.0",
            "-e",
            "WATER_REGIME_GIS_NO_BROWSER=1",
            "-v",
            f"{ROOT / 'data'}:/app/data",
            "-v",
            f"{ROOT / 'outputs'}:/app/outputs",
            "-v",
            f"{ROOT / 'configs'}:/app/configs:ro",
            IMAGE,
        ],
        quiet=True,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        status = wait_bootstrap(url)
        environment = wait_json(url, "/environment.json")
        readiness = wait_json(url, "/readiness.json")
        version = environment["qgis"]["version"]
        assert all(step["status"] == "OK" for step in status["steps"]), status
        assert environment["qgis"]["found"], environment
        assert qgis_version_tuple(version) >= (3, 40), version
        assert environment["nspd_plugin"]["found"], environment
        assert readiness["can_check_system"], readiness
        print(f"Docker app: OK ({version}, NSPD {environment['nspd_plugin']['version']}, {url})")
        return 0
    finally:
        run(["docker", "rm", "-f", CONTAINER], check=False, quiet=True)


def run(command: list[str], check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    output = subprocess.DEVNULL if quiet else None
    return subprocess.run(command, cwd=ROOT, text=True, stdout=output, stderr=output, check=check)


def find_available_port(start: int = 8766, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port found from {start} to {start + attempts - 1}.")


def wait_json(url: str, path: str) -> dict:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urlopen(url + path, timeout=10) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except Exception:
            time.sleep(2)
    raise TimeoutError(f"Docker app did not answer: {url}{path}")


def wait_bootstrap(url: str) -> dict:
    deadline = time.time() + 180
    while time.time() < deadline:
        status = wait_json(url, "/status.json")
        if not status.get("running") and status.get("steps"):
            return status
        time.sleep(2)
    raise TimeoutError("Docker app bootstrap did not finish.")


def qgis_version_tuple(version: str) -> tuple[int, int]:
    number = version.split("-", 1)[0]
    major, minor, *_ = number.split(".")
    return int(major), int(minor)


if __name__ == "__main__":
    raise SystemExit(main())
