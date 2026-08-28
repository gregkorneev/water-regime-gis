#!/usr/bin/env python3
"""Join daily SP KORNIX rows with same-day Sentinel-2 field indices."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KORNIX = ROOT / "data/interim/kornix_timeseries/sp_satellite_timeseries_20260401_20260827_v001/sp_all_fields_all_methods_daily.csv"
DEFAULT_SENTINEL = ROOT / "outputs/reports/field_zonal_means.csv"
DEFAULT_OUTPUT = ROOT / "results/data/sp_kornix_sentinel_daily.csv"
DEFAULT_REPORT = ROOT / "results/reports/sp_kornix_sentinel_merge.json"
INDICES = ("NDVI", "NDMI", "NDRE", "SAVI")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Join SP KORNIX daily rows with same-day Sentinel-2 indices.")
    parser.add_argument("--kornix-csv", type=Path, default=DEFAULT_KORNIX)
    parser.add_argument("--sentinel-csv", type=Path, default=DEFAULT_SENTINEL)
    parser.add_argument("--method", default="ivanov_n4l_meteo_soil")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def normalize_field_id(value: str) -> str:
    value = value.strip().upper()
    match = re.fullmatch(r"SP[:_]([0-9]+)[._]([0-9]+)", value)
    return f"SP:{match.group(1)}.{match.group(2)}" if match else value


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def merge(kornix_rows: list[dict], sentinel_rows: list[dict], method: str) -> tuple[list[dict], dict]:
    satellite: dict[tuple[str, str], dict] = defaultdict(dict)
    satellite_fields = set()
    for row in sentinel_rows:
        index, value = (row.get("index") or "").upper(), (row.get("zonal_mean") or "").strip()
        field_id, day = normalize_field_id(row.get("field_id") or ""), (row.get("scene_date") or "").strip()
        if index in INDICES and value and field_id and day:
            satellite[field_id, day][index] = value
            satellite_fields.add(field_id)

    result, kornix_fields = [], set()
    for row in kornix_rows:
        if row.get("method_code") != method:
            continue
        field_id, day = normalize_field_id(row.get("field_short_name") or ""), (row.get("day") or "").strip()
        kornix_fields.add(field_id)
        indices = satellite.get((field_id, day))
        if indices:
            result.append({**row, "sentinel_field_id": field_id, "sentinel_scene_date": day, **{name: indices.get(name, "") for name in INDICES}})

    report = {
        "method_code": method,
        "kornix_rows_for_method": sum(row.get("method_code") == method for row in kornix_rows),
        "satellite_field_date_rows": len(satellite),
        "matched_rows": len(result),
        "kornix_fields_without_satellite": sorted(kornix_fields - satellite_fields),
        "satellite_fields_without_kornix": sorted(satellite_fields - kornix_fields),
    }
    return result, report


def self_test() -> None:
    assert normalize_field_id("sp_1_11") == "SP:1.11"
    rows, report = merge(
        [{"field_short_name": "SP:1.1", "day": "2026-04-01", "method_code": "m"}],
        [{"field_id": "SP_1_1", "scene_date": "2026-04-01", "index": "NDVI", "zonal_mean": "0.4"}],
        "m",
    )
    assert rows[0]["NDVI"] == "0.4" and report["matched_rows"] == 1


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    rows, report = merge(read_csv(args.kornix_csv), read_csv(args.sentinel_csv), args.method)
    fields = list(rows[0]) if rows else ["field_short_name", "day", "method_code", "sentinel_field_id", "sentinel_scene_date", *INDICES]
    write_csv(args.output, rows, fields)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Matched rows: {report['matched_rows']}; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
