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

from water_regime_gis.qgis_runtime import configure_qgis_environment

configure_qgis_environment()

from osgeo import gdal, osr
from water_regime_gis.project import selected_area_crs, utm_crs_for_lon_lat


CONFIG = ROOT / "configs/project.example.json"
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="
BANDS = {
    "Blue": "B02",
    "Green": "B03",
    "Red": "B04",
    "RedEdge": "B05",
    "NIR": "B08",
    "SWIR1": "B11",
}
FORMULAS = {
    "NDVI": ("NIR", "Red", lambda a, b: (a - b) / (a + b)),
    "NDMI": ("NIR", "SWIR1", lambda a, b: (a - b) / (a + b)),
    "NDWI": ("Green", "NIR", lambda a, b: (a - b) / (a + b)),
    "MNDWI": ("Green", "SWIR1", lambda a, b: (a - b) / (a + b)),
    "NDRE": ("NIR", "RedEdge", lambda a, b: (a - b) / (a + b)),
    "SAVI": ("NIR", "Red", lambda a, b: 1.5 * (a - b) / (a + b + 0.5)),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate Sentinel-2 indices for a GeoJSON area.")
    parser.add_argument("--area", type=Path)
    parser.add_argument("--interim", type=Path)
    parser.add_argument("--rasters", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--indices", nargs="+")
    parser.add_argument("--date-from", type=dt.date.fromisoformat)
    parser.add_argument("--date-to", type=dt.date.fromisoformat)
    parser.add_argument("--scene-id")
    return parser.parse_args()


def main() -> int:
    gdal.UseExceptions()
    for key, value in {
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
    }.items():
        gdal.SetConfigOption(key, value)
    args = parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    area_path = project_path(args.area) if args.area else ROOT / config["paths"]["selected_field_area"]
    if not area_path.exists():
        print("Selected field area does not exist.")
        return 1

    interim = project_path(args.interim) if args.interim else ROOT / "data/interim/satellite"
    rasters = project_path(args.rasters) if args.rasters else ROOT / config["paths"]["rasters"]
    interim.mkdir(parents=True, exist_ok=True)
    rasters.mkdir(parents=True, exist_ok=True)
    latest_scene_path = project_path(args.metadata) if args.metadata else interim / "latest_scene.json"
    report_path = project_path(args.report) if args.report else ROOT / config["paths"]["metrics_report"]

    items = search_items(config, area_path, args.date_from, args.date_to)
    if args.scene_id:
        items = [item for item in items if item.get("id") == args.scene_id]
    if not items:
        write_json(latest_scene_path, {"satellite_status": "no_scene_found", "indices": []})
        write_json(report_path, {"status": "no_scene_found", "generated_at": utc_now(), "indices": []})
        print("Satellite status: no_scene_found")
        print("Metrics report:", report_path)
        return 0

    item = sorted(items, key=lambda feature: float(feature["properties"].get("eo:cloud_cover") or 1000))[0]
    scene_dir = interim / safe_name(item["id"])
    scene_dir.mkdir(parents=True, exist_ok=True)
    target_crs = area_analysis_crs(area_path, config) if args.area else selected_area_crs(ROOT, config)
    band_paths = clip_bands(item, scene_dir, area_path, target_crs)
    indices = calculate_indices(band_paths, rasters, args.indices or config["satellite"]["indices"])
    metadata = {
        "satellite_status": "OK" if indices else "no_indices",
        "provider": config["satellite"]["provider"],
        "collection": config["satellite"]["collection"],
        "scene_id": item["id"],
        "datetime": item["properties"].get("datetime", ""),
        "cloud_cover": item["properties"].get("eo:cloud_cover", ""),
        "bands": {name: str(path.relative_to(ROOT)) for name, path in band_paths.items()},
        "analysis_crs": target_crs,
        "indices": indices,
    }
    write_json(latest_scene_path, metadata)
    report = {
        "status": metadata["satellite_status"],
        "generated_at": utc_now(),
        "area": str(area_path),
        "analysis_crs": target_crs,
        "scene_id": metadata["scene_id"],
        "scene_datetime": metadata["datetime"],
        "cloud_cover": metadata["cloud_cover"],
        "indices": indices,
    }
    write_json(report_path, report)
    print("Satellite status:", metadata["satellite_status"])
    print("Scene:", item["id"])
    print("Scene datetime:", metadata["datetime"])
    print("Cloud cover:", metadata["cloud_cover"])
    print("Indices:", ", ".join(index["name"] for index in indices))
    print("Metadata:", latest_scene_path)
    print("Metrics report:", report_path)
    return 0


def search_items(config: dict, area_path: Path, date_from=None, date_to=None) -> list[dict]:
    end = date_to or dt.datetime.now(dt.timezone.utc).date()
    start = date_from or end - dt.timedelta(days=int(config["satellite"]["date_range_days"]))
    payload = {
        "collections": [config["satellite"]["collection"]],
        "bbox": bbox(area_path),
        "datetime": f"{start.isoformat()}/{end.isoformat()}",
        "query": {"eo:cloud_cover": {"lt": float(config["satellite"]["max_cloud_cover"])}},
        "limit": 20,
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    }
    request = Request(
        STAC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "water-regime-gis"},
    )
    with urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8")).get("features", [])


def bbox(area_path: Path) -> list[float]:
    data = json.loads(area_path.read_text(encoding="utf-8"))
    coords = data["features"][0]["geometry"]["coordinates"][0]
    return [min(p[0] for p in coords), min(p[1] for p in coords), max(p[0] for p in coords), max(p[1] for p in coords)]


def project_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def area_analysis_crs(area_path: Path, config: dict) -> str:
    data = json.loads(area_path.read_text(encoding="utf-8"))
    properties = data["features"][0].get("properties", {})
    if properties.get("analysis_crs"):
        return properties["analysis_crs"]
    minx, miny, maxx, maxy = bbox(area_path)
    return utm_crs_for_lon_lat((minx + maxx) / 2, (miny + maxy) / 2)


def clip_bands(item: dict, scene_dir: Path, area_path: Path, target_crs: str) -> dict[str, Path]:
    paths = {}
    bounds = target_bounds(area_path, target_crs)
    for name, asset_name in BANDS.items():
        asset = item["assets"].get(asset_name)
        if not asset:
            continue
        output = scene_dir / f"{asset_name.lower()}_{name.lower()}.tif"
        remove_if_exists(output)
        signed = sign_href(asset["href"])
        dataset = gdal.Warp(
            str(output),
            signed,
            dstSRS=target_crs,
            outputBounds=bounds,
            cutlineDSName=str(area_path),
            cropToCutline=True,
            xRes=10,
            yRes=10,
            resampleAlg="bilinear",
            dstNodata=0,
            multithread=True,
        )
        if dataset is None:
            raise RuntimeError(f"Failed to clip Sentinel-2 band: {asset_name}")
        dataset = None
        paths[name] = output
    return paths


def target_bounds(area_path: Path, target_crs: str) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bbox(area_path)
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target = osr.SpatialReference()
    target.SetFromUserInput(target_crs)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source, target)
    points = [transform.TransformPoint(x, y) for x, y in [(minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)]]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def sign_href(href: str) -> str:
    request = Request(SIGN_URL + quote(href, safe=""), headers={"User-Agent": "water-regime-gis"})
    with urlopen(request, timeout=30) as response:
        return "/vsicurl/" + json.loads(response.read().decode("utf-8"))["href"]


