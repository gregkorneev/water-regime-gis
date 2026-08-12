#!/usr/bin/env python3
from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "dist" / "water-regime-gis-release"


def main() -> int:
    compose = (RELEASE / "docker-compose.yml").read_text(encoding="utf-8")
    macos = (RELEASE / "Water Regime GIS.command").read_text(encoding="utf-8")
    windows = (RELEASE / "Water Regime GIS.bat").read_text(encoding="utf-8")
    readme = (RELEASE / "README_RU.txt").read_text(encoding="utf-8")
    app = RELEASE / "Water Regime GIS.app"
    executable = app / "Contents/MacOS/water-regime-gis"
    windows_shell = RELEASE / "windows-shell"
    with (app / "Contents/Info.plist").open("rb") as file:
        plist = plistlib.load(file)
    assert "image: water-regime-gis:release" in compose
    assert "./data:/app/data" in compose
    assert "./outputs:/app/outputs" in compose
    assert 'open "$APP_DIR/Water Regime GIS.app"' in macos
    assert "open http://127.0.0.1:8765" not in macos
    assert "dotnet run --project windows-shell\\WaterRegimeGIS.csproj" in windows
    assert "start http://127.0.0.1:8765" not in windows
    assert "QGIS находится внутри Docker-образа" in readme
    assert "desktop-окне, а не в системном браузере" in readme
    assert plist["CFBundleExecutable"] == "water-regime-gis"
    assert executable.exists()
    assert (executable.stat().st_mode & 0o111) != 0
    assert b"Mach-O" in executable.read_bytes()[:16] or executable.read_bytes()[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
    assert (windows_shell / "WaterRegimeGIS.csproj").exists()
    assert (windows_shell / "Program.cs").exists()
    assert "Microsoft.Web.WebView2" in (windows_shell / "WaterRegimeGIS.csproj").read_text(encoding="utf-8")
    assert "WebView2" in (windows_shell / "Program.cs").read_text(encoding="utf-8")
    assert (RELEASE / "water-regime-gis-image.tar").stat().st_size > 0
    assert (RELEASE / "configs/project.example.json").exists()
    for name in (
        "data/aoi",
        "data/raw",
        "data/interim",
        "data/processed",
        "outputs/maps",
        "outputs/reports",
        "outputs/rasters",
    ):
        assert (RELEASE / name).is_dir(), name
    print(f"Release package: OK ({RELEASE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
