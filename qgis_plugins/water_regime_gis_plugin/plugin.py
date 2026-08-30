from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from qgis.PyQt.QtCore import QMetaType, Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QFileDialog,
    QDockWidget,
    QGridLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterLayer,
    QgsRendererCategory,
    QgsTask,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolIdentify

from . import settings
from .aggregate_series import average_by_date
from .radar_series import relative_moisture_proxy, rolling_median
from .seasonal_curve import fit_seasonal_curve


class WaterRegimeGisPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None

    def initGui(self):
        self.action = QAction("Water Regime GIS", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Water Regime GIS", self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Water Regime GIS", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def show_dock(self):
        if not self.dock:
            self.dock = WaterRegimeDock(self.iface)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()


class WaterRegimeDock(QDockWidget):
    def __init__(self, iface):
        super().__init__("Water Regime GIS", iface.mainWindow())
        self.iface = iface
        self.capture_tool = None
        self.chart_tool = None
        self.chart_dialogs = []
        self.active_task = None
        self.kornix_label_cache = {}
        stored_path, _ = QgsProject.instance().readEntry("water_regime_gis", "field_contours", "")
        self.field_contours_path = Path(stored_path) if stored_path else None

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Автоматизированный QGIS-сценарий анализа полей"))

        actions = QGridLayout()
        layout.addLayout(actions)
        self.contours_button = self.add_button(actions, 0, 0, "Загрузить контуры полей", self.load_field_contours)
        self.timeseries_button = self.add_button(actions, 0, 1, "Загрузить ряды из сервиса", self.download_external_timeseries)
        self.refresh_button = self.add_button(actions, 1, 0, "Обновить Sentinel-1/2", self.refresh_field_timeseries)
        self.check_button = self.add_button(actions, 1, 1, "Проверить среду", self.check_environment)
        self.observearth_button = self.add_button(actions, 2, 0, "Открыть Observearth", self.open_observearth)
        self.isolines_button = self.add_button(actions, 2, 1, "Построить изолинии", self.open_isolines)
        self.kriging_button = self.add_button(actions, 3, 0, "Кригинг измерений", self.open_kriging)
        self.project_button = self.add_button(actions, 3, 1, "Собрать проект/слои", self.build_project)
        self.chart_button = self.add_button(actions, 4, 0, "График по полю", self.enable_field_chart_tool)
        self.average_chart_button = self.add_button(actions, 4, 1, "Средний график", self.open_average_chart)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Ожидание загрузки снимков")
        layout.addWidget(self.progress)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(180)
        layout.addWidget(self.output)
        self.setWidget(panel)

    def add_button(self, layout, row, column, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button, row, column)
        return button

    def log(self, message: str):
        self.output.appendPlainText(message.rstrip())

    def notify(self, message: str, level=Qgis.Info):
        self.iface.messageBar().pushMessage("Water Regime GIS", message, level=level, duration=5)

    def check_environment(self):
        config = self.read_config()
        lines = [
            "Environment:",
            f"- QGIS: {Qgis.QGIS_VERSION}",
            f"- Project root: {settings.PROJECT_ROOT}",
            f"- QGIS prefix: {settings.QGIS_PREFIX}",
            f"- QGIS python: {settings.QGIS_PYTHON}",
            f"- Plugin profile: {settings.QGIS_PROFILE_PLUGINS}",
            f"- NSPD plugin: {self.nspd_status(config)}",
            f"- Observearth: {self.plugin_status('observearth')}",
            f"- Isoliner: {self.processing_status('isoliner:raster_to_isolines')}",
        ]
        for key in ("aoi", "interim", "processed", "maps", "rasters", "imagery", "reports"):
            path = settings.PROJECT_ROOT / config["paths"][key]
            lines.append(f"- {key}: {'OK' if path.exists() else 'missing'} {path}")
        self.log("\n".join(lines))
        self.run_task("PyQGIS context check", [settings.QGIS_PYTHON, settings.CHECK_CONTEXT_SCRIPT])

    def enable_point_capture(self):
        self.log("Кликните по карте QGIS, чтобы выбрать точку поля.")
        self.notify("Кликните по карте, чтобы выбрать точку поля.")
        self.capture_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.capture_tool.canvasClicked.connect(self.select_point)
        self.iface.mapCanvas().setMapTool(self.capture_tool)

    def select_point(self, point, button):
        crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        point_crs = self.transform_to_wgs84(point, crs)
        self.log(f"Selected point: lon={point_crs.x():.8f}, lat={point_crs.y():.8f}")
        self.run_task(
            "Select field point",
            [
                settings.QGIS_PYTHON,
                settings.SELECT_FIELD_SCRIPT,
                "--lon",
                str(point_crs.x()),
                "--lat",
                str(point_crs.y()),
            ],
            after_success=self.load_field_layers,
        )

    def transform_to_wgs84(self, point, source_crs):
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform

        target = QgsCoordinateReferenceSystem("EPSG:4326")
        if source_crs == target:
            return point
        transform = QgsCoordinateTransform(source_crs, target, QgsProject.instance())
        return transform.transform(point)

    def resolve_boundary(self):
        self.run_task(
            "Resolve field boundary",
            [settings.QGIS_PYTHON, settings.RESOLVE_BOUNDARY_SCRIPT],
            after_success=self.load_field_layers,
        )

    def process_indices(self):
        self.run_task(
            "Process satellite indices",
            [settings.QGIS_PYTHON, settings.SATELLITE_INDICES_SCRIPT],
            after_success=self.load_raster_layers,
            timeout=1800,
        )

    def load_field_contours(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Контуры полей", str(self.field_contours_path.parent if self.field_contours_path else settings.PROJECT_ROOT),
            "Векторные слои (*.gpkg *.geojson *.json *.shp);;Все файлы (*)",
        )
        if not path:
            return
        source = Path(path).resolve()
        layer = self.add_vector_layer(source, "Контуры полей пользователя")
        if not layer:
            return
        if layer.geometryType() != Qgis.GeometryType.Polygon:
            self.notify("Нужен полигональный слой контуров полей.", Qgis.Warning)
            return
        self.field_contours_path = source
        QgsProject.instance().writeEntry("water_regime_gis", "field_contours", str(source))
        self.log(f"Контуры полей загружены: {source} ({layer.featureCount()} объектов).")
        self.notify("Контуры полей добавлены в проект.")

    def download_external_timeseries(self):
        from qgis.PyQt.QtWidgets import QInputDialog

        url, accepted = QInputDialog.getText(
            self, "Временные ряды", "URL выгрузки CSV или ZIP из внешнего сервиса:"
        )
        if not accepted or not url.strip():
            return
        self.run_task(
            "Загрузка временных рядов из внешнего сервиса",
            [settings.QGIS_PYTHON, settings.EXTERNAL_TIMESERIES_SCRIPT, "--url", url.strip()],
            after_success=self.refresh_field_timeseries,
            timeout=1800,
        )

    def refresh_field_timeseries(self):
        if not self.field_contours_path or not self.field_contours_path.exists():
            self.notify("Сначала загрузите локальный полигональный слой контуров полей.", Qgis.Warning)
            return
        self.progress.setValue(0)
        self.progress.setFormat("Подготовка обновления Sentinel-1/2")
        self.run_task(
            "Обновление Sentinel-1/2 и расчетов",
            [settings.QGIS_PYTHON, settings.REFRESH_TIMESERIES_SCRIPT, "--fields", self.field_contours_path],
            after_success=self.load_downloaded_rasters,
            timeout=14400,
        )

    def load_downloaded_rasters(self):
        for path in sorted((settings.PROJECT_ROOT / "outputs/imagery").glob("**/sentinel_*.tif")):
            self.add_raster_layer(path, path.parent.name + ": " + path.stem)
        self.iface.mapCanvas().refresh()
        self.log("Новые снимки добавлены в текущий проект QGIS.")

    def open_observearth(self):
        from qgis.utils import plugins

        plugin = plugins.get("observearth")
        if plugin is None:
            self.notify("Observearth не включён в менеджере модулей.", Qgis.Warning)
            return
        plugin.run()
        self.log("Observearth открыт. Выберите слой поля; выделенные объекты имеют приоритет.")

    def open_isolines(self):
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsRasterLayer):
            layer = next(
                (candidate for candidate in QgsProject.instance().mapLayers().values()
                 if isinstance(candidate, QgsRasterLayer) and candidate.name().lower() == "ndmi"),
                None,
            )
        self.open_processing_dialog(
            "isoliner:raster_to_isolines",
            {"INPUT": layer, "LEVELS": "-0.2 0 0.1 0.2 0.3"} if layer else {},
            "Выберите растр индекса перед построением изолиний.",
        )

    def open_kriging(self):
        layer = self.iface.activeLayer()
        numeric_fields = []
        if isinstance(layer, QgsVectorLayer) and layer.geometryType() == Qgis.GeometryType.Point:
            numeric_fields = [field.name() for field in layer.fields() if field.isNumeric()]
        if not numeric_fields or layer.featureCount() < 3:
            self.notify(
                "Выберите точечный слой минимум с 3 объектами и числовым полем измерения.",
                Qgis.Warning,
            )
            return
        self.open_processing_dialog(
            "isoliner:kriging2d",
            {"INPUT": layer, "ZFIELD": numeric_fields[0]},
            "Isoliner не включён в менеджере модулей.",
        )

    def enable_field_chart_tool(self):
        path = settings.FIELD_ZONAL_MEANS_CSV
        if not path.exists():
            self.notify(f"Таблица расчетов не найдена: {path}", Qgis.Warning)
            return
        self.load_chart_field_layers()
        self.chart_tool = FieldChartMapTool(self.iface.mapCanvas(), self)
        self.iface.mapCanvas().setMapTool(self.chart_tool)
        self.log("Дважды щёлкните по полю SP, чтобы открыть график индексов.")
        self.notify("Дважды щёлкните по полю SP для графика индексов.")

    def open_average_chart(self):
        field_ids = self.kornix_field_ids()
        satellite_rows = self.average_satellite_rows(field_ids)
        kornix_rows = self.average_kornix_rows(field_ids)
        radar_rows = self.average_radar_rows(field_ids)
        if not satellite_rows and not kornix_rows and not radar_rows:
            self.notify("Нет рядов для среднего графика.", Qgis.Warning)
            return
        dialog = FieldIndexChartDialog(
            self.iface.mainWindow(),
            f"Среднее по {len(field_ids)} полям КОРНИКС",
            satellite_rows,
            kornix_rows,
            radar_rows,
        )
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
        self.chart_dialogs.append(dialog)
        dialog.destroyed.connect(lambda *_: self.chart_dialogs.remove(dialog) if dialog in self.chart_dialogs else None)
        self.log(f"Открыт средний график по {len(field_ids)} полям КОРНИКС; исключены поля с нестабильным лагом.")

    def kornix_field_ids(self) -> set[str]:
        return {
            path.name.removesuffix("_daily.csv")
            for path in settings.KORNIX_BY_FIELD_DIR.glob("SP_*_daily.csv")
            if path.name.removesuffix("_daily.csv") not in settings.AVERAGE_CHART_EXCLUDED_FIELDS
        }

    def average_satellite_rows(self, field_ids: set[str]) -> list[dict]:
        import csv

        if not settings.SP_ZONAL_MEANS_CSV.exists():
            return []
        with settings.SP_ZONAL_MEANS_CSV.open(newline="", encoding="utf-8") as handle:
            rows = [
                row for row in csv.DictReader(handle)
                if row.get("field_id") in field_ids and row.get("index") in settings.CHART_INDICES
            ]
        return average_by_date(rows, "scene_date", ("zonal_mean",), ("index",))

    def average_kornix_rows(self, field_ids: set[str]) -> list[dict]:
        import csv

        rows = []
        columns = tuple(settings.KORNIX_CHART_SERIES.values()) + (
            "precipitation_raw_daily_mm", "irrigation_raw_daily_mm",
        )
        for field_id in field_ids:
            path = settings.KORNIX_BY_FIELD_DIR / f"{field_id}_daily.csv"
            with path.open(newline="", encoding="utf-8-sig") as handle:
                rows.extend(
                    {**row, "field_id": field_id}
                    for row in csv.DictReader(handle)
                    if row.get("method_code") == settings.KORNIX_METHOD
                )
        return average_by_date(rows, "day", columns)

    def average_radar_rows(self, field_ids: set[str]) -> list[dict]:
        import csv

        if not settings.SENTINEL1_ZONAL_MEANS_CSV.exists():
            return []
        with settings.SENTINEL1_ZONAL_MEANS_CSV.open(newline="", encoding="utf-8") as handle:
            rows = [
                row for row in csv.DictReader(handle)
                if row.get("field_id") in field_ids and row.get("polarization", "").upper() == "VV"
            ]
        return average_by_date(rows, "scene_date", ("zonal_mean_db",))

    def load_chart_field_layers(self):
        for path, name in (
            (settings.PROJECT_ROOT / "data/processed/field_boundaries/sp_fields.geojson", "SP fields"),
            (Path("/Users/korneev/Desktop/SP.gpkg"), "Поля SP"),
        ):
            layer = self.add_vector_layer(path, name)
            if name in ("SP fields", "Поля SP") and layer:
                self.apply_kornix_filter(layer)
                if name == "Поля SP":
                    self.add_kornix_labels(layer)
        self.iface.mapCanvas().refresh()

    def apply_kornix_filter(self, layer: QgsVectorLayer):
        """Show only SP polygons that have a supplied KORNIX daily series."""
        if "field_external_key" not in layer.fields().names():
            self.log(f"Не удалось отфильтровать {layer.name()}: нет field_external_key.")
            return
        field_keys = sorted(
            field_id.replace("SP_", "SP:", 1).replace("_", ".")
            for path in settings.KORNIX_BY_FIELD_DIR.glob("SP_*_daily.csv")
            if (field_id := path.name.removesuffix("_daily.csv")) not in settings.ANALYSIS_EXCLUDED_FIELDS
        )
        if not field_keys:
            self.log("Ряды КОРНИКС не найдены: слой SP не изменён.")
            return
        quoted_keys = ", ".join(f"'{key}'" for key in field_keys)
        layer.setSubsetString(f'"field_external_key" IN ({quoted_keys})')
        self.log(f"Слой {layer.name()}: показаны {len(field_keys)} полей с данными КОРНИКС.")

    def open_chart_for_feature(self, feature):
        field_id = self.field_id_for_feature(feature)
        if not field_id:
            self.notify("Не удалось определить field_id для выбранного поля.", Qgis.Warning)
            return
        if field_id in settings.ANALYSIS_EXCLUDED_FIELDS:
            self.notify(f"Поле {field_id} исключено из анализа.", Qgis.Warning)
            return
        rows = self.rows_for_field(field_id)
        kornix_rows = self.kornix_rows_for_field(field_id)
        radar_rows = self.sentinel1_rows_for_field(field_id)
        if not rows and not kornix_rows and not radar_rows:
            self.notify(f"Нет спутниковых или модельных рядов для {field_id}.", Qgis.Warning)
            return
        dialog = FieldIndexChartDialog(self.iface.mainWindow(), field_id, rows, kornix_rows, radar_rows)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
        self.chart_dialogs.append(dialog)
        dialog.destroyed.connect(lambda *_: self.chart_dialogs.remove(dialog) if dialog in self.chart_dialogs else None)
        self.log(f"Открыт график Sentinel-2/КОРНИКС: {field_id}")

    def rows_for_field(self, field_id: str) -> list[dict]:
        import csv

        path = settings.SP_ZONAL_MEANS_CSV if field_id.startswith("SP_") else settings.FIELD_ZONAL_MEANS_CSV
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return [row for row in csv.DictReader(handle) if row.get("field_id") == field_id]

    def kornix_rows_for_field(self, field_id: str) -> list[dict]:
        import csv

        path = settings.KORNIX_BY_FIELD_DIR / f"{field_id}_daily.csv"
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [row for row in csv.DictReader(handle) if row.get("method_code") == settings.KORNIX_METHOD]

    def sentinel1_rows_for_field(self, field_id: str) -> list[dict]:
        import csv

        path = settings.SENTINEL1_ZONAL_MEANS_CSV
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return [row for row in csv.DictReader(handle) if row.get("field_id") == field_id]

    def kornix_label_for_field(self, field_id: str) -> str:
        """Return a compact, static KORNIX summary for a field polygon label."""
        if field_id in self.kornix_label_cache:
            return self.kornix_label_cache[field_id]

        rows = self.kornix_rows_for_field(field_id)
        if not rows:
            label = f"{field_id}\nКОРНИКС: нет данных"
        else:
            latest = max(rows, key=lambda row: row.get("day", ""))
            crop = latest.get("crop_name") or "Культура не указана"
            sowing = self.format_kornix_date(latest.get("crop_sowing_date"))
            day = self.format_kornix_date(latest.get("day"))
            label = (
                f"{field_id}\n{crop}\nПосев: {sowing}\n"
                f"Погода {day}: Tср {self.kornix_number(latest.get('air_temperature_mean_c'))} °C, "
                f"осадки {self.kornix_number(latest.get('weather_precipitation_mm'))} мм, "
                f"ET₀ {self.kornix_number(latest.get('eto_daily_mm'))} мм"
            )
        self.kornix_label_cache[field_id] = label
        return label

    @staticmethod
    def format_kornix_date(value) -> str:
        if not value:
            return "нет данных"
        parts = str(value).split("-")
        return ".".join(reversed(parts)) if len(parts) == 3 else str(value)

    @staticmethod
    def kornix_number(value) -> str:
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return "нет данных"

    def add_kornix_labels(self, source_layer: QgsVectorLayer):
        """Add a transparent companion layer so the user source GeoPackage stays unchanged."""
        layer_name = "КОРНИКС: подписи полей SP"
        for existing_layer in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(existing_layer.id())

        crs = source_layer.crs().authid()
        labels = QgsVectorLayer(f"Polygon?crs={crs}", layer_name, "memory")
        provider = labels.dataProvider()
        provider.addAttributes([
            QgsField("field_id", QMetaType.Type.QString),
            QgsField("kornix_label", QMetaType.Type.QString),
            QgsField("has_kornix", QMetaType.Type.Int),
        ])
        labels.updateFields()

        features = []
        for source_feature in source_layer.getFeatures():
            feature = QgsFeature(labels.fields())
            feature.setGeometry(source_feature.geometry())
            field_id = self.field_id_for_feature(source_feature)
            has_kornix = bool(self.kornix_rows_for_field(field_id))
            feature.setAttributes([field_id, self.kornix_label_for_field(field_id), int(has_kornix)])
            features.append(feature)
        provider.addFeatures(features)

        labels.setRenderer(QgsCategorizedSymbolRenderer(
            "has_kornix",
            [
                QgsRendererCategory(
                    1,
                    QgsFillSymbol.createSimple({
                        "color": "0,220,185,95",
                        "outline_color": "0,150,130,255",
                        "outline_width": "0.8",
                    }),
                    "КОРНИКС: данные есть",
                ),
                QgsRendererCategory(
                    0,
                    QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "0,0,0,0"}),
                    "КОРНИКС: нет данных",
                ),
            ],
        ))
        labels.triggerRepaint()
        self.iface.mapCanvas().refresh()
        self.log(
            f"Выделены поля КОРНИКС: {sum(feature['has_kornix'] for feature in features)} из {len(features)}."
        )
        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = 'CASE WHEN "has_kornix" = 1 THEN "kornix_label" END'
        label_settings.isExpression = True
        label_settings.enabled = True
        label_settings.displayAll = True
        text_format = QgsTextFormat()
        text_format.setSize(7)
        label_settings.setFormat(text_format)
        labels.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
        labels.setLabelsEnabled(True)
        QgsProject.instance().addMapLayer(labels)
        self.log(f"Добавлены подписи КОРНИКС для {len(features)} полей SP.")

    def field_id_for_feature(self, feature) -> str:
        fields = feature.fields()
        attrs = {field.name(): feature[field.name()] for field in fields}
        for key in ("field_id", "fieldId", "FIELD_ID"):
            value = attrs.get(key)
            if value:
                return str(value)

        dataset = str(attrs.get("dataset_code") or attrs.get("dataset") or "").upper()
        for key in ("field_code_raw", "field_name_raw", "field_external_key"):
            value = attrs.get(key)
            if not value:
                continue
            code = str(value).split(":", 1)[-1].replace(".", "_")
            if dataset:
                return f"{dataset}_{code}"
        return ""

    def open_processing_dialog(self, algorithm_id: str, parameters: dict, missing_message: str):
        if QgsApplication.processingRegistry().algorithmById(algorithm_id) is None:
            self.notify(missing_message, Qgis.Warning)
            return
        import processing

        processing.execAlgorithmDialog(algorithm_id, parameters)
        self.log(f"Открыт алгоритм Processing: {algorithm_id}")

    def build_project(self):
        self.load_field_layers()
        self.load_raster_layers()
        config = self.read_config()
        path = settings.PROJECT_ROOT / config["qgis"]["project_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        project = QgsProject.instance()
        project.setFileName(str(path))
        if project.write():
            self.log(f"Проект сохранён: {path}")
            self.notify("Проект и доступные слои сохранены.")
        else:
            self.log(f"Не удалось сохранить проект: {path}")
            self.notify("Не удалось сохранить QGIS-проект.", Qgis.Critical)

    def run_task(self, label: str, command: list[Path | str], after_success=None, timeout=300):
        if self.active_task:
            self.notify("Дождитесь завершения текущей операции.", Qgis.Warning)
            return
        task = CommandTask(label, command, self.log, self.task_finished, after_success, timeout)
        task.progressChanged.connect(self.update_progress)
        self.active_task = task
        self.set_buttons_enabled(False)
        self.log(f"\n== {label} ==")
        QgsApplication.taskManager().addTask(task)

    def update_progress(self, value: float):
        self.progress.setValue(round(value))
        self.progress.setFormat(f"Загрузка и обработка снимков: {round(value)}%")

    def task_finished(self, task):
        self.active_task = None
        self.set_buttons_enabled(True)
        if task.returncode == 0:
            self.progress.setValue(100)
            self.progress.setFormat("Обновление завершено")
        if task.returncode == 0:
            self.notify(f"{task.description()}: OK")
        else:
            self.notify(f"{task.description()}: ошибка", Qgis.Critical)

    def set_buttons_enabled(self, enabled: bool):
        for button in (
            self.contours_button,
            self.timeseries_button,
            self.refresh_button,
            self.check_button,
            self.observearth_button,
            self.isolines_button,
            self.kriging_button,
            self.project_button,
            self.chart_button,
            self.average_chart_button,
        ):
            button.setEnabled(enabled)

    def read_config(self) -> dict:
        return json.loads(settings.CONFIG_PATH.read_text(encoding="utf-8"))

    def nspd_status(self, config: dict) -> str:
        plugin_id = config["nspd"]["plugin_id"]
        plugin_name = config["nspd"]["plugin_name"]
        candidates = [
            settings.QGIS_PROFILE_PLUGINS / plugin_id,
            settings.QGIS_PROFILE_PLUGINS / plugin_name,
        ]
        existing = [path for path in candidates if path.exists()]
        return str(existing[0]) if existing else "missing"

    def plugin_status(self, plugin_id: str) -> str:
        from qgis.utils import plugins

        path = settings.QGIS_PROFILE_PLUGINS / plugin_id
        if plugin_id in plugins:
            return f"enabled ({path})"
        return f"installed ({path})" if path.exists() else "missing"

    def processing_status(self, algorithm_id: str) -> str:
        if QgsApplication.processingRegistry().algorithmById(algorithm_id):
            return "enabled"
        path = settings.QGIS_PROFILE_PLUGINS / "grid_isolines"
        return f"installed ({path})" if path.exists() else "missing"

    def load_field_layers(self):
        config = self.read_config()
        self.add_vector_layer(settings.PROJECT_ROOT / config["paths"]["selected_field_area"], "Selected field working area")
        self.add_vector_layer(settings.PROJECT_ROOT / config["paths"]["selected_field_point"], "Selected field point")
        self.iface.mapCanvas().refresh()

    def load_raster_layers(self):
        config = self.read_config()
        for index in config["satellite"]["indices"]:
            path = settings.PROJECT_ROOT / config["paths"]["rasters"] / f"{index.lower()}.tif"
            if path.exists():
                self.add_raster_layer(path, index)
        self.iface.mapCanvas().refresh()

    def add_vector_layer(self, path: Path, name: str):
        if not path.exists():
            self.log(f"Layer missing: {path}")
            return None
        if self.layer_is_loaded(path):
            target = path.resolve()
            return next(
                (
                    layer for layer in QgsProject.instance().mapLayers().values()
                    if Path(layer.source().split("|")[0]).resolve() == target
                ),
                None,
            )
        layer = QgsVectorLayer(str(path), name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"Loaded layer: {path}")
            return layer
        else:
            self.log(f"Invalid vector layer: {path}")
            return None

    def add_raster_layer(self, path: Path, name: str):
        if self.layer_is_loaded(path):
            return
        layer = QgsRasterLayer(str(path), name, "gdal")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"Loaded raster: {path}")
        else:
            self.log(f"Invalid raster layer: {path}")

    def layer_is_loaded(self, path: Path) -> bool:
        target = path.resolve()
        return any(Path(layer.source().split("|")[0]).resolve() == target for layer in QgsProject.instance().mapLayers().values())


