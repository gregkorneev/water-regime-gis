#!/usr/bin/env python3
"""Calculate SNAP-compatible Sentinel-2 FCover for saved field scenes."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.qgis_runtime import configure_qgis_environment

configure_qgis_environment()

from osgeo import gdal, ogr

from download_field_analysis import fetch_item, sign_href


DEFAULT_OUTPUT = ROOT / "outputs/imagery"
REQUIRED_STACK_BANDS = {"B03": 2, "B04": 3, "B05": 4, "B11": 6, "B12": 7}
EXTRA_ASSETS = ("B06", "B07", "B8A")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate Sentinel-2 FCover rasters for saved field scenes.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dataset", nargs="+", default=["sp"])
    parser.add_argument("--date-from", type=dt.date.fromisoformat)
    parser.add_argument("--date-to", type=dt.date.fromisoformat)
    parser.add_argument("--limit", type=int, help="Process at most N field/date records.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Self-test OK")
        return 0
    if args.date_from and args.date_to and args.date_to < args.date_from:
        raise ValueError("--date-to must not be earlier than --date-from")

    gdal.UseExceptions()
    output_root = args.output.expanduser().resolve()
    metadata_paths = sorted(
        path
        for dataset in args.dataset
        for path in (output_root / dataset).glob("*/*/metadata.json")
        if (args.date_from is None or path.parent.name >= args.date_from.isoformat())
        and (args.date_to is None or path.parent.name <= args.date_to.isoformat())
    )
    sources: dict[Path, object] = {}
    completed = errors = 0
    for index, metadata_path in enumerate(metadata_paths):
        if args.limit is not None and index >= args.limit:
            break
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        scene_dir = metadata_path.parent
        output = scene_dir / "sentinel_fcover.tif"
        label = f"{metadata['dataset']}/{metadata['field_id']}/{metadata['scene_date']}"
        if output.exists() and not args.overwrite:
            completed += 1
            print(f"SKIP {label}: {output.name}")
            continue
        try:
            source_path = Path(metadata["source"]).expanduser().resolve()
            source = sources.get(source_path)
            if source is None:
                source = ogr.Open(str(source_path))
                if source is None:
                    raise FileNotFoundError(f"Could not open GeoPackage: {source_path}")
                sources[source_path] = source
            layer = source.GetLayerByName(metadata["source_layer"])
            if layer is None:
                raise ValueError(f"Layer is missing: {source_path}:{metadata['source_layer']}")
            fid_column = layer.GetFIDColumn() or "fid"
            item = fetch_item(metadata["scene_id"])
            calculate_scene_fcover(
                item,
                scene_dir / "sentinel_analysis.tif",
                source_path,
                layer.GetName(),
                f'"{fid_column}" = {int(metadata["source_fid"])}',
                metadata["analysis_crs"],
                output,
            )
            completed += 1
            print(f"OK {label}: {output.name}")
        except Exception as exc:
            errors += 1
            print(f"ERROR {label}: {exc}")
            if args.fail_fast:
                raise
    print(f"Finished: {completed} ready, {errors} errors")
    return 1 if errors else 0


def calculate_scene_fcover(item: dict, analysis_path: Path, source_path: Path, layer_name: str, cutline_where: str, target_crs: str, output: Path) -> None:
    import numpy as np

    stack = gdal.Open(str(analysis_path))
    if stack is None or stack.RasterCount < max(REQUIRED_STACK_BANDS.values()):
        raise RuntimeError(f"Invalid analysis raster: {analysis_path}")
    arrays = {name: stack.GetRasterBand(number).ReadAsArray().astype("float32") / 10000.0 for name, number in REQUIRED_STACK_BANDS.items()}
    extra_paths = download_extra_bands(item, source_path, layer_name, cutline_where, target_crs, output.parent)
    try:
        arrays.update({name: gdal.Open(str(path)).ReadAsArray().astype("float32") / 10000.0 for name, path in extra_paths.items()})
        view_zenith, view_azimuth = viewing_angles(item["id"])
        properties = item["properties"]
        fcover = fcover_from_reflectance(
            arrays["B03"], arrays["B04"], arrays["B05"], arrays["B06"], arrays["B07"], arrays["B8A"], arrays["B11"], arrays["B12"],
            view_zenith, view_azimuth, float(properties["s2:mean_solar_zenith"]), float(properties["s2:mean_solar_azimuth"]),
        )
        invalid = np.zeros_like(fcover, dtype=bool)
        for values in arrays.values():
            invalid |= values <= 0
        invalid |= ~np.isfinite(fcover)
        write_fcover(output, stack, np.where(invalid, -9999.0, np.clip(fcover, 0.0, 1.0)))
    finally:
        for path in extra_paths.values():
            path.unlink(missing_ok=True)


def download_extra_bands(item: dict, source_path: Path, layer_name: str, cutline_where: str, target_crs: str, scene_dir: Path) -> dict[str, Path]:
    paths = {}
    try:
        for asset_name in EXTRA_ASSETS:
            asset = item.get("assets", {}).get(asset_name)
            if asset is None:
                raise RuntimeError(f"Scene has no {asset_name} asset")
            output = scene_dir / f"_fcover_{asset_name.lower()}.tif"
            output.unlink(missing_ok=True)
            dataset = gdal.Warp(str(output), sign_href(asset["href"]), dstSRS=target_crs, cutlineDSName=str(source_path), cutlineLayer=layer_name, cutlineWhere=cutline_where, cropToCutline=True, xRes=10, yRes=10, targetAlignedPixels=True, resampleAlg="bilinear", dstNodata=-9999, multithread=True)
            if dataset is None:
                raise RuntimeError(f"Failed to download {asset_name}")
            dataset = None
            paths[asset_name] = output
        return paths
    except Exception:
        for path in paths.values():
            path.unlink(missing_ok=True)
        raise


@lru_cache(maxsize=None)
def viewing_angles(item_id: str) -> tuple[float, float]:
    item = fetch_item(item_id)
    href = item["assets"]["granule-metadata"]["href"]
    with urlopen(sign_href(href).removeprefix("/vsicurl/"), timeout=60) as response:
        root = ET.fromstring(response.read())
    for element in root.iter():
        if element.tag.endswith("Mean_Viewing_Incidence_Angle") and element.attrib.get("bandId") == "8":
            values = {child.tag.rsplit("}", 1)[-1]: float(child.text) for child in element}
            return values["ZENITH_ANGLE"], values["AZIMUTH_ANGLE"]
    raise RuntimeError("B8A mean viewing angles are missing from granule metadata")


def fcover_from_reflectance(b03, b04, b05, b06, b07, b8a, b11, b12, view_zenith: float, view_azimuth: float, sun_zenith: float, sun_azimuth: float):
    import numpy as np

    values = [
        normalize(b03, 0, 0.253061520472), normalize(b04, 0, 0.290393577911), normalize(b05, 0, 0.305398915249),
        normalize(b06, 0.00663797254225, 0.608900395798), normalize(b07, 0.0139727270189, 0.753827384323), normalize(b8a, 0.0266901380821, 0.782011770669),
        normalize(b11, 0.0163880741923, 0.493761397883), normalize(b12, 0, 0.49302598446),
        normalize(math.cos(math.radians(view_zenith)), 0.918595400582, 0.999999999991), normalize(math.cos(math.radians(sun_zenith)), 0.342022871159, 0.936206429175), math.cos(math.radians(sun_azimuth - view_azimuth)),
    ]
    weights = np.array([
        [-1.45261652206, -0.156854264841, 0.124234528462, 0.235625516229, -1.8323910258, -0.217188969888, 5.06933958064, -0.887578008155, -1.0808468167, -0.0323167041864, -0.224476137359, -0.195523962947],
        [-1.70417477557, -0.220824927842, 1.28595395487, 0.703139486363, -1.34481216665, -1.96881267559, -1.45444681639, 1.02737560043, -0.12494641532, 0.0802762437265, -0.198705918577, 0.108527100527],
        [1.02168965849, -0.409688743281, 1.08858884766, 0.36284522554, 0.0369390509705, -0.348012590003, -2.0035261881, 0.0410357601757, 1.22373853174, -0.0124082778287, -0.282223364524, 0.0994993117557],
        [-0.498002810205, -0.188970957866, -0.0358621840833, 0.00551248528107, 1.35391570802, -0.739689896116, -2.21719530107, 0.313216124198, 1.5020168915, 1.21530490195, -0.421938358618, 1.48852484547],
        [-3.88922154789, 2.49293993709, -4.40511331388, -1.91062012624, -0.703174115575, -0.215104721138, -0.972151494818, -0.930752241278, 1.2143441876, -0.521665460192, -0.445755955598, 0.344111873777],
    ], dtype="float32")
    hidden = [np.tanh(sum(weight * value for weight, value in zip(row[1:], values)) + row[0]) for row in weights]
    output = -0.0967998147811 + sum(weight * value for weight, value in zip([0.23080586765, -0.333655484884, -0.499418292325, 0.0472484396749, -0.0798516540739], hidden))
    return 0.5 * (output + 1) * (0.999638214715 - 0.000181230723879) + 0.000181230723879


def normalize(values, minimum: float, maximum: float):
    return 2 * (values - minimum) / (maximum - minimum) - 1


def write_fcover(path: Path, reference, values) -> None:
    temporary = path.with_name(path.stem + ".part.tif")
    temporary.unlink(missing_ok=True)
    dataset = gdal.GetDriverByName("GTiff").Create(str(temporary), reference.RasterXSize, reference.RasterYSize, 1, gdal.GDT_Float32, options=["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"])
    dataset.SetGeoTransform(reference.GetGeoTransform())
    dataset.SetProjection(reference.GetProjection())
    band = dataset.GetRasterBand(1)
    band.WriteArray(values)
    band.SetNoDataValue(-9999.0)
    band.SetDescription("SNAP-compatible FCover")
    dataset = None
    path.unlink(missing_ok=True)
    temporary.replace(path)


def self_test() -> None:
    import numpy as np

    values = np.full((1, 1), 0.2, dtype="float32")
    result = fcover_from_reflectance(values, values, values, values, values, values, values, values, 3, 216, 32, 162)
    assert result.shape == (1, 1) and np.isfinite(result).all()


if __name__ == "__main__":
    raise SystemExit(main())
