#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "water_regime_gis_plugin"
SOURCE = ROOT / "qgis_plugins" / PLUGIN_NAME
TARGET = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins" / PLUGIN_NAME
REQUIRED = ("metadata.txt", "__init__.py", "plugin.py", "settings.py")


def main() -> int:
    missing = [name for name in REQUIRED if not (SOURCE / name).exists()]
    if missing:
        print("Missing plugin files:")
        for name in missing:
            print(f"- {SOURCE / name}")
        return 1
    init_text = (SOURCE / "__init__.py").read_text(encoding="utf-8")
    metadata = (SOURCE / "metadata.txt").read_text(encoding="utf-8")
    plugin = (SOURCE / "plugin.py").read_text(encoding="utf-8")
    assert "classFactory" in init_text
    assert "name=Water Regime GIS" in metadata
    assert "WaterRegimeGisPlugin" in plugin
    assert "QgsTask" in plugin
    assert 'plugins.get("observearth")' in plugin
    assert '"isoliner:raster_to_isolines"' in plugin
    assert '"isoliner:kriging2d"' in plugin
    assert "apply_kornix_filter" in plugin
    assert '"field_external_key" IN' in plugin
    assert 'Path("/Users/korneev/Desktop/KAA.gpkg")' not in plugin
    assert "Загрузить контуры полей" in plugin
    assert "Загрузить ряды из сервиса" in plugin
    assert "Обновить Sentinel-1/2" in plugin
    assert "Диаграммы эксперимента" in plugin
    assert "ExperimentChartsDialog" in plugin
    assert "QProgressBar" in plugin
    assert "set_toolbar_action_color" in plugin
    assert "QToolButton { color: #f2f2f2; }" in plugin
    assert "Перезагрузить плагин" in plugin
    assert "qgis.utils.unloadPlugin(plugin_id)" in plugin
    assert 'readEntry("water_regime_gis", "field_contours"' in plugin
    assert 'writeEntry("water_regime_gis", "field_contours"' in plugin
    assert "project.write()" in plugin
    print(f"Plugin source: OK {SOURCE}")
    print(f"QGIS profile target: {TARGET}")
    print(f"Installed: {'yes' if TARGET.exists() else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
