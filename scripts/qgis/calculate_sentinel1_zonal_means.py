#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import configure_qgis_environment

configure_qgis_environment()

from osgeo import gdal

from qgis_plugins.water_regime_gis_plugin.radar_series import mean_backscatter_db


DEFAULT_IMAGERY = ROOT / "outputs/imagery/sentinel1"
DEFAULT_REPORT = ROOT / "outputs/reports/sentinel1_zonal_means.csv"
POLARIZATIONS = ("VV", "VH")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate Sentinel-1 VV/VH field means in dB.")
    parser.add_argument("--imagery", type=Path, default=DEFAULT_IMAGERY)
    parser.add_argument("--dataset", nargs="+", default=["sp"])
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, help="Process at most N raster patches.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gdal.UseExceptions()
    imagery_root = args.imagery.expanduser().resolve()
    paths = sorted(
        path
        for dataset in args.dataset
        for path in (imagery_root / dataset).glob("*/*/sentinel_rtc.tif")
    )
    if args.limit is not None:
        paths = paths[: args.limit]

    records = []
    for raster_path in paths:
        metadata_path = raster_path.with_name("metadata.json")
        if not metadata_path.exists():
            print(f"SKIP {raster_path}: missing metadata.json")
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            records.extend(zonal_records(metadata, raster_path))
            print(f"OK {metadata.get('dataset')}/{metadata.get('field_id')}/{metadata.get('scene_date')}")
        except Exception as exc:
            print(f"ERROR {raster_path}: {exc}")

    records.sort(key=lambda row: (row["dataset"], row["field_id"], row["scene_date"], row["polarization"]))
    report = args.report.expanduser().resolve()
    write_csv(report, records)
    write_manifest(report.with_suffix(".json"), args, records)
    print(f"Rows: {len(records)}")
    print(f"Report: {report}")
    return 0


def zonal_records(metadata: dict, raster_path: Path) -> list[dict]:
    dataset = gdal.Open(str(raster_path))
    if dataset is None or dataset.RasterCount < len(POLARIZATIONS):
        raise RuntimeError(f"Invalid Sentinel-1 raster: {raster_path}")

    rows = []
    for band_number, fallback_name in enumerate(POLARIZATIONS, start=1):
        band = dataset.GetRasterBand(band_number)
        polarization = (band.GetDescription() or fallback_name).upper()
        mean_db, valid_count, nodata_count = mean_backscatter_db(
            band.ReadAsArray(), band.GetNoDataValue()
        )
        rows.append(
            {
                "dataset": metadata.get("dataset", ""),
                "field_id": metadata.get("field_id", ""),
                "scene_date": metadata.get("scene_date", ""),
                "scene_id": metadata.get("scene_id", ""),
                "polarization": polarization,
                "zonal_mean_db": "" if mean_db is None else mean_db,
                "valid_pixel_count": valid_count,
                "nodata_pixel_count": nodata_count,
                "radar_raster": str(raster_path),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "field_id",
        "scene_date",
        "scene_id",
        "polarization",
        "zonal_mean_db",
        "valid_pixel_count",
        "nodata_pixel_count",
        "radar_raster",
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
        "polarizations": list(POLARIZATIONS),
        "units": "dB",
        "aggregation": "10*log10(mean(linear RTC values))",
        "row_count": len(rows),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
