#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import utm_crs_for_lon_lat
from water_regime_gis.qgis_runtime import configure_qgis_environment

configure_qgis_environment()

from osgeo import gdal, ogr, osr


CONFIG = ROOT / "configs/project.example.json"
DEFAULT_INPUTS = (Path("/Users/korneev/Desktop/KAA.gpkg"), Path("/Users/korneev/Desktop/SP.gpkg"))
DEFAULT_OUTPUT = ROOT / "outputs/imagery"
DEFAULT_DATE_FROM = dt.date(2026, 4, 1)
DEFAULT_DATE_TO = dt.date(2026, 8, 10)
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="
RGB_ASSETS = ("B04", "B03", "B02")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Sentinel-2 or Sentinel-1 imagery for GPKG fields.")
    parser.add_argument("--input", nargs="+", type=Path, default=list(DEFAULT_INPUTS))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--date-from", type=dt.date.fromisoformat, default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", type=dt.date.fromisoformat, default=DEFAULT_DATE_TO)
    parser.add_argument("--max-cloud", type=float)
    parser.add_argument("--collection", help="STAC collection; defaults to Sentinel-2 from project config.")
    parser.add_argument("--asset", nargs="+", help="Assets to download; defaults to B04 B03 B02.")
    parser.add_argument("--output-name", default="sentinel_true_color.tif")
    parser.add_argument("--no-cloud-filter", action="store_true", help="Do not apply eo:cloud_cover filter (for Sentinel-1).")
    parser.add_argument("--where", help="OGR attribute filter, for example: calculation_ready = 1")
    parser.add_argument("--limit", type=int, help="Process at most N fields across all inputs.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def main() -> int:
    gdal.UseExceptions()
    args = parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    start = args.date_from
    end = args.date_to
    if end < start:
        raise ValueError("--date-to must not be earlier than --date-from")
    max_cloud = args.max_cloud if args.max_cloud is not None else float(config["satellite"]["max_cloud_cover"])
    collection = args.collection or config["satellite"]["collection"]
    assets = tuple(args.asset or RGB_ASSETS)
    output_root = args.output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "download_manifest.json"
    records = []
    processed = 0
    total_fields = 0

    for source_path in args.input:
        source_path = source_path.expanduser().resolve()
        dataset = ogr.Open(str(source_path))
        if dataset is None:
            raise FileNotFoundError(f"Could not open GeoPackage: {source_path}")
        layer = dataset.GetLayer(0)
        if layer is None:
            raise ValueError(f"GeoPackage has no layers: {source_path}")
        if args.where:
            layer.SetAttributeFilter(args.where)
        total_fields += layer.GetFeatureCount()
        dataset_name = safe_name(source_path.stem).lower()
        fid_column = layer.GetFIDColumn() or "fid"
        source_crs = layer.GetSpatialRef()
        if source_crs is None:
            raise ValueError(f"Layer CRS is missing: {source_path}:{layer.GetName()}")
        source_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        for feature in layer:
            if args.limit is not None and processed >= args.limit:
                break
            processed += 1
            field_id = field_identifier(feature)
            field_dir = output_root / dataset_name / field_id
            try:
                geometry = feature.GetGeometryRef()
                if geometry is None or geometry.IsEmpty():
                    raise ValueError("Field geometry is empty")
                bbox, center = geometry_bbox_wgs84(geometry, source_crs)
                items = find_scenes(bbox, center, start, end, max_cloud, collection, assets, args.no_cloud_filter)
                target_crs = utm_crs_for_lon_lat(*center)
                cutline_where = f'"{fid_column}" = {feature.GetFID()}'
                for item in items:
                    scene_datetime = item["properties"].get("datetime", "")
                    scene_date = scene_datetime[:10]
                    scene_dir = field_dir / scene_date
                    output_path = scene_dir / args.output_name
                    metadata_path = scene_dir / "metadata.json"
                    if output_path.exists() and metadata_path.exists() and not args.overwrite:
                        record = json.loads(metadata_path.read_text(encoding="utf-8"))
                        record["status"] = "skipped_existing"
                        records.append(record)
                        print(f"SKIP {dataset_name}/{field_id}/{scene_date}: {output_path}")
                        continue
                    try:
                        scene_dir.mkdir(parents=True, exist_ok=True)
                        band_paths = download_bands(
                            item,
                            source_path,
                            layer.GetName(),
                            cutline_where,
                            target_crs,
                            scene_dir,
                            assets,
                        )
                        if assets == RGB_ASSETS:
                            write_true_color(band_paths, output_path)
                        else:
                            write_multiband(band_paths, assets, output_path)
                        for path in band_paths:
                            path.unlink(missing_ok=True)
                        record = {
                            "status": "OK",
                            "dataset": dataset_name,
                            "field_id": field_id,
                            "source": str(source_path),
                            "source_layer": layer.GetName(),
                            "source_fid": feature.GetFID(),
                            "scene_id": item["id"],
                            "scene_date": scene_date,
                            "scene_datetime": scene_datetime,
                            "cloud_cover": item["properties"].get("eo:cloud_cover"),
                            "collection": collection,
                            "assets": list(assets),
                            "analysis_crs": target_crs,
                            "output": str(output_path),
                        }
                        metadata_path.write_text(
                            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                        )
                        records.append(record)
                        print(f"OK {dataset_name}/{field_id}/{scene_date}: {output_path}")
                    except Exception as exc:
                        record = {
                            "status": "error",
                            "dataset": dataset_name,
                            "field_id": field_id,
                            "source": str(source_path),
                            "source_fid": feature.GetFID(),
                            "scene_id": item["id"],
                            "scene_date": scene_date,
                            "error": str(exc),
                        }
                        records.append(record)
                        print(f"ERROR {dataset_name}/{field_id}/{scene_date}: {exc}")
                        if args.fail_fast:
                            write_manifest(manifest_path, records, start, end, max_cloud)
                            raise
                    write_manifest(manifest_path, records, start, end, max_cloud)
            except Exception as exc:
                record = {
                    "status": "error",
                    "dataset": dataset_name,
                    "field_id": field_id,
                    "source": str(source_path),
                    "source_fid": feature.GetFID(),
                    "error": str(exc),
                }
                records.append(record)
                print(f"ERROR {dataset_name}/{field_id}: {exc}")
                if args.fail_fast:
                    write_manifest(manifest_path, records, start, end, max_cloud)
                    raise
            write_manifest(manifest_path, records, start, end, max_cloud)
            print_progress(processed, min(total_fields, args.limit) if args.limit is not None else total_fields)

        dataset = None
        if args.limit is not None and processed >= args.limit:
            break

    ok = sum(record["status"] in {"OK", "skipped_existing"} for record in records)
    errors = sum(record["status"] == "error" for record in records)
    if processed:
        print()
    print(f"Finished: {ok} ready, {errors} errors")
    print(f"Manifest: {manifest_path}")
    return 1 if errors else 0


def field_identifier(feature) -> str:
    for field_name in ("field_external_key", "field_code_raw", "source_fid"):
        index = feature.GetFieldIndex(field_name)
        if index >= 0:
            value = str(feature.GetField(index) or "").strip()
            if value:
                return safe_name(value)
    return f"fid_{feature.GetFID()}"


def geometry_bbox_wgs84(geometry, source_crs) -> tuple[list[float], tuple[float, float]]:
    geometry = geometry.Clone()
    target = osr.SpatialReference()
    target.ImportFromEPSG(4326)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    if not source_crs.IsSame(target):
        geometry.Transform(osr.CoordinateTransformation(source_crs, target))
    minx, maxx, miny, maxy = geometry.GetEnvelope()
    centroid = geometry.Centroid()
    return [minx, miny, maxx, maxy], (centroid.GetX(), centroid.GetY())


def find_scenes(
    bbox: list[float],
    center: tuple[float, float],
    start: dt.date,
    end: dt.date,
    max_cloud: float,
    collection: str,
    assets: tuple[str, ...],
    no_cloud_filter: bool,
) -> list[dict]:
    payload = {
        "collections": [collection],
        "bbox": bbox,
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": 1000,
    }
    if not no_cloud_filter:
        payload["query"] = {"eo:cloud_cover": {"lt": max_cloud}}
    request = Request(
        STAC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "water-regime-gis"},
    )
    with urlopen(request, timeout=40) as response:
        items = json.loads(response.read().decode("utf-8")).get("features", [])
    if not items:
        raise RuntimeError("No Sentinel-2 scenes found for the field and date range")
    covering = [item for item in items if bbox_contains(item.get("bbox", []), center)]
    candidates = covering or items
    by_date = {}
    for item in sorted(candidates, key=scene_quality):
        scene_date = item["properties"].get("datetime", "")[:10]
        if scene_date and all(asset in item.get("assets", {}) for asset in assets):
            by_date.setdefault(scene_date, item)
    if not by_date:
        raise RuntimeError(f"{collection} scenes have none of the requested assets: {', '.join(assets)}")
    return [by_date[scene_date] for scene_date in sorted(by_date)]


