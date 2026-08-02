#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import load_config, missing_required_dirs, project_root


def main() -> int:
    root = project_root(ROOT)
    config = load_config(root)
    missing = missing_required_dirs(root)

    print(f"Project: {config['project']['name']}")
    print(f"Stage: {config['project']['stage']}")
    print(f"Root: {root}")
    print(f"Satellite sources: {', '.join(config['satellite']['sources'])}")
    print(f"Indices: {', '.join(config['satellite']['indices'])}")

    if missing:
        print("Missing required directories:")
        for path in missing:
            print(f"- {path}")
        return 1

    print("Required directory structure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
