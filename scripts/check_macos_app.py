#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "dist/Water Regime GIS.app"
INFO = APP_DIR / "Contents/Info.plist"
EXECUTABLE = APP_DIR / "Contents/MacOS/water-regime-gis"


def main() -> int:
    subprocess.run([sys.executable, "scripts/build_macos_app.py"], cwd=ROOT, check=True)
    assert INFO.exists()
    assert EXECUTABLE.exists()
    plist = plistlib.loads(INFO.read_bytes())
    assert plist["CFBundleName"] == "Water Regime GIS"
    assert plist["CFBundleExecutable"] == EXECUTABLE.name
    mode = EXECUTABLE.stat().st_mode
    assert mode & stat.S_IXUSR
    script = EXECUTABLE.read_text(encoding="utf-8")
    assert "python3 scripts/run_app.py" in script
    assert "PROJECT_DIR" in script
    print("macOS app bundle: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
