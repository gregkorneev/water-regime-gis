#!/usr/bin/env python3
"""Test the stability of the FCover/KORNIX canopy-cover time lag."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MERGED = ROOT / "results/data/sp_kornix_sentinel_daily.csv"
DEFAULT_KORNIX = ROOT / "data/interim/kornix_timeseries/sp_satellite_timeseries_20260401_20260827_v001/sp_all_fields_all_methods_daily.csv"
DEFAULT_REPORT = ROOT / "results/reports/sp_kornix_fcover_lag.json"
DEFAULT_FIELD_REPORT = ROOT / "results/tables/sp_kornix_fcover_field_lags.csv"
METHOD = "ivanov_n4l_meteo_soil"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged-csv", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--kornix-csv", type=Path, default=DEFAULT_KORNIX)
    parser.add_argument("--method", default=METHOD)
    parser.add_argument("--lag-min", type=int, default=-30)
    parser.add_argument("--lag-max", type=int, default=30)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--field-report", type=Path, default=DEFAULT_FIELD_REPORT)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def normalize_field_id(value: str) -> str:
    match = re.fullmatch(r"(?:SP[:_])?([0-9]+)[._]([0-9]+)", value.strip().upper())
    return f"SP_{match.group(1)}_{match.group(2)}" if match else value.strip().upper()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def corr(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    left, right = np.array(pairs, dtype=float).T
    left -= left.mean()
    right -= right.mean()
    denominator = math.sqrt(float(left @ left) * float(right @ right))
    return float(left @ right) / denominator if denominator else None


def observations(merged_rows: list[dict]) -> list[dict]:
    result = []
    for row in merged_rows:
        try:
            value = float(row["FCOVER"])
            day = dt.date.fromisoformat(row["day"])
        except (KeyError, TypeError, ValueError):
            continue
        result.append({"field_id": normalize_field_id(row["field_short_name"]), "day": day, "fcover": value})
    return result


def daily_cover(rows: list[dict], method: str) -> dict[str, dict[dt.date, tuple[float, float]]]:
    result: dict[str, dict[dt.date, tuple[float, float]]] = defaultdict(dict)
    for row in rows:
        if row.get("method_code") != method:
            continue
        try:
            result[normalize_field_id(row["field_short_name"])][dt.date.fromisoformat(row["day"])] = (
                float(row["canopy_cover_fraction_derived"]), float(row["days_after_sowing"])
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result


def paired_by_lag(obs: list[dict], cover: dict[str, dict[dt.date, tuple[float, float]]], lag: int) -> dict[str, list[tuple[float, float, float, float]]]:
    result: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    for row in obs:
        target = cover.get(row["field_id"], {}).get(row["day"] + dt.timedelta(days=lag))
        current = cover.get(row["field_id"], {}).get(row["day"])
        if target is not None and current is not None:
            result[row["field_id"]].append((row["fcover"], target[0], current[1], target[1]))
    return result


def lag_profile(obs, cover, lags: range) -> list[dict]:
    profile = []
    for lag in lags:
        groups = paired_by_lag(obs, cover, lag)
        field_r = {field: corr([(a, b) for a, b, _, _ in pairs]) for field, pairs in groups.items()}
        values = [value for value in field_r.values() if value is not None]
        pairs = [(a, b) for field_pairs in groups.values() for a, b, _, _ in field_pairs]
        profile.append({
            "lag_days": lag,
            "pair_count": len(pairs),
            "field_count": len(values),
            "pooled_r": corr(pairs),
            "median_field_r": float(np.median(values)) if values else None,
            "positive_fields": sum(value > 0 for value in values),
        })
    return profile


def best_lag(profile: list[dict]) -> int:
    return max(profile, key=lambda row: (row["pooled_r"] if row["pooled_r"] is not None else -2, -abs(row["lag_days"]))) ["lag_days"]


def bootstrap_lags(obs, cover, lags: range, count: int, seed: int) -> dict:
    groups = {lag: paired_by_lag(obs, cover, lag) for lag in lags}
    fields = sorted({field for by_field in groups.values() for field in by_field})
    rng = np.random.default_rng(seed)
    selected = []
    for _ in range(count):
        sampled = rng.choice(fields, len(fields), replace=True)
        scores = []
        for lag in lags:
            pairs = [(a, b) for field in sampled for a, b, _, _ in groups[lag].get(field, [])]
            scores.append((corr(pairs) if pairs else -2, lag))
        selected.append(max(scores)[1])
    return {
        "replicates": count,
        "median_lag_days": float(np.median(selected)),
        "ci95_lag_days": [float(np.quantile(selected, 0.025)), float(np.quantile(selected, 0.975))],
        "mode_lag_days": int(max(set(selected), key=selected.count)),
        "lag_frequency": {str(lag): selected.count(lag) for lag in sorted(set(selected))},
    }


def leave_one_field_out(obs, cover, lags: range) -> dict:
    groups_by_lag = {lag: paired_by_lag(obs, cover, lag) for lag in lags}
    fields = sorted({field for groups in groups_by_lag.values() for field in groups})
    rows = []
    for held_out in fields:
        profile = []
        for lag in lags:
            pairs = [(a, b) for field, values in groups_by_lag[lag].items() if field != held_out for a, b, _, _ in values]
            profile.append({"lag_days": lag, "pooled_r": corr(pairs)})
        selected_lag = best_lag(profile)
        training_pairs = [(a, b) for field, values in groups_by_lag[selected_lag].items() if field != held_out for a, b, _, _ in values]
        test_pairs = [(a, b) for a, b, _, _ in groups_by_lag[selected_lag].get(held_out, [])]
        training_zero_pairs = [(a, b) for field, values in groups_by_lag[0].items() if field != held_out for a, b, _, _ in values]
        zero_pairs = [(a, b) for a, b, _, _ in groups_by_lag[0].get(held_out, [])]
        intercept, slope = affine_fit(training_pairs)
        errors = [(a - (intercept + slope * b)) ** 2 for a, b in test_pairs]
        zero_intercept, zero_slope = affine_fit(training_zero_pairs)
        zero_errors = [(a - (zero_intercept + zero_slope * b)) ** 2 for a, b in zero_pairs]
        rows.append({"held_out_field": held_out, "training_best_lag_days": selected_lag, "test_r": corr(test_pairs), "test_r_at_zero": corr(zero_pairs), "test_pair_count": len(test_pairs), "test_rmse_after_training_scale": math.sqrt(sum(errors) / len(errors)) if errors else None, "test_rmse_at_zero_after_training_scale": math.sqrt(sum(zero_errors) / len(zero_errors)) if zero_errors else None})
    lags_selected = [row["training_best_lag_days"] for row in rows]
    test_r = [row["test_r"] for row in rows if row["test_r"] is not None]
    rmse = [row["test_rmse_after_training_scale"] for row in rows if row["test_rmse_after_training_scale"] is not None]
    zero_rmse = [row["test_rmse_at_zero_after_training_scale"] for row in rows if row["test_rmse_at_zero_after_training_scale"] is not None]
    zero_r = [row["test_r_at_zero"] for row in rows if row["test_r_at_zero"] is not None]
    return {"rows": rows, "median_training_best_lag_days": float(np.median(lags_selected)), "lag_range_days": [min(lags_selected), max(lags_selected)], "median_test_r": float(np.median(test_r)), "median_test_r_at_zero": float(np.median(zero_r)), "median_test_rmse_after_training_scale": float(np.median(rmse)), "median_test_rmse_at_zero_after_training_scale": float(np.median(zero_rmse))}


def affine_fit(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """Fit FCover = intercept + slope * Kornix cover without extra dependencies."""
    if len(pairs) < 2:
        return 0.0, 1.0
    target, source = np.array(pairs, dtype=float).T
    design = np.column_stack((np.ones(len(source)), source))
    intercept, slope = np.linalg.lstsq(design, target, rcond=None)[0]
    return float(intercept), float(slope)


def field_lags(obs, cover, lags: range) -> list[dict]:
    result = []
    for field in sorted({row["field_id"] for row in obs}):
        profile = []
        for lag in lags:
            pairs = [(a, b) for a, b, _, _ in paired_by_lag([row for row in obs if row["field_id"] == field], cover, lag).get(field, [])]
            profile.append({"lag_days": lag, "pooled_r": corr(pairs), "pair_count": len(pairs)})
        usable = [row for row in profile if row["pooled_r"] is not None]
        if not usable:
            continue
        best = best_lag(usable)
        zero = next((row for row in usable if row["lag_days"] == 0), {})
        optimum = next(row for row in usable if row["lag_days"] == best)
        result.append({"field_id": field, "optimal_lag_days": best, "optimal_r": optimum["pooled_r"], "r_at_zero": zero.get("pooled_r"), "pair_count": optimum["pair_count"]})
    return result


def residual_correlation(obs, cover, lag: int) -> dict:
    groups = paired_by_lag(obs, cover, lag)
    rows = [(field, *pair) for field, pairs in groups.items() for pair in pairs]
    fields = sorted({row[0] for row in rows})
    if not rows:
        return {"lag_days": lag, "r": None, "pair_count": 0}
    field_matrix = np.array([[row[0] == field for field in fields] for row in rows], dtype=float)
    x = np.array([row[1] for row in rows], dtype=float)
    y = np.array([row[2] for row in rows], dtype=float)
    das_x = np.array([row[3] for row in rows], dtype=float)
    das_y = np.array([row[4] for row in rows], dtype=float)
    design_x = np.column_stack((field_matrix, das_x, das_x ** 2, das_x ** 3))
    design_y = np.column_stack((field_matrix, das_y, das_y ** 2, das_y ** 3))
    x_residual = x - design_x @ np.linalg.lstsq(design_x, x, rcond=None)[0]
    y_residual = y - design_y @ np.linalg.lstsq(design_y, y, rcond=None)[0]
    return {"lag_days": lag, "r": corr(list(zip(x_residual, y_residual))), "pair_count": len(rows), "fields": len(fields)}


def crossing_day(points: list[tuple[dt.date, float]], fraction: float) -> float | None:
    values = [value for _, value in points]
    low, high = min(values), max(values)
    threshold = low + fraction * (high - low)
    for (day0, value0), (day1, value1) in zip(points, points[1:]):
        if value0 <= threshold <= value1 and value1 > value0:
            return day0.toordinal() + (threshold - value0) / (value1 - value0) * (day1 - day0).days
    return None


def max_growth_day(points: list[tuple[dt.date, float]]) -> float | None:
    slopes = [((value1 - value0) / (day1 - day0).days, (day0.toordinal() + day1.toordinal()) / 2) for (day0, value0), (day1, value1) in zip(points, points[1:]) if day1 > day0]
    return max(slopes)[1] if slopes else None


def phenology(obs, cover) -> dict:
    by_field = defaultdict(list)
    for row in obs:
        by_field[row["field_id"]].append((row["day"], row["fcover"]))
    differences = defaultdict(list)
    usable = 0
    for field, fcover_points in by_field.items():
        fcover_points.sort()
        kornix_points = sorted((day, value[0]) for day, value in cover.get(field, {}).items() if fcover_points[0][0] <= day <= fcover_points[-1][0])
        if len(fcover_points) < 5 or len(kornix_points) < 5 or max(value for _, value in fcover_points) - min(value for _, value in fcover_points) < 0.05:
            continue
        usable += 1
        for label, fn in (("p20", lambda points: crossing_day(points, .2)), ("p50", lambda points: crossing_day(points, .5)), ("p80", lambda points: crossing_day(points, .8)), ("max_growth", max_growth_day)):
            left, right = fn(fcover_points), fn(kornix_points)
            if left is not None and right is not None:
                differences[label].append(left - right)
    return {"usable_fields": usable, "lag_days_fcover_minus_kornix": {label: {"count": len(values), "median": float(np.median(values)), "p25": float(np.quantile(values, .25)), "p75": float(np.quantile(values, .75))} for label, values in differences.items()}}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    assert normalize_field_id("SP:1.1") == "SP_1_1"
    assert round(corr([(1, 1), (2, 2), (3, 3)]), 6) == 1.0
    assert np.allclose(affine_fit([(1, 0), (3, 1)]), (1.0, 2.0))
    assert crossing_day([(dt.date(2026, 1, 1), 0), (dt.date(2026, 1, 11), 1)], .5) == dt.date(2026, 1, 6).toordinal()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    if args.lag_max < args.lag_min:
        raise ValueError("--lag-max must be at least --lag-min")
    obs = observations(read_csv(args.merged_csv))
    cover = daily_cover(read_csv(args.kornix_csv), args.method)
    lags = range(args.lag_min, args.lag_max + 1)
    profile = lag_profile(obs, cover, lags)
    optimum = best_lag(profile)
    fields = field_lags(obs, cover, lags)
    report = {
        "method_code": args.method,
        "sign_convention": "lag=-12 means FCover(t) is compared with Kornix canopy cover(t-12), equivalent to shifting the Kornix curve 12 days right.",
        "observations": len(obs),
        "fields": len({row['field_id'] for row in obs}),
        "lag_profile": profile,
        "best_lag_days": optimum,
        "bootstrap_fields": bootstrap_lags(obs, cover, lags, args.bootstrap, args.seed),
        "field_optima": {"median_lag_days": float(np.median([row['optimal_lag_days'] for row in fields])), "lag_counts": {str(lag): sum(row['optimal_lag_days'] == lag for row in fields) for lag in sorted({row['optimal_lag_days'] for row in fields})}},
        "leave_one_field_out": leave_one_field_out(obs, cover, lags),
        "phenology": phenology(obs, cover),
        "residual_after_field_and_cubic_das": {"at_zero": residual_correlation(obs, cover, 0), "at_best_lag": residual_correlation(obs, cover, optimum)},
    }
    write_csv(args.field_report, fields)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    best = next(row for row in profile if row["lag_days"] == optimum)
    print(f"Best lag: {optimum:+d} days; pooled r={best['pooled_r']:.3f}; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
