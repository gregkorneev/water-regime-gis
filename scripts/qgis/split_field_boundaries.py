#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from water_regime_gis.project import utm_crs_for_lon_lat
from water_regime_gis.qgis_runtime import configure_qgis_environment, qgis_prefix_path

configure_qgis_environment()

from qgis.PyQt.QtCore import QMetaType
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)


DEFAULT_INPUT = Path("/Users/korneev/Desktop/kornix_field_boundaries_import_20260530_v2.geojson")
DEFAULT_OUTPUT_DIR = ROOT / "data/processed/field_boundaries"
DATASET_CODES = ("SP", "KAA")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split SP/KAA fields and build a minimum rectangle for each field.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def memory_layer(name: str, crs: QgsCoordinateReferenceSystem, fields, rectangle: bool = False) -> QgsVectorLayer:
    layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", name, "memory")
    output_fields = list(fields)
    if rectangle:
        output_fields.extend(
            [
                QgsField("rectangle_area_ha", QMetaType.Type.Double),
                QgsField("rectangle_angle_deg", QMetaType.Type.Double),
                QgsField("rectangle_width_m", QMetaType.Type.Double),
                QgsField("rectangle_height_m", QMetaType.Type.Double),
                QgsField("rectangle_crs", QMetaType.Type.QString),
            ]
        )
    layer.dataProvider().addAttributes(output_fields)
    layer.updateFields()
    return layer


def minimum_rectangle(geometry: QgsGeometry, source_crs: QgsCoordinateReferenceSystem, context):
    center = geometry.centroid().asPoint()
    rectangle_crs = QgsCoordinateReferenceSystem(utm_crs_for_lon_lat(center.x(), center.y()))
    to_metric = QgsCoordinateTransform(source_crs, rectangle_crs, context)
    to_source = QgsCoordinateTransform(rectangle_crs, source_crs, context)

    projected = QgsGeometry(geometry)
    projected.transform(to_metric)
    rectangle, area, angle, width, height = projected.orientedMinimumBoundingBox()
    uncovered_area = projected.difference(rectangle).area()
    if uncovered_area > max(projected.area() * 1e-9, 0.01):
        raise ValueError(f"Minimum rectangle does not cover source geometry: {uncovered_area:.6f} m2")
    rectangle.transform(to_source)
    return rectangle, area / 10_000, angle, width, height, rectangle_crs.authid()


def write_geojson(layer: QgsVectorLayer, path: Path) -> None:
    layer.updateExtents()
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GeoJSON"
    options.fileEncoding = "UTF-8"
    error, _, _, message = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        str(path),
        QgsProject.instance().transformContext(),
        options,
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Could not write {path}: {message}")


def main() -> int:
    args = parse_args()
    source_path = args.input.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source_path.is_file():
        print(f"Input GeoJSON does not exist: {source_path}")
        return 1

    QgsApplication.setPrefixPath(str(qgis_prefix_path()), True)
    app = QgsApplication([], False)
    app.initQgis()
    source = None
    splits = {}
    rectangles = {}
    feature = split_feature = rectangle_feature = geometry = rectangle_geometry = None
    try:
        source = QgsVectorLayer(str(source_path), "Field boundaries", "ogr")
        if not source.isValid():
            print(f"Invalid input vector layer: {source_path}")
            return 1
        if source.crs().authid() != "EPSG:4326":
            print(f"Expected EPSG:4326 input, got: {source.crs().authid()}")
            return 1
        if source.fields().indexOf("dataset_code") < 0:
            print("Required attribute is missing: dataset_code")
            return 1

        output_dir.mkdir(parents=True, exist_ok=True)
        splits = {code: memory_layer(f"{code} fields", source.crs(), source.fields()) for code in DATASET_CODES}
        rectangles = {
            code: memory_layer(f"{code} minimum rectangles", source.crs(), source.fields(), rectangle=True)
            for code in DATASET_CODES
        }
        counts = {code: 0 for code in DATASET_CODES}
        context = QgsProject.instance().transformContext()

        for feature in source.getFeatures():
            code = str(feature["dataset_code"] or "").strip().upper()
            if code not in DATASET_CODES:
                raise ValueError(f"Unexpected dataset_code for feature {feature.id()}: {code!r}")
            geometry = feature.geometry()
            if geometry.isNull() or geometry.isEmpty():
                raise ValueError(f"Empty geometry for feature {feature.id()}")

            split_feature = QgsFeature(splits[code].fields())
            split_feature.setAttributes(feature.attributes())
            split_feature.setGeometry(geometry)
            if not splits[code].dataProvider().addFeature(split_feature):
                raise RuntimeError(f"Could not add source feature {feature.id()} to {code}")

            rectangle_geometry, area_ha, angle, width, height, rectangle_crs = minimum_rectangle(
                geometry, source.crs(), context
            )
            rectangle_feature = QgsFeature(rectangles[code].fields())
            rectangle_feature.setAttributes(
                feature.attributes() + [area_ha, angle, width, height, rectangle_crs]
            )
            rectangle_feature.setGeometry(rectangle_geometry)
            if not rectangles[code].dataProvider().addFeature(rectangle_feature):
                raise RuntimeError(f"Could not add rectangle for feature {feature.id()} to {code}")
            counts[code] += 1

        if sum(counts.values()) != source.featureCount() or any(count == 0 for count in counts.values()):
            raise ValueError(f"Split count mismatch: source={source.featureCount()}, groups={counts}")

        for code in DATASET_CODES:
            slug = code.lower()
            write_geojson(splits[code], output_dir / f"{slug}_fields.geojson")
            write_geojson(rectangles[code], output_dir / f"{slug}_minimum_rectangles.geojson")
            print(f"{code}: {counts[code]} fields, {counts[code]} rectangles")
        print(f"Output directory: {output_dir}")
        return 0
    finally:
        source = feature = split_feature = rectangle_feature = geometry = rectangle_geometry = None
        splits.clear()
        rectangles.clear()
        QgsProject.instance().clear()
        gc.collect()
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
