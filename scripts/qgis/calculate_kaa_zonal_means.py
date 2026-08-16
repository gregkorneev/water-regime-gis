#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import configure_qgis_environment

configure_qgis_environment()

from osgeo import gdal


DEFAULT_IMAGERY = ROOT / "outputs/imagery"
DEFAULT_REPORT = ROOT / "outputs/reports/kaa_zonal_means.csv"
BANDS = {
    "Blue": 1,
    "Green": 2,
    "Red": 3,
    "RedEdge": 4,
    "NIR": 5,
    "SWIR1": 6,
    "SWIR2": 7,
    "SCL": 8,
}
FORMULAS = {
    "NDVI": ("NIR", "Red"),
    "NDMI": ("NIR", "SWIR1"),
    "NDRE": ("NIR", "RedEdge"),
    "SAVI": ("NIR", "Red"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate zonal mean index values for KAA field raster patches."
    )
    parser.add_argument("--imagery", type=Path, default=DEFAULT_IMAGERY)
    parser.add_argument("--dataset", nargs="+", default=["kaa"])
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--indices", nargs="+", default=list(FORMULAS))
    parser.add_argument("--limit", type=int, help="Process at most N raster patches.")
    parser.add_argument("--include-clouds", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0

    gdal.UseExceptions()
    imagery_root = args.imagery.expanduser().resolve()
    records = []
    metadata_paths = sorted(
        path
        for dataset in args.dataset
        for path in (imagery_root / dataset).glob("*/*/metadata.json")
    )
    for metadata_path in metadata_paths:
        if args.limit is not None and len(records) >= args.limit * len(args.indices):
            break
        scene_dir = metadata_path.parent
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        analysis_path = scene_dir / "sentinel_analysis.tif"
        mask_path = scene_dir / "cloud_mask.tif"
        label = f"{metadata.get('dataset')}/{metadata.get('field_id')}/{metadata.get('scene_date')}"
        if not analysis_path.exists():
            print(f"SKIP {label}: missing {analysis_path.name}")
            continue
        try:
            records.extend(
                zonal_records(metadata, analysis_path, mask_path, args.indices, args.include_clouds)
            )
            print(f"OK {label}")
        except Exception as exc:
            print(f"ERROR {label}: {exc}")

    write_csv(args.report.expanduser().resolve(), records)
    write_manifest(args.report.expanduser().resolve().with_suffix(".json"), args, records)
    print(f"Rows: {len(records)}")
    print(f"Report: {args.report.expanduser().resolve()}")
    return 0


def zonal_records(
    metadata: dict,
    analysis_path: Path,
    mask_path: Path,
    indices: list[str],
    include_clouds: bool,
) -> list[dict]:
    import numpy as np

    dataset = gdal.Open(str(analysis_path))
    if dataset is None or dataset.RasterCount < len(BANDS):
        raise RuntimeError(f"Invalid analysis raster: {analysis_path}")

    arrays = {
        name: dataset.GetRasterBand(number).ReadAsArray().astype("float32") / 10000.0
        for name, number in BANDS.items()
        if name != "SCL"
    }
    scene_invalid = np.zeros_like(next(iter(arrays.values())), dtype=bool)
    if not include_clouds and mask_path.exists():
        mask_ds = gdal.Open(str(mask_path))
        scene_invalid |= mask_ds.ReadAsArray().astype("uint8") != 0

    rows = []
    for index_name in indices:
        index_name = index_name.upper()
        if index_name not in FORMULAS:
            continue
        left, right = FORMULAS[index_name]
        values = calculate_index(index_name, arrays[left], arrays[right])
        index_invalid = scene_invalid | (arrays[left] <= 0) | (arrays[right] <= 0) | ~np.isfinite(values)
        valid = values[~index_invalid]
        rows.append(
            {
                "dataset": metadata.get("dataset", ""),
                "field_id": metadata.get("field_id", ""),
                "scene_date": metadata.get("scene_date", ""),
                "scene_id": metadata.get("scene_id", ""),
                "index": index_name,
                "zonal_mean": float(valid.mean()) if valid.size else "",
                "valid_pixel_count": int(valid.size),
                "nodata_pixel_count": int(index_invalid.sum()),
                "aoi_cloud_cover": metadata.get("aoi_cloud_cover", ""),
                "analysis_raster": str(analysis_path),
            }
        )
    return rows


def calculate_index(name: str, left, right):
    import numpy as np

    with np.errstate(divide="ignore", invalid="ignore"):
        if name == "SAVI":
            return 1.5 * (left - right) / (left + right + 0.5)
        return (left - right) / (left + right)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "field_id",
        "scene_date",
        "scene_id",
        "index",
        "zonal_mean",
        "valid_pixel_count",
        "nodata_pixel_count",
        "aoi_cloud_cover",
        "analysis_raster",
    ]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_manifest(path: Path, args: argparse.Namespace, rows: list[dict]) -> None:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "imagery": str(args.imagery.expanduser().resolve()),
        "dataset": args.dataset,
        "indices": args.indices,
        "include_clouds": args.include_clouds,
        "row_count": len(rows),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def self_test() -> None:
    import numpy as np

    nir = np.array([[0.6, 0.4]], dtype="float32")
    red = np.array([[0.2, 0.2]], dtype="float32")
    ndvi = calculate_index("NDVI", nir, red)
    savi = calculate_index("SAVI", nir, red)
    assert np.allclose(ndvi, np.array([[0.5, 1 / 3]], dtype="float32"))
    assert np.allclose(savi, np.array([[6 / 13, 3 / 11]], dtype="float32"))


if __name__ == "__main__":
    raise SystemExit(main())