class FieldChartMapTool(QgsMapToolIdentify):
    def __init__(self, canvas, dock: WaterRegimeDock):
        super().__init__(canvas)
        self.dock = dock

    def canvasDoubleClickEvent(self, event):
        feature = self.feature_at(event.x(), event.y())
        if feature:
            self.dock.open_chart_for_feature(feature)
        else:
            self.dock.notify("Под двойным щелчком не найдено поле.", Qgis.Warning)

    def canvasMoveEvent(self, event):
        feature = self.feature_at(event.x(), event.y())
        if not feature:
            QToolTip.hideText()
            return
        field_id = self.dock.field_id_for_feature(feature)
        if field_id:
            QToolTip.showText(QCursor.pos(), f"{field_id}\nДвойной щелчок: график индексов")

    def feature_at(self, x, y):
        results = self.identify(x, y, self.TopDownStopAtFirst, self.VectorLayer)
        for result in results:
            layer = result.mLayer
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == Qgis.GeometryType.Polygon:
                return result.mFeature
        return None


class FieldIndexChartDialog(QDialog):
    def __init__(self, parent, field_id: str, rows: list[dict], kornix_rows: list[dict], radar_rows: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Sentinel-2, КОРНИКС и Sentinel-1: {field_id}")
        self.resize(980, 900)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(field_id))

        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        figure = Figure(figsize=(9, 9), tight_layout=True)
        canvas = FigureCanvasQTAgg(figure)
        layout.addWidget(canvas)
        satellite_axis = figure.add_subplot(311)
        kornix_axis = figure.add_subplot(312, sharex=satellite_axis)
        radar_axis = figure.add_subplot(313, sharex=satellite_axis)
        satellite_period = self.satellite_date_range(rows)
        self.plot_rows(satellite_axis, rows)
        self.plot_kornix_rows(kornix_axis, kornix_rows, satellite_period)
        self.plot_radar_rows(radar_axis, radar_rows, satellite_period)
        if satellite_period:
            satellite_axis.set_xlim(*satellite_period)
        canvas.draw()

    @staticmethod
    def satellite_date_range(rows: list[dict]):
        import datetime as dt

        dates = []
        for row in rows:
            if row.get("index") not in settings.CHART_INDICES or row.get("zonal_mean") in ("", None):
                continue
            try:
                dates.append(dt.date.fromisoformat(row["scene_date"]))
            except (KeyError, TypeError, ValueError):
                continue
        return (min(dates), max(dates)) if dates else None

    def plot_rows(self, axis, rows: list[dict]):
        import datetime as dt
        from collections import defaultdict

        by_index = defaultdict(list)
        for row in rows:
            value = row.get("zonal_mean")
            if value in ("", None):
                continue
            if row["index"] not in settings.CHART_INDICES:
                continue
            date = dt.date.fromisoformat(row["scene_date"])
            by_index[row["index"]].append((date, float(value)))

        for index_name in sorted(by_index):
            values = self.values_by_date(by_index[index_name])
            dates = [date for date, _ in values]
            means = [value for _, value in values]
            color = settings.FCOVER_COLOR if index_name == "FCOVER" else axis._get_lines.get_next_color()
            axis.scatter(dates, means, s=28, color=color, alpha=0.85, zorder=3)
            fit = fit_seasonal_curve(values, settings.SEASONAL_CHART_FIT)
            axis.plot(
                fit.dates,
                fit.values,
                color=color,
                linewidth=1.8,
                label=f"{index_name} (Qrob={fit.quality:.2f})",
            )

        if not by_index:
            axis.text(0.5, 0.5, "Нет валидных значений zonal_mean", ha="center", va="center", transform=axis.transAxes)

        axis.axhline(0, color="#888888", linewidth=0.8)
        axis.set_ylabel("Sentinel-2 индекс")
        axis.grid(True, alpha=0.25)
        if by_index:
            axis.legend(loc="best")

    def plot_kornix_rows(self, axis, rows: list[dict], satellite_period=None):
        import datetime as dt

        rows = self.rows_in_period(rows, "day", satellite_period)
        plotted = False
        for label, column in settings.KORNIX_CHART_SERIES.items():
            values = []
            for row in rows:
                value = row.get(column)
                if value in ("", None):
                    continue
                values.append((dt.date.fromisoformat(row["day"]), float(value)))
            if values:
                dates, numbers = zip(*values)
                color = settings.FCOVER_COLOR if column == "satellite_fcover_expected" else None
                axis.plot(dates, numbers, color=color, linewidth=1.5, label=label)
                plotted = True

        water_by_date = {}
        for row in rows:
            date = dt.date.fromisoformat(row["day"])
            precipitation = self.positive_kornix_value(row.get("precipitation_raw_daily_mm"))
            irrigation = self.positive_kornix_value(row.get("irrigation_raw_daily_mm"))
            if precipitation or irrigation:
                water_by_date[date] = (
                    float(row.get("precipitation_raw_daily_mm") or 0),
                    float(row.get("irrigation_raw_daily_mm") or 0),
                )
        if water_by_date:
            dates = sorted(water_by_date)
            precipitation = [water_by_date[date][0] for date in dates]
            irrigation = [water_by_date[date][1] for date in dates]
            water_axis = axis.twinx()
            water_axis.bar(dates, precipitation, width=0.8, color="#1f77b4", alpha=0.5, label="Осадки")
            water_axis.bar(dates, irrigation, width=0.8, bottom=precipitation, color="#7b2cbf", alpha=0.5, label="Полив")
            water_axis.set_ylabel("Вода, мм/сут")

        if not plotted:
            axis.text(0.5, 0.5, "Нет рядов КОРНИКС выбранного метода", ha="center", va="center", transform=axis.transAxes)
        axis.set_ylabel("КОРНИКС: модельное значение")
        axis.grid(True, alpha=0.25)
        if plotted:
            handles, labels = axis.get_legend_handles_labels()
            if water_by_date:
                water_handles, water_labels = water_axis.get_legend_handles_labels()
                handles += water_handles
                labels += water_labels
            axis.legend(handles, labels, loc="best")

    @staticmethod
    def positive_kornix_value(value) -> bool:
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False

    def plot_radar_rows(self, axis, rows: list[dict], satellite_period=None):
        import datetime as dt

        rows = self.rows_in_period(rows, "scene_date", satellite_period)
        vv_values = []
        for row in rows:
            value = row.get("zonal_mean_db")
            polarization = row.get("polarization", "VV").upper()
            if value in ("", None) or polarization != "VV":
                continue
            vv_values.append((dt.date.fromisoformat(row["scene_date"]), float(value)))

        values = self.values_by_date(vv_values)
        if values:
            dates = [date for date, _ in values]
            moisture = relative_moisture_proxy(
                [value for _, value in values],
                minimum=settings.RADAR_MOISTURE_RANGE[0],
                maximum=settings.RADAR_MOISTURE_RANGE[1],
            )
            axis.scatter(dates, moisture, s=18, color="#1f77b4", alpha=0.7, zorder=3)
            axis.plot(dates, rolling_median(moisture), color="#1f77b4", linewidth=1.6, label="Влажность VV")
        else:
            axis.text(0.5, 0.5, "Нет данных Sentinel-1 для поля", ha="center", va="center", transform=axis.transAxes)
        axis.set_xlabel("Дата")
        axis.set_ylabel("Влажность Sentinel-1")
        axis.grid(True, alpha=0.25)
        if values:
            axis.legend(loc="best")

    def values_by_date(self, values):
        import statistics
        from collections import defaultdict

        by_date = defaultdict(list)
        for date, value in values:
            by_date[date].append(value)
        return [(date, statistics.median(by_date[date])) for date in sorted(by_date)]

    @staticmethod
    def rows_in_period(rows: list[dict], date_column: str, satellite_period):
        if not satellite_period:
            return rows
        start_date, end_date = satellite_period
        return [
            row
            for row in rows
            if start_date.isoformat() <= row.get(date_column, "") <= end_date.isoformat()
        ]

