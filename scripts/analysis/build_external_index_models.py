#!/usr/bin/env python3
"""Fit simple, auditable relationships between external series and Sentinel-2 indices."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build per-variable linear models against Sentinel indices.")
    parser.add_argument("--series-state", type=Path, required=True)
    parser.add_argument("--indices", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "results/tables/external_index_models.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = json.loads(args.series_state.read_text(encoding="utf-8"))
    series = external_rows([Path(path) for path in state["csv_files"]])
    indices = index_rows(args.indices)
    records = fit_models(series, indices)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("variable", "index", "pairs", "slope", "intercept", "pearson_r", "r_squared"))
        writer.writeheader()
        writer.writerows(records)
    print(f"Models: {len(records)}; output: {args.output}")
    return 0


def external_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                field_id = row.get("field_id") or row.get("field_external_key")
                date = row.get("day") or row.get("date")
                if field_id and date:
                    rows.append({**row, "field_id": str(field_id), "date": date[:10]})
    return rows


def index_rows(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    result = defaultdict(dict)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                result[(row["field_id"], row["scene_date"])][row["index"]] = float(row["zonal_mean"])
            except (KeyError, TypeError, ValueError):
                pass
    return result


def fit_models(series: list[dict], indices: dict[tuple[str, str], dict[str, float]]) -> list[dict]:
    pairs = defaultdict(list)
    for row in series:
        satellite = indices.get((row["field_id"], row["date"]), {})
        for variable, value in row.items():
            if variable in {"field_id", "field_external_key", "day", "date"}:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            for index, index_value in satellite.items():
                pairs[(variable, index)].append((number, index_value))
    records = []
    for (variable, index), values in sorted(pairs.items()):
        if len(values) < 3:
            continue
        x, y = zip(*values)
        mean_x, mean_y = sum(x) / len(x), sum(y) / len(y)
        covariance = sum((left - mean_x) * (right - mean_y) for left, right in zip(x, y))
        variance_x = sum((value - mean_x) ** 2 for value in x)
        variance_y = sum((value - mean_y) ** 2 for value in y)
        if not variance_x or not variance_y:
            continue
        slope = covariance / variance_x
        intercept = mean_y - slope * mean_x
        r = covariance / (variance_x * variance_y) ** 0.5
        records.append({
            "variable": variable, "index": index, "pairs": len(values),
            "slope": float(slope), "intercept": float(intercept),
            "pearson_r": r, "r_squared": r * r,
        })
    return records


if __name__ == "__main__":
    raise SystemExit(main())
