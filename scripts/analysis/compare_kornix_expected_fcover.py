#!/usr/bin/env python3
"""Compare KORNIX satellite_fcover_expected with same-day Sentinel-2 FCOVER per field."""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "results/data/sp_kornix_sentinel_daily.csv"
DEFAULT_OUTPUT = ROOT / "results/tables/sp_kornix_expected_fcover_by_field.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    expected_mean = sum(expected for expected, _ in pairs) / len(pairs)
    observed_mean = sum(observed for _, observed in pairs) / len(pairs)
    numerator = sum((expected - expected_mean) * (observed - observed_mean) for expected, observed in pairs)
    expected_sum = sum((expected - expected_mean) ** 2 for expected, _ in pairs)
    observed_sum = sum((observed - observed_mean) ** 2 for _, observed in pairs)
    denominator = math.sqrt(expected_sum * observed_sum)
    return numerator / denominator if denominator else None


def agreement_group(pearson_r: float | None, rmse: float) -> str:
    if pearson_r is not None and pearson_r >= 0.9 and rmse <= 0.15:
        return "Высокое"
    if pearson_r is not None and pearson_r >= 0.5 and rmse <= 0.3:
        return "Умеренное"
    return "Слабое"


def summary(field_id: str, pairs: list[tuple[float, float]]) -> dict:
    errors = [observed - expected for expected, observed in pairs]
    pearson_r = correlation(pairs)
    rmse = math.sqrt(sum(error ** 2 for error in errors) / len(errors))
    return {
        "field_id": field_id,
        "pair_count": len(pairs),
        "agreement_group": agreement_group(pearson_r, rmse),
        "pearson_r": pearson_r,
        "mean_expected_fcover": sum(expected for expected, _ in pairs) / len(pairs),
        "mean_sentinel2_fcover": sum(observed for _, observed in pairs) / len(pairs),
        "bias_sentinel2_minus_expected": sum(errors) / len(errors),
        "mae": sum(abs(error) for error in errors) / len(errors),
        "rmse": rmse,
    }


def compare(rows: list[dict]) -> list[dict]:
    pairs_by_field: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        try:
            field_id = row.get("sentinel_field_id") or row["field_id"]
            pairs_by_field[field_id].append((float(row["satellite_fcover_expected"]), float(row["FCOVER"])))
        except (KeyError, TypeError, ValueError):
            continue
    return [summary(field_id, pairs) for field_id, pairs in sorted(pairs_by_field.items())]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["field_id"])
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    row = summary("SP_1_1", [(0.1, 0.2), (0.2, 0.4), (0.3, 0.6)])
    assert row["pair_count"] == 3
    assert round(row["pearson_r"], 6) == 1.0
    assert round(row["bias_sentinel2_minus_expected"], 6) == 0.2
    assert row["agreement_group"] == "Умеренное"


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = compare(list(csv.DictReader(handle)))
    if not rows:
        raise ValueError("No valid satellite_fcover_expected / FCOVER pairs found.")
    write_csv(args.output, rows)
    print(f"Compared {sum(row['pair_count'] for row in rows)} pairs across {len(rows)} fields: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
