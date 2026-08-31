#!/usr/bin/env python3
"""Rebuild every QGIS-visible Sentinel-1/Sentinel-2 experiment figure."""
from __future__ import annotations

import subprocess
import sys
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "scripts/analysis/run_s1_s2_surface_validation.py"
FCOVER_PROTOCOL = ROOT / "scripts/analysis/analyze_kornix_fcover_lag.py"
SUMMARY = ROOT / "results/reports/sp_s1_s2_surface_validation_summary.json"


def write_summary() -> None:
    """Collect the four QGIS-visible reports into one stable JSON result."""
    variants = (
        ("vv_65", "VV, междурядье 65 см", "sp_s1_s2_surface_validation_65.json"),
        ("vh_65", "VH, междурядье 65 см", "sp_s1_s2_surface_validation_65_vh.json"),
        ("vv_90", "VV, междурядье 90 см", "sp_s1_s2_surface_validation_90.json"),
        ("vv_65_fcover_r2_070", "VV, 65 см, FCOVER R² ≥ 0,70", "sp_s1_s2_surface_validation_65_fcover_r2_070.json"),
    )
    reports = []
    for identifier, label, filename in variants:
        path = SUMMARY.parent / filename
        report = json.loads(path.read_text(encoding="utf-8"))
        reports.append({
            "id": identifier,
            "label": label,
            "source_report": str(path.relative_to(ROOT)),
            "fields": report["fields"],
            "s1_index": report["s1_index"],
            "row_spacing_variant": report["row_spacing_variant"],
            "models": report["models"],
            "robust_huber": {
                name: report["robust_huber"][name]["all_points"]
                for name in ("M1", "M2", "M3")
            },
            "bootstrap_huber": report["bootstrap_huber"],
            "sensitivity": {
                "rule": report["same_day_water_rule"],
                "m3_without_same_day_water": report["robust_huber"]["M3"]["without_same_day_water"],
            },
        })
    SUMMARY.write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Итог кнопки QGIS «Диаграммы эксперимента»; все метрики — только для отложенных полей.",
        "excluded_fields": ["SP_7_3"],
        "variants": reports,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def commands() -> list[list[str]]:
    common = [str(sys.executable), str(VALIDATION)]
    return [
        common,
        [*common, "--s1-index", "vh", "--data-output", "results/data/sp_s1_s2_surface_validation_65_vh.csv", "--predictions-output", "results/data/sp_s1_s2_surface_validation_predictions_65_vh.csv", "--report", "results/reports/sp_s1_s2_surface_validation_65_vh.json", "--field-output", "results/tables/sp_s1_s2_surface_validation_by_field_65_vh.csv", "--figure", "results/figures/sp_s1_s2_surface_validation_65_vh.png"],
        [*common, "--variant", "90", "--data-output", "results/data/sp_s1_s2_surface_validation_90.csv", "--predictions-output", "results/data/sp_s1_s2_surface_validation_predictions_90.csv", "--report", "results/reports/sp_s1_s2_surface_validation_90.json", "--field-output", "results/tables/sp_s1_s2_surface_validation_by_field_90.csv", "--figure", "results/figures/sp_s1_s2_surface_validation_90.png"],
        [*common, "--min-fcover-r2", "0.7", "--data-output", "results/data/sp_s1_s2_surface_validation_65_fcover_r2_070.csv", "--predictions-output", "results/data/sp_s1_s2_surface_validation_predictions_65_fcover_r2_070.csv", "--report", "results/reports/sp_s1_s2_surface_validation_65_fcover_r2_070.json", "--field-output", "results/tables/sp_s1_s2_surface_validation_by_field_65_fcover_r2_070.csv", "--figure", "results/figures/sp_s1_s2_surface_validation_65_fcover_r2_070.png"],
        [str(sys.executable), str(FCOVER_PROTOCOL), "--variant", "90", "--report", "results/reports/sp_kornix_fcover_lag_90.json", "--field-report", "results/tables/sp_kornix_fcover_field_lags_90.csv", "--warp-report", "results/tables/sp_kornix_fcover_piecewise_warp_90.csv", "--protocol-report", "results/reports/sp_kornix_fcover_series_protocol_90.json"],
    ]


def main() -> int:
    if "--self-test" in sys.argv:
        assert len(commands()) == 5
        assert all(command[1] == str(VALIDATION) for command in commands()[:4])
        assert commands()[-1][1] == str(FCOVER_PROTOCOL)
        assert SUMMARY.name == "sp_s1_s2_surface_validation_summary.json"
        print("Self-test OK")
        return 0
    all_commands = commands()
    for index, command in enumerate(all_commands, start=1):
        print(f"PROGRESS {(index - 1) * 100 // len(all_commands)}")
        subprocess.run(command, cwd=ROOT, check=True)
    write_summary()
    print(f"SUMMARY_JSON {SUMMARY}")
    print("PROGRESS 100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