def bbox_contains(item_bbox: list[float], point: tuple[float, float]) -> bool:
    return len(item_bbox) >= 4 and item_bbox[0] <= point[0] <= item_bbox[2] and item_bbox[1] <= point[1] <= item_bbox[3]


def cloud_cover(item: dict) -> float:
    value = item.get("properties", {}).get("eo:cloud_cover")
    return float(value) if value is not None else 1000.0


def scene_quality(item: dict) -> tuple[float, float, float]:
    properties = item.get("properties", {})
    degraded = properties.get("s2:degraded_msi_data_percentage")
    nodata = properties.get("s2:nodata_pixel_percentage")
    return (
        float(degraded) if degraded is not None else 0.0,
        cloud_cover(item),
        float(nodata) if nodata is not None else 0.0,
    )


def download_bands(
    item: dict,
    source_path: Path,
    layer_name: str,
    cutline_where: str,
    target_crs: str,
    field_dir: Path,
    assets: tuple[str, ...],
) -> list[Path]:
    paths = []
    try:
        for asset_name in assets:
            asset = item["assets"].get(asset_name)
            if asset is None:
                raise RuntimeError(f"Scene has no {asset_name} asset")
            output = field_dir / f"_{asset_name.lower()}.tif"
            output.unlink(missing_ok=True)
            paths.append(output)
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
                resampleAlg="bilinear",
                dstNodata=0,
                multithread=True,
            )
            if dataset is None:
                raise RuntimeError(f"Failed to download {asset_name}")
            dataset = None
        return paths
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise


