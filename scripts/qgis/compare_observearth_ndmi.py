#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PLUGINS = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(PROFILE_PLUGINS))

from water_regime_gis.qgis_runtime import configure_qgis_environment

configure_qgis_environment()

from osgeo import gdal
from observearth.sentinel2 import Sentinel2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare project NDMI with the installed Observearth engine.")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--project-raster", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    import numpy as np

    gdal.UseExceptions()
    args = parse_args()
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    paths = {name: ROOT / path for name, path in metadata["bands"].items()}
    nir_ds = gdal.Open(str(paths["NIR"]))
    swir_ds = gdal.Open(str(paths["SWIR1"]))
    nir_raw = nir_ds.ReadAsArray()
    swir_raw = swir_ds.ReadAsArray()
    invalid = (nir_raw <= 0) | (swir_raw <= 0)

    engine = Sentinel2()
    observed = engine.calculate_index(
        "ndmi",
        {
            "nir": engine.scale_band(nir_raw.astype("float32"), "nir"),
            "swir1": engine.scale_band(swir_raw.astype("float32"), "swir1"),
        },
    ).astype("float32")
    observed[invalid | ~np.isfinite(observed)] = -9999

    args.output.parent.mkdir(parents=True, exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    output = driver.Create(
        str(args.output), nir_ds.RasterXSize, nir_ds.RasterYSize, 1, gdal.GDT_Float32,
        options=["COMPRESS=DEFLATE", "TILED=YES"],
    )
    output.SetGeoTransform(nir_ds.GetGeoTransform())
    output.SetProjection(nir_ds.GetProjection())
    output.GetRasterBand(1).WriteArray(observed)
    output.GetRasterBand(1).SetNoDataValue(-9999)
    output = None

    project_ds = gdal.Open(str(args.project_raster))
    project = project_ds.ReadAsArray().astype("float32")
    valid = (observed != -9999) & (project != -9999) & np.isfinite(observed) & np.isfinite(project)
    difference = np.abs(observed[valid] - project[valid])
    report = {
        "scene_id": metadata["scene_id"],
        "datetime": metadata["datetime"],
        "valid_pixels": int(valid.sum()),
        "observearth_mean": float(observed[valid].mean()),
        "project_mean": float(project[valid].mean()),
        "mean_absolute_difference": float(difference.mean()),
        "maximum_absolute_difference": float(difference.max()),
        "equivalent_at_1e_6": bool(np.allclose(observed[valid], project[valid], atol=1e-6, rtol=0)),
        "observearth_raster": str(args.output),
        "project_raster": str(args.project_raster),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["equivalent_at_1e_6"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