def calculate_indices(bands: dict[str, Path], rasters: Path, wanted: list[str]) -> list[dict]:
    written = []
    for name in wanted:
        if name not in FORMULAS:
            continue
        left, right, formula = FORMULAS[name]
        if left not in bands or right not in bands:
            written.append({"name": name, "status": "missing_band", "path": ""})
            continue
        output = rasters / f"{name.lower()}.tif"
        remove_if_exists(output)
        metrics = write_index(name, bands[left], bands[right], output, formula)
        written.append({"name": name, "status": "OK", "path": str(output.relative_to(ROOT)), **metrics})
    return written


def write_index(name: str, left: Path, right: Path, output: Path, formula) -> dict:
    import numpy as np

    left_ds = gdal.Open(str(left))
    right_ds = gdal.Open(str(right))
    left_raw = left_ds.ReadAsArray()
    right_raw = right_ds.ReadAsArray()
    mask = (left_raw <= 0) | (right_raw <= 0)
    a = left_raw.astype("float32") / 10000.0
    b = right_raw.astype("float32") / 10000.0
    with np.errstate(divide="ignore", invalid="ignore"):
        result = formula(a, b)
    invalid = mask | ~np.isfinite(result)
    result[invalid] = -9999
    valid = result[~invalid]

    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(output), left_ds.RasterXSize, left_ds.RasterYSize, 1, gdal.GDT_Float32, options=["COMPRESS=DEFLATE", "TILED=YES"])
    ds.SetGeoTransform(left_ds.GetGeoTransform())
    ds.SetProjection(left_ds.GetProjection())
    band = ds.GetRasterBand(1)
    band.WriteArray(result)
    band.SetNoDataValue(-9999)
    band.SetDescription(name)
    band.FlushCache()
    ds = None
    return {
        "valid_pixel_count": int(valid.size),
        "nodata_pixel_count": int(invalid.sum()),
        "minimum": float(valid.min()) if valid.size else None,
        "maximum": float(valid.max()) if valid.size else None,
        "mean": float(valid.mean()) if valid.size else None,
        "standard_deviation": float(valid.std()) if valid.size else None,
    }


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
