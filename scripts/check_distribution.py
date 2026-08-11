#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    launcher = (ROOT / "launch_panel.bat").read_text(encoding="utf-8")

    assert "qgis/qgis:3.44-noble" in dockerfile
    assert "WATER_REGIME_GIS_HOST=0.0.0.0" in dockerfile
    assert 'CMD ["python3", "scripts/run_app.py"]' in dockerfile
    assert "platform: linux/amd64" in compose
    assert "8765:8765" in compose
    assert "./data:/app/data" in compose
    assert "./outputs:/app/outputs" in compose
    assert "outputs/rasters/*" in dockerignore
    assert ".git" in dockerignore
    assert "python scripts\\run_app.py" in launcher
    print("Distribution config: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
