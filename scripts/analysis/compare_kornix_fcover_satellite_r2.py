#!/usr/bin/env python3
"""Group SP fields by R² between KORNIX expected and Sentinel-2 FCover."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "results/data/sp_kornix_sentinel_daily.csv"
DEFAULT_OUTPUT = ROOT / "results/tables/sp_kornix_fcover_satellite_r2_by_field.csv"
DEFAULT_REPORT = ROOT / "results/reports/sp_kornix_fcover_satellite_r2.json"
TARGET = "satellite_fcover_expected"
SATELLITE_SERIES = ("FCOVER",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def pearson_r(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    target_mean = sum(target for target, _ in pairs) / len(pairs)
    satellite_mean = sum(value for _, value in pairs) / len(pairs)
    numerator = sum((target - target_mean) * (value - satellite_mean) for target, value in pairs)
    target_sum = sum((target - target_mean) ** 2 for target, _ in pairs)
    satellite_sum = sum((value - satellite_mean) ** 2 for _, value in pairs)
    denominator = math.sqrt(target_sum * satellite_sum)
    return numerator / denominator if denominator else None


def r_squared_group(pearson_r: float | None, r_squared: float | None) -> str:
    if pearson_r is not None and pearson_r > 0 and r_squared is not None and r_squared >= 0.70:
        return "Высокое совпадение (R² >= 0.70)"
    return "Низкое совпадение (R² < 0.70 или обратная связь)"


def summarize(field_id: str, series: str, pairs: list[tuple[float, float]]) -> dict:
    r = pearson_r(pairs)
    r_squared = r * r if r is not None else None
    target_mean = sum(target for target, _ in pairs) / len(pairs)
    satellite_mean = sum(value for _, value in pairs) / len(pairs)
    target_variance = sum((target - target_mean) ** 2 for target, _ in pairs)
    slope = (
        sum((target - target_mean) * (value - satellite_mean) for target, value in pairs) / target_variance
        if target_variance
        else None
    )
    return {
        "field_id": field_id,
        "satellite_series": series,
        "pair_count": len(pairs),
        "pearson_r": r,
        "r_squared": r_squared,
        "r_squared_group": r_squared_group(r, r_squared),
        "mean_kornix_expected_fcover": target_mean,
        "mean_satellite_value": satellite_mean,
        "slope_satellite_per_kornix_fcover": slope,
        "intercept": satellite_mean - slope * target_mean if slope is not None else None,
    }


def compare(rows: list[dict]) -> list[dict]:
    pairs: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        field_id = row.get("sentinel_field_id") or row.get("field_id")
        try:
            target = float(row[TARGET])
        except (KeyError, TypeError, ValueError):
            continue
        if not field_id:
            continue
        for series in SATELLITE_SERIES:
            try:
                satellite_value = float(row[series])
            except (KeyError, TypeError, ValueError):
                continue
            pairs[field_id, series].append((target, satellite_value))
    return [summarize(field_id, series, values) for (field_id, series), values in sorted(pairs.items())]


def make_report(rows: list[dict]) -> dict:
    by_series = {}
    for series in SATELLITE_SERIES:
        series_rows = [row for row in rows if row["satellite_series"] == series]
        usable = [row["r_squared"] for row in series_rows if row["r_squared"] is not None]
        groups = defaultdict(list)
        for row in series_rows:
            groups[row["r_squared_group"]].append(row["field_id"])
        by_series[series] = {
            "field_count": len(series_rows),
            "median_r_squared": statistics.median(usable) if usable else None,
            "mean_r_squared": sum(usable) / len(usable) if usable else None,
            "group_counts": dict(Counter(row["r_squared_group"] for row in series_rows)),
            "fields_by_group": {group: sorted(fields) for group, fields in groups.items()},
        }
    return {"target": TARGET, "comparison": "same field and same Sentinel-2 date", "by_series": by_series}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["field_id", "satellite_series", "r_squared"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    rows = compare([
        {"sentinel_field_id": "SP:1.1", TARGET: "0.1", "FCOVER": "0.2", "NDVI": "0.6"},
        {"sentinel_field_id": "SP:1.1", TARGET: "0.2", "FCOVER": "0.4", "NDVI": "0.4"},
        {"sentinel_field_id": "SP:1.1", TARGET: "0.3", "FCOVER": "0.6", "NDVI": "0.2"},
    ])
    fcover = next(row for row in rows if row["satellite_series"] == "FCOVER")
    assert fcover["r_squared"] == 1.0
    assert fcover["r_squared_group"] == "Высокое совпадение (R² >= 0.70)"
    assert r_squared_group(-1.0, 1.0) == "Низкое совпадение (R² < 0.70 или обратная связь)"


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = compare(list(csv.DictReader(handle)))
    if not rows:
        raise ValueError("No valid KORNIX expected FCover / Sentinel-2 pairs found.")
    write_csv(args.output, rows)
    report = make_report(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Compared {len(rows)} field-series groups: {args.output}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
