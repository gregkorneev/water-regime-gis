#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from functools import lru_cache
from pathlib import Path
from time import time
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import configure_qgis_environment

configure_qgis_environment()

from osgeo import gdal, ogr


DEFAULT_OUTPUT = ROOT / "outputs/imagery"
ITEM_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a/items/"
SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="
SIGNED_HREF_TTL_SECONDS = 30 * 60
ANALYSIS_ASSETS = ("B02", "B03", "B04", "B05", "B08", "B11", "B12", "SCL")
CLOUD_SCL_CLASSES = (3, 8, 9, 10, 11)
INVALID_SCL_CLASSES = (0, 1, *CLOUD_SCL_CLASSES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Sentinel-2 analysis bands and SCL for existing field imagery."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dataset", nargs="+", default=["kaa", "sp"])
    parser.add_argument("--limit", type=int, help="Process at most N field/date records.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def main() -> int:
    gdal.UseExceptions()
    for key, value in {
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
        "VSI_CACHE": "TRUE",
    }.items():
        gdal.SetConfigOption(key, value)

    args = parse_args()
    output_root = args.output.expanduser().resolve()
    manifest_path = output_root / "analysis_manifest.json"
    metadata_paths = sorted(
        path
        for dataset in args.dataset
        for path in (output_root / dataset).glob("*/*/metadata.json")
    )
    records = []
    sources = {}

    for index, metadata_path in enumerate(metadata_paths):
        if args.limit is not None and index >= args.limit:
            break
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        scene_dir = metadata_path.parent
        analysis_path = scene_dir / "sentinel_analysis.tif"
        mask_path = scene_dir / "cloud_mask.tif"
        label = f"{metadata['dataset']}/{metadata['field_id']}/{metadata['scene_date']}"
        if analysis_ready(analysis_path, mask_path) and not args.overwrite:
            record = analysis_record(metadata, analysis_path, mask_path, "skipped_existing")
            records.append(record)
            print(f"SKIP {label}: {analysis_path}")
            write_manifest(manifest_path, records)
            continue

        try:
            source_path = Path(metadata["source"]).expanduser().resolve()
            dataset = sources.get(source_path)
            if dataset is None:
                dataset = ogr.Open(str(source_path))
                if dataset is None:
                    raise FileNotFoundError(f"Could not open GeoPackage: {source_path}")
                sources[source_path] = dataset
            layer = dataset.GetLayerByName(metadata["source_layer"])
            if layer is None:
                raise ValueError(f"Layer is missing: {source_path}:{metadata['source_layer']}")
            fid_column = layer.GetFIDColumn() or "fid"
            cutline_where = f'"{fid_column}" = {int(metadata["source_fid"])}'
            item = fetch_item(metadata["scene_id"])
            band_paths = download_bands(
                item,
                source_path,
                layer.GetName(),
                cutline_where,
                metadata["analysis_crs"],
                scene_dir,
            )
            try:
                write_analysis_stack(band_paths, analysis_path)
                aoi_cloud_cover = write_cloud_mask(band_paths["SCL"], mask_path)
            finally:
                for path in band_paths.values():
                    path.unlink(missing_ok=True)

            metadata.update(
                {
                    "analysis_status": "OK",
                    "analysis_output": str(analysis_path),
                    "analysis_bands": list(ANALYSIS_ASSETS),
                    "cloud_mask": str(mask_path),
                    "aoi_cloud_cover": aoi_cloud_cover,
                }
            )
            write_json(metadata_path, metadata)
            record = analysis_record(metadata, analysis_path, mask_path, "OK")
            records.append(record)
            print(f"OK {label}: {analysis_path} (AOI clouds {aoi_cloud_cover:.1f}%)")
        except Exception as exc:
            record = {
                "status": "error",
                "dataset": metadata.get("dataset"),
                "field_id": metadata.get("field_id"),
                "scene_id": metadata.get("scene_id"),
                "scene_date": metadata.get("scene_date"),
                "error": str(exc),
            }
            records.append(record)
            print(f"ERROR {label}: {exc}")
            if args.fail_fast:
                write_manifest(manifest_path, records)
                raise
        write_manifest(manifest_path, records)

    ready = sum(record["status"] in {"OK", "skipped_existing"} for record in records)
    errors = sum(record["status"] == "error" for record in records)
    print(f"Finished: {ready} ready, {errors} errors")
    print(f"Manifest: {manifest_path}")
    return 1 if errors else 0


@lru_cache(maxsize=None)
def fetch_item(scene_id: str) -> dict:
    request = Request(ITEM_URL + quote(scene_id), headers={"User-Agent": "water-regime-gis"})
    with urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


@lru_cache(maxsize=None)
def _sign_href(href: str, time_bucket: int) -> str:
    request = Request(SIGN_URL + quote(href, safe=""), headers={"User-Agent": "water-regime-gis"})
    with urlopen(request, timeout=30) as response:
        return "/vsicurl/" + json.loads(response.read().decode("utf-8"))["href"]


def sign_href(href: str) -> str:
    return _sign_href(href, int(time() // SIGNED_HREF_TTL_SECONDS))


def download_bands(
    item: dict,
    source_path: Path,
    layer_name: str,
    cutline_where: str,
    target_crs: str,
    scene_dir: Path,
) -> dict[str, Path]:
    paths = {}
    try:
        for asset_name in ANALYSIS_ASSETS:
            asset = item.get("assets", {}).get(asset_name)
            if asset is None:
                raise RuntimeError(f"Scene has no {asset_name} asset")
            output = scene_dir / f"_analysis_{asset_name.lower()}.tif"
            output.unlink(missing_ok=True)
            paths[asset_name] = output
            dataset = gdal.Warp(
                str(output),
                sign_href(asset["href"]),
                dstSRS=target_crs,
                cutlineDSName=str(source_path),
                cutlineLayer=layer_name,
                cutlineWhere=cutline_where,
                cropToCutline=True,
                xRes=10,
                yRes=10,
                targetAlignedPixels=True,
                resampleAlg="near" if asset_name == "SCL" else "bilinear",
                dstNodata=0,
                multithread=True,
            )
            if dataset is None:
                raise RuntimeError(f"Failed to download {asset_name}")
            dataset = None
        return paths
    except Exception:
        for path in paths.values():
            path.unlink(missing_ok=True)
        raise


def write_analysis_stack(band_paths: dict[str, Path], output: Path) -> None:
    datasets = [gdal.Open(str(band_paths[name])) for name in ANALYSIS_ASSETS]
    reference = datasets[0]
    if any(
        dataset.RasterXSize != reference.RasterXSize or dataset.RasterYSize != reference.RasterYSize
        for dataset in datasets[1:]
    ):
        raise RuntimeError("Analysis bands do not share the same raster grid")

    temporary = output.with_name(output.stem + ".part.tif")
    temporary.unlink(missing_ok=True)
    result = gdal.GetDriverByName("GTiff").Create(
        str(temporary),
        reference.RasterXSize,
        reference.RasterYSize,
        len(ANALYSIS_ASSETS),
        gdal.GDT_UInt16,
        options=["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES"],
    )
    result.SetGeoTransform(reference.GetGeoTransform())
    result.SetProjection(reference.GetProjection())
    for band_number, (asset_name, dataset) in enumerate(zip(ANALYSIS_ASSETS, datasets), start=1):
        band = result.GetRasterBand(band_number)
        band.WriteArray(dataset.ReadAsArray())
        band.SetNoDataValue(0)
        band.SetDescription(asset_name)
        if asset_name != "SCL":
            band.SetScale(0.0001)
            band.SetUnitType("surface reflectance")
    result = None
    output.unlink(missing_ok=True)
    temporary.replace(output)


def write_cloud_mask(scl_path: Path, output: Path) -> float:
    import numpy as np

    dataset = gdal.Open(str(scl_path))
    scl = dataset.ReadAsArray()
    invalid = np.isin(scl, INVALID_SCL_CLASSES)
    valid_data = scl > 0
    cloud = np.isin(scl, CLOUD_SCL_CLASSES)
    denominator = int(valid_data.sum())
    cloud_cover = float(cloud.sum() * 100.0 / denominator) if denominator else 100.0

    temporary = output.with_name(output.stem + ".part.tif")
    temporary.unlink(missing_ok=True)
    result = gdal.GetDriverByName("GTiff").Create(
        str(temporary),
        dataset.RasterXSize,
        dataset.RasterYSize,
        1,
        gdal.GDT_Byte,
        options=["COMPRESS=DEFLATE", "TILED=YES"],
    )
    result.SetGeoTransform(dataset.GetGeoTransform())
    result.SetProjection(dataset.GetProjection())
    band = result.GetRasterBand(1)
    band.WriteArray(invalid.astype("uint8"))
    band.SetNoDataValue(1)
    band.SetDescription("Invalid pixels: no data, saturation, cloud shadow, cloud, cirrus, snow/ice")
    result = None
    output.unlink(missing_ok=True)
    temporary.replace(output)
    return cloud_cover


def analysis_ready(analysis_path: Path, mask_path: Path) -> bool:
    if not analysis_path.exists() or not mask_path.exists():
        return False
    dataset = gdal.Open(str(analysis_path))
    return dataset is not None and dataset.RasterCount == len(ANALYSIS_ASSETS)


def analysis_record(metadata: dict, analysis_path: Path, mask_path: Path, status: str) -> dict:
    return {
        "status": status,
        "dataset": metadata["dataset"],
        "field_id": metadata["field_id"],
        "scene_id": metadata["scene_id"],
        "scene_date": metadata["scene_date"],
        "analysis_output": str(analysis_path),
        "cloud_mask": str(mask_path),
        "aoi_cloud_cover": metadata.get("aoi_cloud_cover"),
    }


def write_manifest(path: Path, records: list[dict]) -> None:
    write_json(
        path,
        {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "analysis_bands": list(ANALYSIS_ASSETS),
            "cloud_scl_classes": list(CLOUD_SCL_CLASSES),
            "fields": records,
        },
    )


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
