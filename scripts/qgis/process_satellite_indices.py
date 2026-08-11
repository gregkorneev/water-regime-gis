#!/usr/bin/env python3
from __future__ import annotations

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


def main() -> int:
    gdal.UseExceptions()
    for key, value in {
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
    }.items():
        gdal.SetConfigOption(key, value)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    area_path = ROOT / config["paths"]["selected_field_area"]
    if not area_path.exists():
        print("Selected field area does not exist.")
        return 1

    interim = ROOT / "data/interim/satellite"
    rasters = ROOT / config["paths"]["rasters"]
    interim.mkdir(parents=True, exist_ok=True)
    rasters.mkdir(parents=True, exist_ok=True)
    latest_scene_path = interim / "latest_scene.json"

    items = search_items(config, area_path)
    if not items:
        write_json(latest_scene_path, {"satellite_status": "no_scene_found", "indices": []})
        print("Satellite status: no_scene_found")
        return 0

    item = sorted(items, key=lambda feature: float(feature["properties"].get("eo:cloud_cover") or 1000))[0]
    scene_dir = interim / safe_name(item["id"])
    scene_dir.mkdir(parents=True, exist_ok=True)
    band_paths = clip_bands(item, scene_dir, area_path, config["qgis"]["target_crs"])
    indices = calculate_indices(band_paths, rasters, config["satellite"]["indices"])
    true_color = write_true_color(band_paths, ROOT / config["paths"]["maps"], config["qgis"]["target_crs"])
    metadata = {
        "satellite_status": "OK" if indices else "no_indices",
        "provider": config["satellite"]["provider"],
        "collection": config["satellite"]["collection"],
        "scene_id": item["id"],
        "datetime": item["properties"].get("datetime", ""),
        "cloud_cover": item["properties"].get("eo:cloud_cover", ""),
        "bands": {name: str(path.relative_to(ROOT)) for name, path in band_paths.items()},
        "indices": indices,
        "true_color": true_color,
    }
    write_json(latest_scene_path, metadata)
    print("Satellite status:", metadata["satellite_status"])
    print("Scene:", item["id"])
    print("Scene datetime:", metadata["datetime"])
    print("Cloud cover:", metadata["cloud_cover"])
    print("Indices:", ", ".join(index["name"] for index in indices))
    if true_color.get("url"):
        print("True color:", true_color["url"])
    print("Metadata:", latest_scene_path)
    return 0


def search_items(config: dict, area_path: Path) -> list[dict]:
    end = dt.datetime.now(dt.timezone.utc).date()
    start = end - dt.timedelta(days=int(config["satellite"]["date_range_days"]))
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


def clip_bands(item: dict, scene_dir: Path, area_path: Path, target_crs: str) -> dict[str, Path]:
    paths = {}
    bounds = target_bounds(area_path, target_crs)
    for name, asset_name in BANDS.items():
        asset = item["assets"].get(asset_name)
        if not asset:
            continue
        output = scene_dir / f"{asset_name.lower()}_{name.lower()}.tif"
        signed = sign_href(asset["href"])
        gdal.Warp(
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
        write_index(name, bands[left], bands[right], output, formula)
        written.append({"name": name, "status": "OK", "path": str(output.relative_to(ROOT)), "url": f"/download/rasters/{name.lower()}.tif"})
    return written


def write_index(name: str, left: Path, right: Path, output: Path, formula) -> None:
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
    result[mask | ~np.isfinite(result)] = -9999

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


def write_true_color(bands: dict[str, Path], maps_dir: Path, target_crs: str) -> dict:
    import numpy as np

    required = ["Red", "Green", "Blue"]
    if any(name not in bands for name in required):
        return {"status": "missing_band"}
    maps_dir.mkdir(parents=True, exist_ok=True)
    red_ds = gdal.Open(str(bands["Red"]))
    arrays = [gdal.Open(str(bands[name])).ReadAsArray().astype("float32") for name in required]
    mask = np.zeros_like(arrays[0], dtype=bool)
    for array in arrays:
        mask |= array <= 0
    scaled = []
    for array in arrays:
        valid = array[~mask]
        high = float(np.percentile(valid, 98)) if valid.size else 3000.0
        high = max(high, 1000.0)
        scaled.append(np.clip((array / high) * 255.0, 0, 255).astype("uint8"))

    output = maps_dir / "latest_sentinel_true_color.png"
    bounds = wgs84_bounds(red_ds, target_crs)
    temp_tif = maps_dir / "latest_sentinel_true_color.tif"
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(temp_tif), red_ds.RasterXSize, red_ds.RasterYSize, 3, gdal.GDT_Byte, options=["COMPRESS=DEFLATE", "TILED=YES"])
    ds.SetGeoTransform(red_ds.GetGeoTransform())
    ds.SetProjection(red_ds.GetProjection())
    for index, array in enumerate(scaled, start=1):
        band = ds.GetRasterBand(index)
        band.WriteArray(array)
        band.FlushCache()
    ds = None
    gdal.Translate(str(output), str(temp_tif), format="PNG")
    return {
        "status": "OK",
        "path": str(output.relative_to(ROOT)),
        "url": "/satellite-true-color.png",
        "bounds": bounds,
    }


def wgs84_bounds(dataset, target_crs: str) -> list[list[float]]:
    transform = dataset.GetGeoTransform()
    width = dataset.RasterXSize
    height = dataset.RasterYSize
    corners = [
        (transform[0], transform[3]),
        (transform[0] + width * transform[1], transform[3]),
        (transform[0], transform[3] + height * transform[5]),
        (transform[0] + width * transform[1], transform[3] + height * transform[5]),
    ]
    source = osr.SpatialReference()
    source.SetFromUserInput(target_crs)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target = osr.SpatialReference()
    target.ImportFromEPSG(4326)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform_crs = osr.CoordinateTransformation(source, target)
    points = [transform_crs.TransformPoint(x, y) for x, y in corners]
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
