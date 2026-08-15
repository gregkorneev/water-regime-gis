#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/analysis.example.json"
GROUND_COLUMNS = [
    "field_id",
    "date",
    "soil_moisture",
    "LAI",
    "FCOVER",
    "soil_moisture_0_10",
    "soil_moisture_10_20",
    "soil_moisture_20_40",
    "irrigation_mm",
    "precipitation_mm",
]
MODEL_SPECS = {
    "M1": ["OPTRAM"],
    "M2": ["NDMI"],
    "M3": ["OPTRAM", "NDMI"],
    "M4": ["OPTRAM", "NDMI", "LAI", "FCOVER"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare satellite/ground analysis tables and model reports.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--satellite-csv", type=Path)
    parser.add_argument("--ground-csv", type=Path)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--max-days-difference", type=int)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0

    config = load_config(args.config)
    satellite_csv = project_path(args.satellite_csv or Path(config["satellite_csv"]))
    ground_csv = project_path(args.ground_csv or Path(config["ground_csv"]))
    results_dir = project_path(args.results_dir or Path(config["results_dir"]))
    max_days = args.max_days_difference if args.max_days_difference is not None else int(config["max_days_difference"])
    indices = [name.upper() for name in config["indices"]]
    ensure_results_tree(results_dir)

    long_rows = read_csv(satellite_csv)
    prepared_rows, qa = prepare_satellite(long_rows, indices)
    prepared_path = results_dir / "data/prepared_satellite_data.csv"
    write_csv(prepared_path, prepared_rows, prepared_fieldnames(indices))

    seasonal_rows = seasonal_summary(prepared_rows, indices)
    write_csv(results_dir / "tables/seasonal_summary.csv", seasonal_rows, seasonal_fieldnames())
    write_csv(results_dir / "data/field_time_series.csv", prepared_rows, prepared_fieldnames(indices))
    write_quality_report(results_dir / "reports/satellite_quality_report.json", qa, prepared_rows, indices)
    write_quality_markdown(results_dir / "reports/satellite_quality_report.md", qa, prepared_rows, indices)

    ground_template = results_dir / "data/ground_measurements_template.csv"
    if not ground_csv.exists() and not ground_template.exists():
        write_csv(ground_template, [], GROUND_COLUMNS)

    model_rows, merge_report = merge_ground(prepared_rows, ground_csv, max_days, indices)
    write_csv(results_dir / "data/model_dataset.csv", model_rows, model_fieldnames(indices, model_rows))
    write_json(results_dir / "reports/merge_report.json", merge_report)

    optram_report = check_optram_availability(prepared_rows, project_path(Path(config["imagery_root"])))
    write_json(results_dir / "reports/optram_availability.json", optram_report)

    model_report = run_models(model_rows, indices, int(config["temporal_test_month"]))
    write_json(results_dir / "reports/model_report.json", model_report)
    write_model_comparison(results_dir / "tables/model_comparison.csv", model_report)
    write_figure_sources(results_dir, prepared_rows, model_rows, indices)
    write_run_summary(results_dir / "reports/run_summary.md", satellite_csv, ground_csv, prepared_rows, qa, merge_report, optram_report, model_report)

    print(f"Prepared satellite rows: {len(prepared_rows)}")
    print(f"Ground rows matched: {merge_report['matched_rows']}")
    print(f"Results: {results_dir}")
    return 0


def load_config(path: Path) -> dict:
    return json.loads(project_path(path).read_text(encoding="utf-8"))


def project_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def ensure_results_tree(results_dir: Path) -> None:
    for name in ("data", "figures", "models", "tables", "reports"):
        (results_dir / name).mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_satellite(long_rows: list[dict], indices: list[str]) -> tuple[list[dict], dict]:
    duplicate_counts = Counter()
    duplicate_examples = []
    by_key: dict[tuple[str, str], dict] = {}
    qa = {
        "source_rows": len(long_rows),
        "duplicate_field_date_index": 0,
        "duplicate_examples": duplicate_examples,
        "nan_rows": 0,
        "empty_zonal_mean_rows": 0,
        "unknown_indices": Counter(),
    }

    seen = set()
    for row in long_rows:
        field_id = (row.get("field_id") or "").strip()
        scene_date = (row.get("scene_date") or "").strip()
        index = (row.get("index") or "").strip().upper()
        key3 = (field_id, scene_date, index)
        if key3 in seen:
            duplicate_counts[key3] += 1
            if len(duplicate_examples) < 20:
                duplicate_examples.append({"field_id": field_id, "scene_date": scene_date, "index": index})
            continue
        seen.add(key3)

        if index not in indices:
            qa["unknown_indices"][index] += 1
            continue
        value = parse_float(row.get("zonal_mean"))
        if is_nan_text(row.get("zonal_mean")):
            qa["nan_rows"] += 1
        if value is None:
            qa["empty_zonal_mean_rows"] += 1

        key2 = (field_id, scene_date)
        prepared = by_key.setdefault(
            key2,
            {
                "field_id": field_id,
                "scene_date": scene_date,
                "scene_id": row.get("scene_id", ""),
                "analysis_raster": row.get("analysis_raster", ""),
            },
        )
        prepared[index] = format_float(value)

    rows = [fill_missing(row, indices) for row in sorted(by_key.values(), key=lambda r: (r["field_id"], r["scene_date"]))]
    qa["duplicate_field_date_index"] = sum(duplicate_counts.values())
    qa["unknown_indices"] = dict(qa["unknown_indices"])
    qa.update(satellite_quality(rows, indices))
    return rows, qa


def satellite_quality(rows: list[dict], indices: list[str]) -> dict:
    by_field = defaultdict(list)
    valid_by_index = {}
    ranges = {}
    missing_by_index = {}
    anomalous_rows = []
    for row in rows:
        by_field[row["field_id"]].append(row["scene_date"])
        missing_count = sum(1 for name in indices if parse_float(row.get(name)) is None)
        if missing_count >= max(1, len(indices) // 2):
            anomalous_rows.append({"field_id": row["field_id"], "scene_date": row["scene_date"], "missing_indices": missing_count})

    for name in indices:
        values = [parse_float(row.get(name)) for row in rows]
        values = [value for value in values if value is not None]
        valid_by_index[name] = len(values)
        missing_by_index[name] = len(rows) - len(values)
        ranges[name] = {"min": min(values) if values else None, "max": max(values) if values else None}

    dates_per_field = {field_id: len(set(dates)) for field_id, dates in by_field.items()}
    return {
        "prepared_rows": len(rows),
        "field_count": len(by_field),
        "dates_per_field": dates_per_field,
        "valid_observations_by_index": valid_by_index,
        "missing_by_index": missing_by_index,
        "ranges_by_index": ranges,
        "rows_with_many_missing_values": anomalous_rows[:100],
        "rows_with_many_missing_values_count": len(anomalous_rows),
    }


def fill_missing(row: dict, indices: list[str]) -> dict:
    for name in indices:
        row.setdefault(name, "")
    return row


def prepared_fieldnames(indices: list[str]) -> list[str]:
    return ["field_id", "scene_date", *indices, "scene_id", "analysis_raster"]


def seasonal_summary(rows: list[dict], indices: list[str]) -> list[dict]:
    result = []
    dates = sorted({row["scene_date"] for row in rows})
    for scene_date in dates:
        day_rows = [row for row in rows if row["scene_date"] == scene_date]
        for index in indices:
            values = [parse_float(row.get(index)) for row in day_rows]
            values = sorted(value for value in values if value is not None)
            result.append(
                {
                    "scene_date": scene_date,
                    "index": index,
                    "field_count": len(day_rows),
                    "valid_count": len(values),
                    "mean": format_float(mean(values)),
                    "median": format_float(percentile(values, 0.5)),
                    "p25": format_float(percentile(values, 0.25)),
                    "p75": format_float(percentile(values, 0.75)),
                }
            )
    return result


def seasonal_fieldnames() -> list[str]:
    return ["scene_date", "index", "field_count", "valid_count", "mean", "median", "p25", "p75"]


def write_quality_report(path: Path, qa: dict, rows: list[dict], indices: list[str]) -> None:
    write_json(path, qa)


def write_quality_markdown(path: Path, qa: dict, rows: list[dict], indices: list[str]) -> None:
    lines = [
        "# Satellite Data Quality",
        "",
        f"- Source rows: {qa['source_rows']}",
        f"- Prepared field-date rows: {qa['prepared_rows']}",
        f"- Fields: {qa['field_count']}",
        f"- Duplicate field/date/index rows: {qa['duplicate_field_date_index']}",
        f"- Empty zonal_mean rows: {qa['empty_zonal_mean_rows']}",
        f"- Rows with many missing values: {qa['rows_with_many_missing_values_count']}",
        "",
        "## Valid Observations",
        "",
        "| Index | Valid | Missing | Min | Max |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for index in indices:
        ranges = qa["ranges_by_index"][index]
        lines.append(
            f"| {index} | {qa['valid_observations_by_index'][index]} | {qa['missing_by_index'][index]} | {ranges['min']} | {ranges['max']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "Rows with empty means are preserved; they usually correspond to fully masked cloudy/nodata scenes.",
        "No averaging is performed across different fields.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def merge_ground(prepared_rows: list[dict], ground_csv: Path, max_days: int, indices: list[str]) -> tuple[list[dict], dict]:
    if not ground_csv.exists():
        empty = [{name: "" for name in model_fieldnames(indices, [])}]
        return empty[:0], {
            "status": "ground_missing",
            "ground_csv": str(ground_csv),
            "matched_rows": 0,
            "message": "Add ground measurements CSV and rerun.",
        }

    ground_rows = read_csv(ground_csv)
    satellite_by_field = defaultdict(list)
    for row in prepared_rows:
        parsed = parse_date(row["scene_date"])
        if parsed:
            satellite_by_field[row["field_id"]].append((parsed, row))
    for field_rows in satellite_by_field.values():
        field_rows.sort(key=lambda item: item[0])

    output = []
    unmatched = []
    for ground in ground_rows:
        field_id = ground.get("field_id", "")
        date = parse_date(ground.get("date", ""))
        if not field_id or not date:
            unmatched.append({"field_id": field_id, "date": ground.get("date", ""), "reason": "missing_key"})
            continue
        candidates = []
        for satellite_date, satellite in satellite_by_field.get(field_id, []):
            difference = abs((satellite_date - date).days)
            if difference <= max_days:
                candidates.append((difference, satellite_date, satellite))
        if not candidates:
            unmatched.append({"field_id": field_id, "date": ground.get("date", ""), "reason": "no_satellite_within_window"})
            continue
        difference, satellite_date, satellite = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        merged = {**satellite, **ground}
        merged["date"] = ground.get("date", "")
        merged["satellite_date"] = satellite["scene_date"]
        merged["days_difference"] = difference
        merged.setdefault("OPTRAM", "")
        output.append(merged)

    return output, {
        "status": "OK",
        "ground_csv": str(ground_csv),
        "ground_rows": len(ground_rows),
        "matched_rows": len(output),
        "unmatched_rows": len(unmatched),
        "max_days_difference": max_days,
        "unmatched_examples": unmatched[:50],
    }


def model_fieldnames(indices: list[str], rows: list[dict]) -> list[str]:
    base = ["field_id", "date", "satellite_date", "days_difference", *indices, "OPTRAM"]
    extras = []
    for column in GROUND_COLUMNS:
        if column not in base:
            extras.append(column)
    for row in rows:
        for key in row:
            if key not in base and key not in extras and key not in {"scene_date"}:
                extras.append(key)
    return base + extras


def check_optram_availability(prepared_rows: list[dict], imagery_root: Path) -> dict:
    rasters = [row.get("analysis_raster") for row in prepared_rows if row.get("analysis_raster")]
    existing = [path for path in (Path(raster) for raster in rasters) if path.exists()]
    return {
        "status": "bands_available_parameters_missing" if existing else "missing_analysis_rasters",
        "analysis_raster_count": len(existing),
        "required_bands": ["Red/B04", "NIR/B08", "SWIR2/B12"],
        "available_by_pipeline_contract": bool(existing),
        "computed": False,
        "reason": (
            "sentinel_analysis.tif contains B04/B08/B12, but OPTRAM edge/calibration parameters are not defined yet."
            if existing
            else "No local sentinel_analysis.tif files were found."
        ),
    }


def run_models(rows: list[dict], indices: list[str], temporal_test_month: int) -> dict:
    targets = ["soil_moisture", *sorted({key for row in rows for key in row if key.startswith("soil_moisture_")})]
    report = {
        "status": "ground_missing_or_empty" if not rows else "OK",
        "models": [],
        "correlation_matrix": {},
        "vif": {},
        "warnings": [],
    }
    if not rows:
        report["warnings"].append("Ground measurements are missing, so M1-M4 are not fitted yet.")
        for model_name, features in MODEL_SPECS.items():
            report["models"].append(skipped_model(model_name, features, "soil_moisture", 0, "ground_measurements_missing"))
        return report

    feature_columns = sorted({column for features in MODEL_SPECS.values() for column in features})
    report["correlation_matrix"] = correlation_matrix(rows, feature_columns + targets)
    report["vif"] = vif(rows, ["OPTRAM", "NDMI", "LAI", "FCOVER"])

    for target in targets:
        for model_name, features in MODEL_SPECS.items():
            dataset = numeric_dataset(rows, target, features)
            if len(dataset) < max(3, len(features) + 2):
                report["models"].append(skipped_model(model_name, features, target, len(dataset), "not_enough_complete_rows"))
                continue
            groups = [item["field_id"] for item in dataset]
            report["models"].append(evaluate_in_sample(model_name, features, target, dataset))
            report["models"].append(evaluate_group_kfold(model_name, features, target, dataset, groups))
            temporal = evaluate_temporal(model_name, features, target, dataset, temporal_test_month)
            if temporal:
                report["models"].append(temporal)
    return report


def numeric_dataset(rows: list[dict], target: str, features: list[str]) -> list[dict]:
    dataset = []
    for row in rows:
        y = parse_float(row.get(target))
        x = [parse_float(row.get(feature)) for feature in features]
        if y is None or any(value is None for value in x):
            continue
        dataset.append({"field_id": row.get("field_id", ""), "date": row.get("date") or row.get("satellite_date", ""), "x": x, "y": y})
    return dataset


def evaluate_in_sample(model_name: str, features: list[str], target: str, dataset: list[dict]) -> dict:
    model = fit_linear([item["x"] for item in dataset], [item["y"] for item in dataset])
    predictions = [predict(model, item["x"]) for item in dataset]
    return model_result(model_name, features, target, "InSample", dataset, model, predictions)


def evaluate_group_kfold(model_name: str, features: list[str], target: str, dataset: list[dict], groups: list[str]) -> dict:
    unique_groups = sorted(set(groups))
    if len(unique_groups) < 2:
        return skipped_model(model_name, features, target, len(dataset), "need_at_least_two_fields_for_group_kfold", "GroupKFold")
    fold_count = min(5, len(unique_groups))
    predictions = []
    observed = []
    for fold in range(fold_count):
        test_groups = set(unique_groups[fold::fold_count])
        train = [item for item in dataset if item["field_id"] not in test_groups]
        test = [item for item in dataset if item["field_id"] in test_groups]
        if len(train) < len(features) + 1 or not test:
            continue
        model = fit_linear([item["x"] for item in train], [item["y"] for item in train])
        predictions.extend(predict(model, item["x"]) for item in test)
        observed.extend(item["y"] for item in test)
    if not predictions:
        return skipped_model(model_name, features, target, len(dataset), "no_valid_group_folds", "GroupKFold")
    return metric_result(model_name, features, target, "GroupKFold", observed, predictions, None)


def evaluate_temporal(model_name: str, features: list[str], target: str, dataset: list[dict], test_month: int) -> dict | None:
    train = [item for item in dataset if (parse_date(item["date"]) or dt.date.min).month < test_month]
    test = [item for item in dataset if (parse_date(item["date"]) or dt.date.min).month >= test_month]
    if len(train) < len(features) + 1 or not test:
        return skipped_model(model_name, features, target, len(dataset), "not_enough_temporal_split_rows", "Temporal")
    model = fit_linear([item["x"] for item in train], [item["y"] for item in train])
    predictions = [predict(model, item["x"]) for item in test]
    return metric_result(model_name, features, target, "Temporal", [item["y"] for item in test], predictions, model)


def fit_linear(xs: list[list[float]], ys: list[float]) -> list[float]:
    matrix = [[1.0, *row] for row in xs]
    cols = len(matrix[0])
    xtx = [[sum(row[i] * row[j] for row in matrix) for j in range(cols)] for i in range(cols)]
    xty = [sum(row[i] * y for row, y in zip(matrix, ys)) for i in range(cols)]
    return solve_linear(xtx, xty)


def solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    aug = [row[:] + [value] for row, value in zip(matrix, vector)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("singular_matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        factor = aug[col][col]
        aug[col] = [value / factor for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            scale = aug[row][col]
            aug[row] = [value - scale * pivot_value for value, pivot_value in zip(aug[row], aug[col])]
    return [row[-1] for row in aug]


def predict(model: list[float], x: list[float]) -> float:
    return model[0] + sum(coef * value for coef, value in zip(model[1:], x))


def model_result(model_name: str, features: list[str], target: str, validation: str, dataset: list[dict], model: list[float], predictions: list[float]) -> dict:
    return metric_result(model_name, features, target, validation, [item["y"] for item in dataset], predictions, model)


def metric_result(model_name: str, features: list[str], target: str, validation: str, observed: list[float], predictions: list[float], model: list[float] | None) -> dict:
    metrics = regression_metrics(observed, predictions, len(features))
    result = {
        "model": model_name,
        "target": target,
        "features": features,
        "validation": validation,
        "N": len(observed),
        **metrics,
    }
    if model:
        result["intercept"] = model[0]
        result["coefficients"] = dict(zip(features, model[1:]))
    return result


def skipped_model(model_name: str, features: list[str], target: str, n: int, reason: str, validation: str = "All") -> dict:
    return {"model": model_name, "target": target, "features": features, "validation": validation, "N": n, "status": "skipped", "reason": reason}


def regression_metrics(observed: list[float], predicted: list[float], feature_count: int) -> dict:
    n = len(observed)
    mean_y = mean(observed)
    ss_res = sum((y - yhat) ** 2 for y, yhat in zip(observed, predicted))
    ss_tot = sum((y - mean_y) ** 2 for y in observed)
    r2 = 1 - ss_res / ss_tot if ss_tot else None
    adjusted = 1 - (1 - r2) * (n - 1) / (n - feature_count - 1) if r2 is not None and n > feature_count + 1 else None
    return {
        "R2": r2,
        "adjusted_R2": adjusted,
        "RMSE": math.sqrt(ss_res / n) if n else None,
        "MAE": mean([abs(y - yhat) for y, yhat in zip(observed, predicted)]),
    }


def correlation_matrix(rows: list[dict], columns: list[str]) -> dict:
    matrix = {}
    for left in columns:
        matrix[left] = {}
        for right in columns:
            pairs = [(parse_float(row.get(left)), parse_float(row.get(right))) for row in rows]
            pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
            matrix[left][right] = pearson([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 2 else None
    return matrix


def vif(rows: list[dict], features: list[str]) -> dict:
    values = {}
    for feature in features:
        others = [item for item in features if item != feature]
        dataset = numeric_dataset(rows, feature, others)
        if len(dataset) < len(others) + 2:
            values[feature] = None
            continue
        try:
            model = fit_linear([item["x"] for item in dataset], [item["y"] for item in dataset])
            predictions = [predict(model, item["x"]) for item in dataset]
            r2 = regression_metrics([item["y"] for item in dataset], predictions, len(others))["R2"]
            values[feature] = 1 / (1 - r2) if r2 is not None and r2 < 1 else None
        except ValueError:
            values[feature] = None
    return values


def write_model_comparison(path: Path, report: dict) -> None:
    rows = []
    for row in report.get("models", []):
        if row.get("status") == "skipped":
            rows.append({"Model": row["model"], "Features": " + ".join(row["features"]), "Validation": row["validation"], "N": row["N"], "R2": "", "RMSE": "", "MAE": "", "Status": row["reason"]})
        else:
            rows.append({"Model": row["model"], "Features": " + ".join(row["features"]), "Validation": row["validation"], "N": row["N"], "R2": row.get("R2"), "RMSE": row.get("RMSE"), "MAE": row.get("MAE"), "Status": "OK"})
    write_csv(path, rows, ["Model", "Features", "Validation", "N", "R2", "RMSE", "MAE", "Status"])


def write_figure_sources(results_dir: Path, prepared_rows: list[dict], model_rows: list[dict], indices: list[str]) -> None:
    note = (
        "# Figure Sources\n\n"
        "Matplotlib is not required by this project yet. Use the CSV files in `results/data/` and `results/tables/` "
        "as direct sources for QGIS/Excel plots. Ground-dependent plots will become available after `data/ground_measurements.csv` is filled.\n"
    )
    (results_dir / "figures/README.md").write_text(note, encoding="utf-8")


def write_run_summary(
    path: Path,
    satellite_csv: Path,
    ground_csv: Path,
    prepared_rows: list[dict],
    qa: dict,
    merge_report: dict,
    optram_report: dict,
    model_report: dict,
) -> None:
    lines = [
        "# Analysis Run Summary",
        "",
        f"- Satellite source: `{satellite_csv}`",
        f"- Ground source: `{ground_csv}`",
        f"- Prepared satellite rows: {len(prepared_rows)}",
        f"- Fields: {qa['field_count']}",
        f"- Ground merge status: {merge_report['status']}",
        f"- Matched ground rows: {merge_report['matched_rows']}",
        f"- OPTRAM status: {optram_report['status']}",
        f"- Model status: {model_report['status']}",
        "",
        "## Missing Data",
        "",
        "- Ground measurements are required for soil moisture, LAI and FCOVER analysis.",
        "- OPTRAM is not generated until the OPTRAM edge/calibration parameters are defined.",
        "",
        "## Main Outputs",
        "",
        "- `results/data/prepared_satellite_data.csv`",
        "- `results/data/model_dataset.csv`",
        "- `results/data/ground_measurements_template.csv`",
        "- `results/tables/seasonal_summary.csv`",
        "- `results/reports/satellite_quality_report.md`",
        "- `results/reports/model_report.json`",
        "- `results/reports/optram_availability.json`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return None if math.isnan(number) else number


def is_nan_text(value) -> bool:
    return str(value).strip().lower() == "nan"


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def format_float(value: float | None) -> str:
    return "" if value is None else f"{value:.12g}"


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return values[lower]
    return values[lower] * (upper - pos) + values[upper] * (pos - lower)


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    num = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    den_a = math.sqrt(sum((a - left_mean) ** 2 for a in left))
    den_b = math.sqrt(sum((b - right_mean) ** 2 for b in right))
    return num / (den_a * den_b) if den_a and den_b else None


def self_test() -> None:
    rows = [
        {"field_id": "A", "scene_date": "2026-01-01", "index": "NDVI", "zonal_mean": "0.2"},
        {"field_id": "A", "scene_date": "2026-01-01", "index": "NDMI", "zonal_mean": "-0.1"},
        {"field_id": "B", "scene_date": "2026-01-01", "index": "NDVI", "zonal_mean": "0.4"},
    ]
    prepared, qa = prepare_satellite(rows, ["NDVI", "NDMI"])
    assert len(prepared) == 2
    assert qa["valid_observations_by_index"]["NDVI"] == 2
    assert seasonal_summary(prepared, ["NDVI"])[0]["mean"] == "0.3"
    model = fit_linear([[1.0], [2.0], [3.0]], [2.0, 4.0, 6.0])
    assert abs(model[1] - 2.0) < 1e-9


if __name__ == "__main__":
    raise SystemExit(main())
