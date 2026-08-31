#!/usr/bin/env python3
"""Rebuild every QGIS-visible Sentinel-1/Sentinel-2 experiment figure."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "scripts/analysis/run_s1_s2_surface_validation.py"


def commands() -> list[list[str]]:
    common = [str(sys.executable), str(VALIDATION)]
    return [
        common,
        [*common, "--s1-index", "vh", "--data-output", "results/data/sp_s1_s2_surface_validation_65_vh.csv", "--predictions-output", "results/data/sp_s1_s2_surface_validation_predictions_65_vh.csv", "--report", "results/reports/sp_s1_s2_surface_validation_65_vh.json", "--field-output", "results/tables/sp_s1_s2_surface_validation_by_field_65_vh.csv", "--figure", "results/figures/sp_s1_s2_surface_validation_65_vh.png"],
        [*common, "--variant", "90", "--data-output", "results/data/sp_s1_s2_surface_validation_90.csv", "--predictions-output", "results/data/sp_s1_s2_surface_validation_predictions_90.csv", "--report", "results/reports/sp_s1_s2_surface_validation_90.json", "--field-output", "results/tables/sp_s1_s2_surface_validation_by_field_90.csv", "--figure", "results/figures/sp_s1_s2_surface_validation_90.png"],
        [*common, "--min-fcover-r2", "0.7", "--data-output", "results/data/sp_s1_s2_surface_validation_65_fcover_r2_070.csv", "--predictions-output", "results/data/sp_s1_s2_surface_validation_predictions_65_fcover_r2_070.csv", "--report", "results/reports/sp_s1_s2_surface_validation_65_fcover_r2_070.json", "--field-output", "results/tables/sp_s1_s2_surface_validation_by_field_65_fcover_r2_070.csv", "--figure", "results/figures/sp_s1_s2_surface_validation_65_fcover_r2_070.png"],
    ]


def main() -> int:
    if "--self-test" in sys.argv:
        assert len(commands()) == 4
        assert all(command[1] == str(VALIDATION) for command in commands())
        print("Self-test OK")
        return 0
    for index, command in enumerate(commands(), start=1):
        print(f"PROGRESS {(index - 1) * 25}")
        subprocess.run(command, cwd=ROOT, check=True)
    print("PROGRESS 100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
