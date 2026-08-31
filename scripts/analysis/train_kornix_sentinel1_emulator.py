#!/usr/bin/env python3
"""Train a KORNIX 0-10 cm moisture emulator on fields unseen during testing."""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "results/data/sp_kornix_sentinel1_moisture.csv"
DEFAULT_OUTPUT = ROOT / "results/data/sp_kornix_sentinel1_field_holdout_predictions.csv"
DEFAULT_REPORT = ROOT / "results/reports/sp_kornix_sentinel1_field_holdout.json"
TARGET = "kornix_moisture_0_10"
WATER_INPUTS = (
    "precipitation_3d_mm",
    "irrigation_3d_mm",
    "precipitation_7d_mm",
    "irrigation_7d_mm",
)
EXCLUDED_FIELDS = {"SP_7_3"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--train-fields", type=int, default=23)
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--ridge-alpha", type=float, default=1.0)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            {key: float(value) if key not in {"field_id", "day"} else value for key, value in row.items()}
            for row in csv.DictReader(handle)
            if row["field_id"] not in EXCLUDED_FIELDS
        ]


def split_fields(rows: list[dict], train_count: int, seed: int) -> tuple[list[str], list[str]]:
    fields = sorted({row["field_id"] for row in rows})
    if not 0 < train_count < len(fields):
        raise ValueError(f"--train-fields must be between 1 and {len(fields) - 1}")
    random.Random(seed).shuffle(fields)
    return sorted(fields[:train_count]), sorted(fields[train_count:])


def feature_values(row: dict, mode: str) -> list[float]:
    values = [row[name] for name in WATER_INPUTS] if mode != "sentinel1_only" else []
    if mode != "water_only":
        vv, vh = row["sentinel1_vv_db"], row["sentinel1_vh_db"]
        values.extend((vv, vh, vv * vh, vv * vv, vh * vh))
    return values


def fit_ridge(rows: list[dict], mode: str, alpha: float) -> dict:
    features = np.array([feature_values(row, mode) for row in rows], dtype=float)
    target = np.array([row[TARGET] for row in rows], dtype=float)
    mean, scale = features.mean(axis=0), features.std(axis=0)
    scale[scale == 0] = 1.0
    standardized = (features - mean) / scale
    coefficients = np.linalg.solve(standardized.T @ standardized + alpha * np.eye(standardized.shape[1]), standardized.T @ (target - target.mean()))
    return {"mean": mean, "scale": scale, "target_mean": target.mean(), "coefficients": coefficients, "mode": mode}


def predict(model: dict, rows: list[dict]) -> np.ndarray:
    features = np.array([feature_values(row, model["mode"]) for row in rows], dtype=float)
    return (features - model["mean"]) / model["scale"] @ model["coefficients"] + model["target_mean"]


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    residual = actual - predicted
    return {
        "mae": float(np.abs(residual).mean()),
        "rmse": float(np.sqrt((residual * residual).mean())),
        "r_squared": float(1 - (residual @ residual) / ((actual - actual.mean()) @ (actual - actual.mean()))),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def train(rows: list[dict], train_count: int, seed: int, alpha: float) -> tuple[list[dict], dict]:
    train_fields, test_fields = split_fields(rows, train_count, seed)
    training = [row for row in rows if row["field_id"] in train_fields]
    testing = [row for row in rows if row["field_id"] in test_fields]
    sentinel_model = fit_ridge(training, "sentinel1_only", alpha)
    water_model = fit_ridge(training, "water_only", alpha)
    hybrid_model = fit_ridge(training, "sentinel1_plus_water", alpha)
    sentinel_reconstruction = predict(sentinel_model, testing)
    water_reconstruction = predict(water_model, testing)
    hybrid_reconstruction = predict(hybrid_model, testing)
    actual = np.array([row[TARGET] for row in testing], dtype=float)
    predictions = [
        {
            "field_id": row["field_id"],
            "day": row["day"],
            "split": "test",
            "kornix_moisture_0_10": row[TARGET],
            "sentinel1_only_reconstruction": sentinel,
            "water_only_reconstruction": water,
            "sentinel1_plus_water_reconstruction": hybrid,
            "sentinel1_plus_water_residual": row[TARGET] - hybrid,
        }
        for row, sentinel, water, hybrid in zip(testing, sentinel_reconstruction, water_reconstruction, hybrid_reconstruction)
    ]
    report = {
        "target": TARGET,
        "method": "ridge regression with field holdout",
        "train_fields": train_fields,
        "test_fields": test_fields,
        "training_rows": len(training),
        "test_rows": len(testing),
        "sentinel1_only_test": metrics(actual, sentinel_reconstruction),
        "water_only_test": metrics(actual, water_reconstruction),
        "sentinel1_plus_water_test": metrics(actual, hybrid_reconstruction),
        "test_r_squared_gain_from_sentinel1": metrics(actual, hybrid_reconstruction)["r_squared"] - metrics(actual, water_reconstruction)["r_squared"],
        "features": {"sentinel1_only": ["VV", "VH", "VV*VH", "VV^2", "VH^2"], "water_only": list(WATER_INPUTS), "sentinel1_plus_water": [*WATER_INPUTS, "VV", "VH", "VV*VH", "VV^2", "VH^2"]},
        "interpretation": "Это ретроспективная реконструкция КОРНИКС в даты Sentinel-1. Поля в test_fields не использовались при обучении; модель не является независимым наземным измерением.",
    }
    return predictions, report


def self_test() -> None:
    rows = [{"field_id": f"SP_{index}_1", "day": "2026-04-01", TARGET: 0.2, **{name: 1.0 for name in WATER_INPUTS}, "sentinel1_vv_db": -8.0, "sentinel1_vh_db": -16.0} for index in range(4)]
    train_fields, test_fields = split_fields(rows, 3, 1)
    assert len(train_fields) == 3 and len(test_fields) == 1
    assert len(feature_values(rows[0], "sentinel1_only")) == 5
    assert len(feature_values(rows[0], "sentinel1_plus_water")) == len(WATER_INPUTS) + 5


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    predictions, report = train(read_rows(args.input), args.train_fields, args.seed, args.ridge_alpha)
    write_csv(args.output, predictions)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Test rows: {report['test_rows']}; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