def sign_href(href: str) -> str:
    request = Request(SIGN_URL + quote(href, safe=""), headers={"User-Agent": "water-regime-gis"})
    with urlopen(request, timeout=30) as response:
        return "/vsicurl/" + json.loads(response.read().decode("utf-8"))["href"]


def write_true_color(band_paths: list[Path], output: Path) -> None:
    import numpy as np

    datasets = [gdal.Open(str(path)) for path in band_paths]
    arrays = [dataset.ReadAsArray().astype("float32") for dataset in datasets]
    invalid = np.logical_or.reduce([array <= 0 for array in arrays])
    valid = np.concatenate([array[~invalid] for array in arrays])
    low, high = np.percentile(valid, (2, 98)) if valid.size else (0.0, 3000.0)
    if high <= low:
        high = low + 1
    rendered = [np.power(np.clip((array - low) / (high - low), 0, 1), 0.9) * 255 for array in arrays]
    output.unlink(missing_ok=True)
    result = gdal.GetDriverByName("GTiff").Create(
        str(output),
        datasets[0].RasterXSize,
        datasets[0].RasterYSize,
        3,
        gdal.GDT_Byte,
        options=["COMPRESS=DEFLATE", "TILED=YES"],
    )
    result.SetGeoTransform(datasets[0].GetGeoTransform())
    result.SetProjection(datasets[0].GetProjection())
    interpretations = (gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand)
    for index, (array, interpretation) in enumerate(zip(rendered, interpretations), start=1):
        array[invalid] = 0
        band = result.GetRasterBand(index)
        band.WriteArray(array.astype("uint8"))
        band.SetNoDataValue(0)
        band.SetColorInterpretation(interpretation)
    result = None


def write_multiband(band_paths: list[Path], asset_names: tuple[str, ...], output: Path) -> None:
    datasets = [gdal.Open(str(path)) for path in band_paths]
    if any(dataset is None for dataset in datasets):
        raise RuntimeError("Could not open downloaded raster bands")
    output.unlink(missing_ok=True)
    result = gdal.GetDriverByName("GTiff").Create(
        str(output),
        datasets[0].RasterXSize,
        datasets[0].RasterYSize,
        len(datasets),
        gdal.GDT_Float32,
        options=["COMPRESS=DEFLATE", "TILED=YES"],
    )
    result.SetGeoTransform(datasets[0].GetGeoTransform())
    result.SetProjection(datasets[0].GetProjection())
    for index, (dataset, asset_name) in enumerate(zip(datasets, asset_names), start=1):
        band = result.GetRasterBand(index)
        band.WriteArray(dataset.ReadAsArray().astype("float32"))
        band.SetDescription(asset_name.upper())
        band.SetNoDataValue(0)
    result = None


def write_manifest(path: Path, records: list[dict], start: dt.date, end: dt.date, max_cloud: float) -> None:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "max_cloud_cover": max_cloud,
        "fields": records,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in value.strip())
    return cleaned[:120] or "field"


def print_progress(current: int, total: int) -> None:
    if not total:
        return
    width = 24
    filled = round(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r[{bar}] {current}/{total} полей ({current / total:.0%})", end="", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