class CommandTask(QgsTask):
    def __init__(self, label, command, log_callback, finished_callback, after_success=None, timeout=300):
        super().__init__(label, QgsTask.CanCancel)
        self.command = [str(part) for part in command]
        self.log_callback = log_callback
        self.finished_callback = finished_callback
        self.after_success = after_success
        self.timeout = timeout
        self.returncode = 1
        self.stdout = ""
        self.stderr = ""

    def run(self):
        env = os.environ.copy()
        env.setdefault("QGIS_PREFIX_PATH", str(settings.QGIS_PREFIX))
        env.setdefault("PROJ_DATA", str(settings.QGIS_PREFIX / "Contents/Resources/qgis/proj"))
        src = str(settings.PROJECT_ROOT / "src")
        env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else f"{src}{os.pathsep}{env['PYTHONPATH']}"
        try:
            process = subprocess.Popen(
                self.command,
                cwd=settings.PROJECT_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            lines = []
            for line in process.stdout:
                lines.append(line)
                if line.startswith("PROGRESS "):
                    try:
                        self.setProgress(float(line.split()[1]))
                    except (IndexError, ValueError):
                        pass
            self.returncode = process.wait(timeout=self.timeout)
            self.stdout = "".join(lines)
            return self.returncode == 0
        except Exception as exc:
            self.stderr = str(exc)
            self.returncode = 1
            return False

    def finished(self, result):
        if self.stdout:
            self.log_callback(self.stdout)
        if self.stderr:
            self.log_callback(self.stderr)
        if result and self.returncode == 0 and self.after_success:
            self.after_success()
        self.finished_callback(self)
