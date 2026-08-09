#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("PROJ_DATA", "/Applications/QGIS.app/Contents/Resources/qgis/proj")

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsMapRendererCustomPainterJob,
    QgsMapSettings,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/project.example.json"


def main() -> int:
    QgsApplication.setPrefixPath("/Applications/QGIS.app/Contents/MacOS", True)

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    project_path = ROOT / config["qgis"]["project_file"]
    aoi_path = ROOT / config["paths"]["selected_field_area"]
    point_path = ROOT / config["paths"]["selected_field_point"]
    project_path.parent.mkdir(parents=True, exist_ok=True)

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        crs = QgsCoordinateReferenceSystem(config["qgis"]["target_crs"])
        if not crs.isValid():
            print(f"CRS is not valid: {config['qgis']['target_crs']}")
            return 1
        project.setCrs(crs)
        project.setTitle("water-regime-gis")

        if not aoi_path.exists() or not point_path.exists():
            print("Selected field does not exist yet. Choose a point on the map in the app first.")
            return 1

        layer = QgsVectorLayer(str(aoi_path), "Selected field working area", "ogr")
        if not layer.isValid():
            print(f"Layer is not valid: {aoi_path}")
            return 1
        point_layer = QgsVectorLayer(str(point_path), "Selected field point", "ogr")
        if not point_layer.isValid():
            print(f"Layer is not valid: {point_path}")
            return 1

        symbol = QgsFillSymbol.createSimple(
            {
                "color": "46,125,50,70",
                "outline_color": "20,83,45,255",
                "outline_width": "0.8",
            }
        )
        symbol.setColor(QColor(46, 125, 50, 70))
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        project.addMapLayer(layer)
        project.addMapLayer(point_layer)

        if not project.write(str(project_path)):
            print(f"Failed to write QGIS project: {project_path}")
            return 1

        preview_path = project_path.with_name("water_regime_gis_preview.png")
        render_preview(project, layer, preview_path)

        print("Demo QGIS project: OK")
        print(f"QGIS version: {Qgis.QGIS_VERSION}")
        print(f"Project: {project_path}")
        print(f"Preview: {preview_path}")
        print(f"Layer: {aoi_path}")
        print(f"Point: {point_path}")
        print(f"Project CRS: {project.crs().authid()}")
        return 0
    finally:
        app.exitQgis()


def render_preview(project: QgsProject, layer: QgsVectorLayer, output: Path) -> None:
    transform = QgsCoordinateTransform(layer.crs(), project.crs(), project)
    extent = transform.transformBoundingBox(layer.extent())
    extent.scale(1.25)

    image = QImage(QSize(1200, 800), QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor(245, 249, 247))

    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setDestinationCrs(project.crs())
    settings.setExtent(extent)
    settings.setOutputSize(image.size())
    settings.setBackgroundColor(QColor(245, 249, 247))

    painter = QPainter(image)
    job = QgsMapRendererCustomPainterJob(settings, painter)
    job.start()
    job.waitForFinished()
    painter.end()
    image.save(str(output), "PNG")


if __name__ == "__main__":
    raise SystemExit(main())
