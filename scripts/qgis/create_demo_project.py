#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("PROJ_DATA", "/Applications/QGIS.app/Contents/Resources/qgis/proj")

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtNetwork import QNetworkRequest, QSslCertificate
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsBookmark,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsMapRendererCustomPainterJob,
    QgsMapSettings,
    QgsMarkerSymbol,
    QgsNetworkAccessManager,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/project.example.json"


def main() -> int:
    QgsApplication.setPrefixPath("/Applications/QGIS.app", True)

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
        osm_layer = add_osm_layer(project)
        nspd_layer = add_nspd_parcels_layer(project, config)
        project.addMapLayer(layer)
        project.addMapLayer(point_layer)
        set_point_style(point_layer)
        set_start_extent(project, layer)
        add_field_bookmark(project, layer)
        order_layers(project, [point_layer, layer, nspd_layer, osm_layer])

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


def add_osm_layer(project: QgsProject) -> QgsRasterLayer | None:
    uri = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0"
    layer = QgsRasterLayer(uri, "OpenStreetMap", "wms")
    if layer.isValid():
        project.addMapLayer(layer)
        return layer
    print("OpenStreetMap XYZ layer was not added: QGIS marked it invalid.")
    return None


def add_nspd_parcels_layer(project: QgsProject, config: dict) -> QgsRasterLayer | None:
    nspd = config.get("nspd", {})
    layer_id = nspd.get("parcels_wms_layer_id", 36048)
    name = nspd.get("parcels_wms_name", "Земельные участки из ЕГРН")
    wms_url = nspd.get("local_wms_proxy_url") or f"https://nspd.gov.ru/api/aeggis/v3/{layer_id}/wms"
    if wms_url.startswith("https://nspd.gov.ru/"):
        install_nspd_request_hook(config)
    uri = (
        "contextualWMSLegend=0&crs=EPSG:3857&dpiMode=7&featureCount=10&format=image/png"
        f"&layers={layer_id}&styles="
        "&IgnoreGetMapUrl=1"
        f"&url={wms_url}"
    )
    layer = QgsRasterLayer(uri, name, "wms")
    if layer.isValid():
        project.addMapLayer(layer)
        return layer
    else:
        print("NSPD parcels WMS layer was not added: QGIS marked it invalid. Install/check the Rosreestr NSPD plugin.")
        return None


def set_point_style(layer: QgsVectorLayer) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "255,87,34,255",
            "outline_color": "255,255,255,255",
            "outline_width": "0.8",
            "size": "4",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def set_start_extent(project: QgsProject, layer: QgsVectorLayer) -> None:
    transform = QgsCoordinateTransform(layer.crs(), project.crs(), project)
    extent = transform.transformBoundingBox(layer.extent())
    extent.scale(1.35)
    referenced_extent = QgsReferencedRectangle(extent, project.crs())
    project.viewSettings().setDefaultViewExtent(referenced_extent)
    project.viewSettings().setPresetFullExtent(referenced_extent)


def add_field_bookmark(project: QgsProject, layer: QgsVectorLayer) -> None:
    transform = QgsCoordinateTransform(layer.crs(), project.crs(), project)
    extent = transform.transformBoundingBox(layer.extent())
    extent.scale(1.35)
    bookmark = QgsBookmark()
    bookmark.setName("Selected field")
    bookmark.setGroup("water-regime-gis")
    bookmark.setExtent(QgsReferencedRectangle(extent, project.crs()))
    project.bookmarkManager().addBookmark(bookmark)


def order_layers(project: QgsProject, layers: list[object | None]) -> None:
    root = project.layerTreeRoot()
    for layer in reversed(layers):
        if layer is None:
            continue
        node = root.findLayer(layer.id())
        if node:
            clone = node.clone()
            root.insertChildNode(0, clone)
            root.removeChildNode(node)


def install_nspd_request_hook(config: dict) -> None:
    cert_path = nspd_plugin_dir(config) / "certs/nspd-ca-bundle.pem"
    if not cert_path.exists():
        print("NSPD request hook was not installed: plugin certificate bundle was not found.")
        return

    nspd_ca_certs = QSslCertificate.fromPath(str(cert_path))
    if not nspd_ca_certs:
        print("NSPD request hook was not installed: plugin certificate bundle is empty.")
        return

    def preprocessor(request):
        url = request.url()
        if url.scheme().lower() != "https" or not is_nspd_host(url.host()):
            return ""

        ssl_config = request.sslConfiguration()
        ssl_config.setCaCertificates(ssl_config.caCertificates() + nspd_ca_certs)
        request.setSslConfiguration(ssl_config)
        request.setAttribute(QNetworkRequest.Http2AllowedAttribute, False)
        request.setRawHeader(
            b"User-Agent",
            b"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
        )
        request.setRawHeader(b"Referer", b"https://nspd.gov.ru/map?active_layers=%E8%B3%90")
        return ""

    QgsNetworkAccessManager.setRequestPreprocessor(preprocessor)


def nspd_plugin_dir(config: dict) -> Path:
    plugin_id = config["nspd"]["plugin_id"]
    plugin_name = config["nspd"]["plugin_name"]
    candidates = [
        Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins" / plugin_id,
        Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins" / plugin_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def is_nspd_host(host: str) -> bool:
    host = (host or "").lower()
    return host == "nspd.gov.ru" or host.endswith(".nspd.gov.ru")


if __name__ == "__main__":
    raise SystemExit(main())
