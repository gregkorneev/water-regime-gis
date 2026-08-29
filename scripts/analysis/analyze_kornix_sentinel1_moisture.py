#!/usr/bin/env python3
"""Measure the Sentinel-1/KORNIX moisture relationship after water inputs."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KORNIX = ROOT / "data/interim/kornix_timeseries/sp_satellite_timeseries_20260401_20260827_v001/sp_all_fields_all_methods_daily.csv"
DEFAULT_RADAR = ROOT / "outputs/reports/sentinel1_zonal_means.csv"
DEFAULT_OUTPUT = ROOT / "results/data/sp_kornix_sentinel1_moisture.csv"
DEFAULT_REPORT = ROOT / "results/reports/sp_kornix_sentinel1_moisture.json"
METHOD = "ivanov_n4l_meteo_soil"
MOISTURE = "soil_surface_0_10_theta"
WATER_COLUMNS = ("precipitation_raw_daily_mm", "irrigation_raw_daily_mm")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kornix-csv", type=Path, default=DEFAULT_KORNIX)
    parser.add_argument("--radar-csv", type=Path, default=DEFAULT_RADAR)
    parser.add_argument("--method", default=METHOD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def normalize_field_id(value: str) -> str:
    match = re.fullmatch(r"(?:SP[:_])?([0-9]+)[._]([0-9]+)", value.strip().upper())
    return f"SP_{match.group(1)}_{match.group(2)}" if match else value.strip().upper()


def number(value: str | None) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def water_sum(daily: dict[date, float], day: date, days: int) -> float:
    return sum(daily.get(day - timedelta(offset), 0.0) for offset in range(days))


def matched_rows(kornix_rows: list[dict], radar_rows: list[dict], method: str) -> list[dict]:
    daily, moisture = defaultdict(dict), {}
    for row in kornix_rows:
        if row.get("method_code") != method:
            continue
        field_id, day = normalize_field_id(row.get("field_short_name", "")), date.fromisoformat(row["day"])
        daily[field_id, "precipitation"][day] = number(row.get(WATER_COLUMNS[0]))
        daily[field_id, "irrigation"][day] = number(row.get(WATER_COLUMNS[1]))
        moisture[field_id, day] = number(row.get(MOISTURE))

    radar = defaultdict(dict)
    for row in radar_rows:
        if row.get("dataset") != "sp" or not row.get("zonal_mean_db"):
            continue
        polarization = row.get("polarization", "").upper()
        if polarization in {"VV", "VH"}:
            radar[normalize_field_id(row["field_id"]), date.fromisoformat(row["scene_date"])][polarization] = number(row["zonal_mean_db"])

    rows = []
    for (field_id, day), values in sorted(radar.items()):
        if (field_id, day) not in moisture or {"VV", "VH"} - values.keys():
            continue
        precipitation = daily[field_id, "precipitation"]
        irrigation = daily[field_id, "irrigation"]
        rows.append({
            "field_id": field_id,
            "day": day.isoformat(),
            "kornix_moisture_0_10": moisture[field_id, day],
            "sentinel1_vv_db": values["VV"],
            "sentinel1_vh_db": values["VH"],
            "precipitation_3d_mm": water_sum(precipitation, day, 3),
            "irrigation_3d_mm": water_sum(irrigation, day, 3),
            "precipitation_7d_mm": water_sum(precipitation, day, 7),
            "irrigation_7d_mm": water_sum(irrigation, day, 7),
        })
    return rows


def within_field(rows: list[dict], column: str) -> np.ndarray:
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["field_id"]].append(index)
    values = np.array([row[column] for row in rows], dtype=float)
    result = values.copy()
    for indices in groups.values():
        result[indices] -= values[indices].mean()
    return result


def fit_model(rows: list[dict], columns: tuple[str, ...]) -> dict:
    target = within_field(rows, "kornix_moisture_0_10")
    predictors = [within_field(rows, column) for column in columns]
    matrix = np.column_stack(predictors)
    coefficients, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    fitted = matrix @ coefficients
    residual = target - fitted
    total = float(target @ target)
    r_squared = 1.0 - float(residual @ residual) / total if total else 0.0
    return {
        "columns": list(columns),
        "r_squared_within_field": r_squared,
        "coefficients": {column: float(coefficient) for column, coefficient in zip(columns, coefficients)},
        "residual": residual,
    }


def residual_after_controls(rows: list[dict], target_column: str, controls: tuple[str, ...]) -> np.ndarray:
    target = within_field(rows, target_column)
    matrix = np.column_stack([within_field(rows, column) for column in controls])
    coefficients, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    return target - matrix @ coefficients


def correlation(first: np.ndarray, second: np.ndarray) -> float:
    denominator = math.sqrt(float(first @ first) * float(second @ second))
    return float(first @ second) / denominator if denominator else 0.0


def analyze(rows: list[dict]) -> dict:
    water = ("precipitation_3d_mm", "irrigation_3d_mm", "precipitation_7d_mm", "irrigation_7d_mm")
    water_model = fit_model(rows, water)
    radar_model = fit_model(rows, water + ("sentinel1_vv_db", "sentinel1_vh_db"))
    pooled_moisture = np.array([row["kornix_moisture_0_10"] for row in rows], dtype=float)
    within_moisture = within_field(rows, "kornix_moisture_0_10")
    correlations = {"pooled": {}, "within_field": {}}
    partial = {}
    for column in ("sentinel1_vv_db", "sentinel1_vh_db"):
        pooled_radar = np.array([row[column] for row in rows], dtype=float)
        correlations["pooled"][column] = correlation(
            pooled_moisture - pooled_moisture.mean(), pooled_radar - pooled_radar.mean()
        )
        correlations["within_field"][column] = correlation(within_moisture, within_field(rows, column))
        partial[column] = correlation(
            residual_after_controls(rows, "kornix_moisture_0_10", water),
            residual_after_controls(rows, column, water),
        )
    return {
        "matched_field_dates": len(rows),
        "fields": len({row["field_id"] for row in rows}),
        "water_only": {key: value for key, value in water_model.items() if key != "residual"},
        "water_plus_radar": {key: value for key, value in radar_model.items() if key != "residual"},
        "radar_r_squared_gain_after_water": radar_model["r_squared_within_field"] - water_model["r_squared_within_field"],
        "pearson_correlation": correlations,
        "partial_correlation_after_water": partial,
        "interpretation": "Связь оценивается внутри каждого поля после учета суммы осадков и полива за 3 и 7 суток; это наблюдательная, а не причинная оценка.",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    assert normalize_field_id("SP:1.1") == "SP_1_1"
    assert water_sum({date(2026, 4, 2): 2.0, date(2026, 4, 3): 3.0}, date(2026, 4, 3), 3) == 5.0


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    rows = matched_rows(read_csv(args.kornix_csv), read_csv(args.radar_csv), args.method)
    report = analyze(rows)
    write_csv(args.output, rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Matched field-dates: {report['matched_field_dates']}; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
