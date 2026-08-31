#!/usr/bin/env python3
"""Validate modelled 0-10 cm moisture against Sentinel-1 with fixed fCover."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KORNIX = ROOT / "data/interim/kornix_timeseries/sp_all_calculation_timeseries_20260401_20260827_v006/sp_all_fields_all_methods_daily_65_90.csv"
DEFAULT_RADAR = ROOT / "outputs/reports/sentinel1_zonal_means.csv"
DEFAULT_DATA = ROOT / "results/data/sp_s1_s2_surface_validation_65.csv"
DEFAULT_PREDICTIONS = ROOT / "results/data/sp_s1_s2_surface_validation_predictions_65.csv"
DEFAULT_REPORT = ROOT / "results/reports/sp_s1_s2_surface_validation_65.json"
DEFAULT_FCOVER_R2 = ROOT / "results/tables/sp_kornix_fcover_satellite_r2_by_field.csv"
METHOD = "ivanov_n4l_meteo_soil"
EXCLUDED_FIELDS = {"SP_7_3"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kornix-csv", type=Path, default=DEFAULT_KORNIX)
    parser.add_argument("--radar-csv", type=Path, default=DEFAULT_RADAR)
    parser.add_argument("--method", default=METHOD)
    parser.add_argument("--variant", choices=("65", "90"), default="65")
    parser.add_argument("--s1-index", choices=("vv", "vh"), default="vv", help="Основной неизменяемый S1-показатель в dB.")
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--delta-theta-min", type=float, default=0.001, help="Минимальное различимое изменение theta_0_10 для sign-test, м³/м³.")
    parser.add_argument("--fcover-r2-csv", type=Path, default=DEFAULT_FCOVER_R2)
    parser.add_argument("--min-fcover-r2", type=float, help="Sensitivity-анализ только по полям с FCOVER R² не ниже порога.")
    parser.add_argument("--data-output", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--predictions-output", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--field-output", type=Path, default=ROOT / "results/tables/sp_s1_s2_surface_validation_by_field_65.csv")
    parser.add_argument("--figure", type=Path, default=ROOT / "results/figures/sp_s1_s2_surface_validation_65.png")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def normalize_field_id(value: str) -> str:
    match = re.fullmatch(r"(?:SP[:_])?([0-9]+)[._]([0-9]+)", value.strip().upper())
    return f"SP_{match.group(1)}_{match.group(2)}" if match else value.strip().upper()


def number(value: str | None) -> float:
    return float(value) if value not in (None, "") else math.nan


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fcover_fields(path: Path, threshold: float | None) -> set[str] | None:
    if threshold is None:
        return None
    return {
        normalize_field_id(row["field_id"])
        for row in read_csv(path)
        if float(row["pearson_r"]) > 0 and float(row["r_squared"]) >= threshold
    }


def build_rows(kornix_rows: list[dict], radar_rows: list[dict], method: str, variant: str, s1_index: str, allowed_fields: set[str] | None = None) -> list[dict]:
    suffix = f"_{variant}"
    model = {}
    for row in kornix_rows:
        if row.get("method_code") != method:
            continue
        field_id = normalize_field_id(row.get("field_short_name", ""))
        if field_id in EXCLUDED_FIELDS or allowed_fields is not None and field_id not in allowed_fields:
            continue
        try:
            day = date.fromisoformat(row["day"])
            model[field_id, day] = {
                "theta_0_10": number(row.get(f"soil_layer_0_10_theta_m3_m3{suffix}")),
                "fcover_model": number(row.get(f"satellite_fcover_expected{suffix}")),
                "P0": number(row.get(f"precipitation_raw_daily_mm{suffix}")),
                "I0": number(row.get(f"irrigation_raw_daily_mm{suffix}")),
            }
        except (KeyError, ValueError):
            continue

    radar = defaultdict(dict)
    for row in radar_rows:
        if row.get("dataset") != "sp":
            continue
        field_id = normalize_field_id(row.get("field_id", ""))
        if field_id in EXCLUDED_FIELDS or allowed_fields is not None and field_id not in allowed_fields:
            continue
        try:
            day = date.fromisoformat(row["scene_date"])
            polarization = row.get("polarization", "").lower()
            if polarization in {"vv", "vh"}:
                radar[field_id, day][polarization] = number(row.get("zonal_mean_db"))
                radar[field_id, day][f"valid_pixels_{polarization}"] = row.get("valid_pixel_count", "")
        except (ValueError, KeyError):
            continue

    rows = []
    for (field_id, day), values in sorted(radar.items()):
        state = model.get((field_id, day))
        if not state or not all(math.isfinite(state[name]) for name in ("theta_0_10", "fcover_model", "P0", "I0")):
            continue
        index = values.get(s1_index, math.nan)
        if not math.isfinite(index):
            continue
        rows.append({"field_id": field_id, "date": day.isoformat(), "S1_index": index, "theta_0_10": state["theta_0_10"], "fcover_model": state["fcover_model"], "P0": state["P0"], "I0": state["I0"], "vv_db": values.get("vv", math.nan), "vh_db": values.get("vh", math.nan), "valid_pixels": values.get(f"valid_pixels_{s1_index}", "")})
    return rows


def field_folds(rows: list[dict], folds: int) -> list[list[str]]:
    fields = sorted({row["field_id"] for row in rows})
    if len(fields) == 36 and folds != 6:
        raise ValueError("The confirmatory experiment uses exactly six field folds.")
    if len(fields) == 36:
        return [fields[index::folds] for index in range(folds)]
    if len(fields) < folds:
        raise ValueError(f"Need at least {folds} fields, got {len(fields)}")
    if len(fields) > 36:
        raise ValueError(f"Expected 36 fields after exclusion, got {len(fields)}")
    return [fields[index::folds] for index in range(folds)]


def design(rows: list[dict], model: str) -> np.ndarray:
    theta = np.array([row["theta_0_10"] for row in rows])
    cover = np.array([row["fcover_model"] for row in rows])
    if model == "M1":
        return np.column_stack((np.ones(len(rows)), cover))
    if model == "M2":
        return np.column_stack((np.ones(len(rows)), theta))
    return np.column_stack((np.ones(len(rows)), theta, cover, theta * cover))


def fit_ols(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(x, y, rcond=None)[0]


def fit_huber(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    coefficients = fit_ols(x, y)
    for _ in range(50):
        residual = y - x @ coefficients
        scale = max(np.median(np.abs(residual)) / 0.6745, 1e-8)
        weights = np.minimum(1.0, 1.345 * scale / np.maximum(np.abs(residual), 1e-12))
        updated = np.linalg.lstsq(x * np.sqrt(weights)[:, None], y * np.sqrt(weights), rcond=None)[0]
        if np.max(np.abs(updated - coefficients)) < 1e-10:
            return updated
        coefficients = updated
    return coefficients


def rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    result = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        result[order[start:end]] = (start + end - 1) / 2 + 1
        start = end
    return result


def correlation(actual: np.ndarray, predicted: np.ndarray) -> float:
    centered_a, centered_b = actual - actual.mean(), predicted - predicted.mean()
    denominator = math.sqrt(float(centered_a @ centered_a) * float(centered_b @ centered_b))
    return float(centered_a @ centered_b / denominator) if denominator else math.nan


def metrics(rows: list[dict]) -> dict:
    actual = np.array([row["S1_index"] for row in rows])
    predicted = np.array([row["prediction"] for row in rows])
    residual = actual - predicted
    baseline = float((actual - actual.mean()) @ (actual - actual.mean()))
    return {"r_squared_out": float(1 - (residual @ residual) / baseline) if baseline else math.nan, "rmse_out": float(np.sqrt(np.mean(residual ** 2))), "mae_out": float(np.mean(np.abs(residual))), "pearson_r": correlation(actual, predicted), "spearman_rho": correlation(rank(actual), rank(predicted)), "n": len(rows), "fields": len({row["field_id"] for row in rows})}


def field_mean_metrics(rows: list[dict]) -> dict:
    by_field = defaultdict(list)
    for row in rows:
        by_field[row["field_id"]].append(row)
    values = [metrics(group) for group in by_field.values()]
    return {key: float(np.nanmean([item[key] for item in values])) for key in ("r_squared_out", "rmse_out", "mae_out", "pearson_r", "spearman_rho")} | {"fields": len(values)}


def evaluate(rows: list[dict], folds: list[list[str]], robust: bool) -> tuple[list[dict], dict]:
    predictions = []
    fitter = fit_huber if robust else fit_ols
    for model in ("M1", "M2", "M3"):
        model_predictions = []
        for fold, test_fields in enumerate(folds, start=1):
            train = [row for row in rows if row["field_id"] not in test_fields]
            test = [row for row in rows if row["field_id"] in test_fields]
            coefficients = fitter(design(train, model), np.array([row["S1_index"] for row in train]))
            values = design(test, model) @ coefficients
            for row, value in zip(test, values):
                model_predictions.append({"model": model, "fit": "Huber" if robust else "OLS", "fold": fold, "field_id": row["field_id"], "date": row["date"], "S1_index": row["S1_index"], "prediction": float(value), "residual": float(row["S1_index"] - value), "theta_0_10": row["theta_0_10"], "fcover_model": row["fcover_model"], "P0": row["P0"], "I0": row["I0"]})
        predictions.extend(model_predictions)
    report = {}
    for model in ("M1", "M2", "M3"):
        selected = [row for row in predictions if row["model"] == model]
        report[model] = {"all_points": metrics(selected), "equal_field_weight": field_mean_metrics(selected), "without_same_day_water": metrics([row for row in selected if row["P0"] + row["I0"] == 0])}
    return predictions, report


def bootstrap_difference(predictions: list[dict], model_a: str, model_b: str, count: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    fields = sorted({row["field_id"] for row in predictions})
    by_model_field = defaultdict(list)
    for row in predictions:
        by_model_field[row["model"], row["field_id"]].append(row)
    r2_differences, rmse_differences = [], []
    for _ in range(count):
        sampled = rng.choice(fields, len(fields), replace=True)
        first = [item for field in sampled for item in by_model_field[model_a, field]]
        second = [item for field in sampled for item in by_model_field[model_b, field]]
        first_metrics, second_metrics = metrics(first), metrics(second)
        r2_differences.append(first_metrics["r_squared_out"] - second_metrics["r_squared_out"])
        rmse_differences.append(second_metrics["rmse_out"] - first_metrics["rmse_out"])
    interval = lambda values: [float(np.quantile(values, .025)), float(np.quantile(values, .975))]
    return {
        "models": [model_a, model_b], "bootstrap_fields": count,
        "delta_r_squared_out": {"median": float(np.median(r2_differences)), "ci95": interval(r2_differences)},
        "delta_rmse_out": {"median": float(np.median(rmse_differences)), "ci95": interval(rmse_differences)},
    }


def pair_correlation(first: np.ndarray, second: np.ndarray) -> dict:
    return {
        "pearson_r": correlation(first, second),
        "spearman_rho": correlation(rank(first), rank(second)),
        "n": int(len(first)),
    }


def robust_z(values: np.ndarray) -> np.ndarray | None:
    scale = float(np.median(np.abs(values - np.median(values))))
    if not math.isfinite(scale) or scale <= 0:
        return None
    return (values - np.median(values)) / scale


def bootstrap_field_stat(by_field: dict[str, list[dict]], statistic, count: int, seed: int) -> dict:
    fields = sorted(by_field)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(count):
        sampled = rng.choice(fields, len(fields), replace=True)
        value = statistic([item for field in sampled for item in by_field[field]])
        if math.isfinite(value):
            values.append(value)
    if not values:
        return {"bootstrap_fields": count, "median": math.nan, "ci95": [math.nan, math.nan]}
    return {
        "bootstrap_fields": count,
        "median": float(np.median(values)),
        "ci95": [float(np.quantile(values, .025)), float(np.quantile(values, .975))],
    }


def rank_summary(values: list[float], count: int, seed: int) -> dict:
    finite = np.array([value for value in values if math.isfinite(value)])
    if not len(finite):
        return {"fields": 0}
    rng = np.random.default_rng(seed)
    samples = [float(np.median(rng.choice(finite, len(finite), replace=True))) for _ in range(count)]
    return {
        "fields": int(len(finite)), "median": float(np.median(finite)),
        "iqr": [float(np.quantile(finite, .25)), float(np.quantile(finite, .75))],
        "min": float(np.min(finite)), "max": float(np.max(finite)),
        "share_positive": float(np.mean(finite > 0)), "share_gt_0_4": float(np.mean(finite > .4)),
        "share_gt_0_6": float(np.mean(finite > .6)),
        "bootstrap_median": {"bootstrap_fields": count, "median": float(np.median(samples)), "ci95": [float(np.quantile(samples, .025)), float(np.quantile(samples, .975))]},
    }


def auc_wet_over_dry(dry: np.ndarray, wet: np.ndarray) -> float:
    comparisons = wet[:, None] - dry[None, :]
    return float((np.sum(comparisons > 0) + .5 * np.sum(comparisons == 0)) / comparisons.size) if comparisons.size else math.nan


def observability_analysis(rows: list[dict], bootstrap: int, seed: int, delta_theta_min: float) -> tuple[list[dict], dict]:
    """Diagnostics of whether S1 tracks within-field model-moisture dynamics."""
    by_field = defaultdict(list)
    for row in rows:
        by_field[row["field_id"]].append(row)
    field_rows, all_z_s1, all_z_theta, all_delta_s1, all_delta_theta, sign_matches = [], [], [], [], [], []
    field_aucs = []
    for field, group in sorted(by_field.items()):
        group = sorted(group, key=lambda item: item["date"])
        s1 = np.array([item["S1_index"] for item in group])
        theta = np.array([item["theta_0_10"] for item in group])
        raw = pair_correlation(s1, theta)
        z_s1, z_theta = robust_z(s1), robust_z(theta)
        anomaly = pair_correlation(z_s1, z_theta) if z_s1 is not None and z_theta is not None else {"pearson_r": math.nan, "spearman_rho": math.nan, "n": 0}
        delta_s1, delta_theta = np.diff(s1), np.diff(theta)
        keep = np.abs(delta_theta) >= delta_theta_min
        dynamic = pair_correlation(delta_s1[keep], delta_theta[keep]) if np.count_nonzero(keep) >= 2 else {"pearson_r": math.nan, "spearman_rho": math.nan, "n": int(np.count_nonzero(keep))}
        signs = np.sign(delta_s1[keep]) == np.sign(delta_theta[keep])
        dry_cut, wet_cut = np.quantile(theta, (1 / 3, 2 / 3))
        auc = auc_wet_over_dry(s1[theta <= dry_cut], s1[theta >= wet_cut])
        field_rows.append({
            "field_id": field, "n": len(group), "raw_pearson_r": raw["pearson_r"], "raw_spearman_rho": raw["spearman_rho"],
            "anomaly_pearson_r": anomaly["pearson_r"], "anomaly_spearman_rho": anomaly["spearman_rho"],
            "delta_spearman_rho": dynamic["spearman_rho"], "delta_n": dynamic["n"],
            "sign_accuracy": float(np.mean(signs)) if len(signs) else math.nan, "sign_n": int(len(signs)), "auc_wet_over_dry": auc,
        })
        if z_s1 is not None and z_theta is not None:
            all_z_s1.extend(z_s1); all_z_theta.extend(z_theta)
        if np.count_nonzero(keep):
            all_delta_s1.extend(delta_s1[keep]); all_delta_theta.extend(delta_theta[keep]); sign_matches.extend(signs)
        if math.isfinite(auc):
            field_aucs.append(auc)

    raw_s1 = np.array([row["S1_index"] for row in rows])
    raw_theta = np.array([row["theta_0_10"] for row in rows])
    raw_field_spearman = [row["raw_spearman_rho"] for row in field_rows]
    delta_by_field = {field: sorted(group, key=lambda item: item["date"]) for field, group in by_field.items()}
    sign_bootstrap = bootstrap_field_stat(
        delta_by_field,
        lambda sampled: sign_accuracy_for_rows(sampled, delta_theta_min), bootstrap, seed + 23,
    )
    return field_rows, {
        "purpose": "Диагностика добавочной наблюдаемости расчётной влажности 0–10 см через Sentinel-1; не является калибровкой абсолютной влажности.",
        "pooled_raw": pair_correlation(raw_s1, raw_theta),
        "within_field_spearman": rank_summary(raw_field_spearman, bootstrap, seed + 11),
        "robust_standardized_anomalies": pair_correlation(np.array(all_z_s1), np.array(all_z_theta)) if len(all_z_s1) >= 2 else {"n": 0},
        "changes_between_sentinel1_dates": {
            "theta_change_minimum": delta_theta_min,
            "correlation": pair_correlation(np.array(all_delta_s1), np.array(all_delta_theta)) if len(all_delta_s1) >= 2 else {"n": 0},
            "sign_accuracy": float(np.mean(sign_matches)) if sign_matches else math.nan,
            "n": len(sign_matches), "bootstrap_sign_accuracy": sign_bootstrap,
        },
        "dry_wet_terciles": {"field_auc_wet_over_dry_median": float(np.median(field_aucs)) if field_aucs else math.nan, "fields": len(field_aucs), "interpretation": "Вероятность P(S1_wet > S1_dry); 0.5 соответствует случайному различению."},
        "field_intercept_diagnostic": field_intercept_diagnostic(rows),
        "mixed_effects": {"status": "not_fitted", "reason": "В рабочей среде QGIS нет statsmodels; использована диагностическая OLS с отдельными перехватами полей, но основным доказательством остаётся grouped cross-validation."},
    }


def sign_accuracy_for_rows(rows: list[dict], threshold: float) -> float:
    by_field = defaultdict(list)
    for row in rows:
        by_field[row["field_id"]].append(row)
    matches = []
    for group in by_field.values():
        group = sorted(group, key=lambda item: item["date"])
        delta_s1 = np.diff([item["S1_index"] for item in group])
        delta_theta = np.diff([item["theta_0_10"] for item in group])
        keep = np.abs(delta_theta) >= threshold
        matches.extend(np.sign(delta_s1[keep]) == np.sign(delta_theta[keep]))
    return float(np.mean(matches)) if matches else math.nan


def field_intercept_diagnostic(rows: list[dict]) -> dict:
    fields = sorted({row["field_id"] for row in rows})
    field_index = {field: index for index, field in enumerate(fields)}
    theta = np.array([row["theta_0_10"] for row in rows])
    cover = np.array([row["fcover_model"] for row in rows])
    intercepts = np.zeros((len(rows), len(fields)))
    for index, row in enumerate(rows):
        intercepts[index, field_index[row["field_id"]]] = 1
    x = np.column_stack((intercepts, theta, cover, theta * cover))
    actual = np.array([row["S1_index"] for row in rows])
    predicted = x @ fit_ols(x, actual)
    residual = actual - predicted
    baseline = float(np.sum((actual - actual.mean()) ** 2))
    return {"kind": "OLS с отдельным перехватом каждого поля", "in_sample_r_squared": float(1 - np.sum(residual ** 2) / baseline) if baseline else math.nan, "fields": len(fields), "warning": "Это внутривыборочная диагностика, не метрика переносимости на новое поле."}


def diagnostics(predictions: list[dict]) -> tuple[list[dict], dict]:
    selected = [row for row in predictions if row["model"] == "M3" and row["fit"] == "Huber"]
    by_field = defaultdict(list)
    for row in selected:
        by_field[row["field_id"]].append(row)
    fields = [{"field_id": field, **metrics(rows)} for field, rows in sorted(by_field.items())]
    residual = np.array([row["residual"] for row in selected])
    return fields, {
        "residual_pearson": {
            "fcover_model": correlation(residual, np.array([row["fcover_model"] for row in selected])),
            "theta_0_10": correlation(residual, np.array([row["theta_0_10"] for row in selected])),
            "same_day_water": correlation(residual, np.array([row["P0"] + row["I0"] for row in selected])),
        }
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def save_figure(path: Path, predictions: list[dict], report: dict) -> None:
    import matplotlib.pyplot as plt

    selected = [row for row in predictions if row["model"] == "M3" and row["fit"] == "Huber"]
    actual = np.array([row["S1_index"] for row in selected])
    predicted = np.array([row["prediction"] for row in selected])
    values = [report["robust_huber"][model]["all_points"]["r_squared_out"] for model in ("M1", "M2", "M3")]
    figure, (left, right) = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    left.scatter(actual, predicted, s=10, alpha=.45, color="#267a9e", edgecolors="none")
    limits = [min(actual.min(), predicted.min()), max(actual.max(), predicted.max())]
    left.plot(limits, limits, color="#555555", linewidth=1)
    left.set(xlabel=f"Наблюдаемый Sentinel-1 {report['s1_index'].replace('dB', 'дБ')}", ylabel="Предсказание на новых полях, дБ", title="M3: наблюдаемый и предсказанный Sentinel-1")
    right.bar(("M1\nтолько fCover", "M2\nтолько влажность", "M3\nвлага + fCover"), values, color=("#d95f02", "#7570b3", "#1b9e77"))
    right.axhline(0, color="#555555", linewidth=1)
    right.set(ylabel="R² вне обучения", title="Робастная межполевая проверка (36 полей)")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def self_test() -> None:
    assert normalize_field_id("SP:7.3") == "SP_7_3"
    test = [{"theta_0_10": .2, "fcover_model": .3}, {"theta_0_10": .4, "fcover_model": .5}]
    assert design(test, "M3").shape == (2, 4)
    assert round(correlation(rank(np.array([2., 1.])), rank(np.array([4., 3.]))), 6) == 1.0
    test_rows = [
        {"field_id": "SP_1_1", "date": "2026-01-01", "S1_index": 1., "theta_0_10": .1, "fcover_model": .2},
        {"field_id": "SP_1_1", "date": "2026-01-02", "S1_index": 2., "theta_0_10": .2, "fcover_model": .3},
        {"field_id": "SP_1_1", "date": "2026-01-03", "S1_index": 3., "theta_0_10": .3, "fcover_model": .4},
    ]
    _, observability = observability_analysis(test_rows, 10, 1, .01)
    assert observability["within_field_spearman"]["median"] == 1.0


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    allowed_fields = fcover_fields(args.fcover_r2_csv, args.min_fcover_r2)
    rows = build_rows(read_csv(args.kornix_csv), read_csv(args.radar_csv), args.method, args.variant, args.s1_index, allowed_fields)
    folds = field_folds(rows, args.folds)
    write_csv(args.data_output, rows)
    ordinary, ordinary_report = evaluate(rows, folds, robust=False)
    robust, robust_report = evaluate(rows, folds, robust=True)
    predictions = ordinary + robust
    write_csv(args.predictions_output, predictions)
    prediction_field_rows, residual_report = diagnostics(predictions)
    observability_field_rows, observability_report = observability_analysis(rows, args.bootstrap, args.seed, args.delta_theta_min)
    field_rows_by_id = {row["field_id"]: row for row in prediction_field_rows}
    for row in observability_field_rows:
        field_rows_by_id.setdefault(row["field_id"], {}).update(row)
    write_csv(args.field_output, [field_rows_by_id[field] for field in sorted(field_rows_by_id)])
    bootstrap_huber = [bootstrap_difference(robust, "M3", baseline, args.bootstrap, args.seed) for baseline in ("M1", "M2")]
    report = {
        "schema_version": 2,
        "purpose": "Проверка добавочной наблюдаемости расчётной влажности 0–10 см через Sentinel-1 после независимой фиксации FCOVER Sentinel-2.",
        "method": args.method, "row_spacing_variant": args.variant, "s1_index": f"{args.s1_index.upper()} dB",
        "excluded_fields": sorted(EXCLUDED_FIELDS), "min_fcover_r2": args.min_fcover_r2,
        "input_rows": len(rows), "fields": len({row['field_id'] for row in rows}), "folds": folds,
        "models": {"M1": "S1 ~ fCover", "M2": "S1 ~ theta_0_10", "M3": "S1 ~ theta_0_10 + fCover + theta_0_10*fCover"},
        "ordinary_least_squares": ordinary_report, "robust_huber": robust_report,
        "cross_validated_predictive_gain": {"comparison": "M3 против M1 и M2 только на отложенных полях", "bootstrap_huber": bootstrap_huber},
        "bootstrap_huber": bootstrap_huber, "observability_analysis": observability_report,
        "residual_diagnostics_m3_huber": residual_report,
        "same_day_water_rule": "Sensitivity analysis excludes P0 + I0 > 0; water inputs are not regression predictors.",
        "interpretation_rules": [
            "Невысокий pooled R² не отменяет внутриполевую и динамическую связь, поэтому они выводятся отдельно.",
            "Главное подтверждение переносимости — прирост качества M3 относительно M1 на отложенных полях.",
            "Sentinel-1 является шумным независимым наблюдением приповерхностного состояния, а не калибровкой абсолютной влажности.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_figure(args.figure, predictions, report)
    print(f"Validated {report['fields']} fields and {report['input_rows']} field-dates; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
