from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QDockWidget,
    QGridLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from qgis.core import Qgis, QgsApplication, QgsProject, QgsRasterLayer, QgsTask, QgsVectorLayer
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolIdentify

from . import settings


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

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Личный QGIS-сценарий анализа поля"))

        actions = QGridLayout()
        layout.addLayout(actions)
        self.check_button = self.add_button(actions, 0, 0, "Проверить среду", self.check_environment)
        self.pick_button = self.add_button(actions, 0, 1, "Взять точку с карты", self.enable_point_capture)
        self.boundary_button = self.add_button(actions, 1, 0, "Уточнить границу", self.resolve_boundary)
        self.indices_button = self.add_button(actions, 1, 1, "Рассчитать индексы", self.process_indices)
        self.observearth_button = self.add_button(actions, 2, 0, "Открыть Observearth", self.open_observearth)
        self.isolines_button = self.add_button(actions, 2, 1, "Построить изолинии", self.open_isolines)
        self.kriging_button = self.add_button(actions, 3, 0, "Кригинг измерений", self.open_kriging)
        self.project_button = self.add_button(actions, 3, 1, "Собрать проект/слои", self.build_project)
        self.chart_button = self.add_button(actions, 4, 0, "График по полю", self.enable_field_chart_tool)

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
        self.log("Дважды щёлкните по полю KAA/SP, чтобы открыть график индексов.")
        self.notify("Дважды щёлкните по полю KAA/SP для графика индексов.")

    def load_chart_field_layers(self):
        for path, name in (
            (settings.PROJECT_ROOT / "data/processed/field_boundaries/kaa_fields.geojson", "KAA fields"),
            (settings.PROJECT_ROOT / "data/processed/field_boundaries/sp_fields.geojson", "SP fields"),
            (Path("/Users/korneev/Desktop/KAA.gpkg"), "Поля KAA"),
            (Path("/Users/korneev/Desktop/SP.gpkg"), "Поля SP"),
        ):
            self.add_vector_layer(path, name)
        self.iface.mapCanvas().refresh()

    def open_chart_for_feature(self, feature):
        field_id = self.field_id_for_feature(feature)
        if not field_id:
            self.notify("Не удалось определить field_id для выбранного поля.", Qgis.Warning)
            return
        rows = self.rows_for_field(field_id)
        if not rows:
            self.notify(f"В таблице расчетов нет данных для {field_id}.", Qgis.Warning)
            return
        dialog = FieldIndexChartDialog(self.iface.mainWindow(), field_id, rows)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
        self.chart_dialogs.append(dialog)
        dialog.destroyed.connect(lambda *_: self.chart_dialogs.remove(dialog) if dialog in self.chart_dialogs else None)
        self.log(f"Открыт график индексов: {field_id}")

    def rows_for_field(self, field_id: str) -> list[dict]:
        import csv

        with settings.FIELD_ZONAL_MEANS_CSV.open(newline="", encoding="utf-8") as handle:
            return [row for row in csv.DictReader(handle) if row.get("field_id") == field_id]

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
        self.active_task = task
        self.set_buttons_enabled(False)
        self.log(f"\n== {label} ==")
        QgsApplication.taskManager().addTask(task)

    def task_finished(self, task):
        self.active_task = None
        self.set_buttons_enabled(True)
        if task.returncode == 0:
            self.notify(f"{task.description()}: OK")
        else:
            self.notify(f"{task.description()}: ошибка", Qgis.Critical)

    def set_buttons_enabled(self, enabled: bool):
        for button in (
            self.check_button,
            self.pick_button,
            self.boundary_button,
            self.indices_button,
            self.observearth_button,
            self.isolines_button,
            self.kriging_button,
            self.project_button,
            self.chart_button,
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
            return
        if self.layer_is_loaded(path):
            return
        layer = QgsVectorLayer(str(path), name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"Loaded layer: {path}")
        else:
            self.log(f"Invalid vector layer: {path}")

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
    def __init__(self, parent, field_id: str, rows: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Индексы поля {field_id}")
        self.resize(980, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(field_id))

        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        figure = Figure(figsize=(9, 5), tight_layout=True)
        canvas = FigureCanvasQTAgg(figure)
        layout.addWidget(canvas)
        axis = figure.add_subplot(111)
        self.plot_rows(axis, rows)
        canvas.draw()

    def plot_rows(self, axis, rows: list[dict]):
        import datetime as dt
        from collections import defaultdict

        by_index = defaultdict(list)
        for row in rows:
            value = row.get("zonal_mean")
            if value in ("", None):
                continue
            date = dt.date.fromisoformat(row["scene_date"])
            by_index[row["index"]].append((date, float(value)))

        for index_name in sorted(by_index):
            values = self.values_by_date(by_index[index_name])
            dates = [date for date, _ in values]
            means = [value for _, value in values]
            color = axis._get_lines.get_next_color()
            axis.scatter(dates, means, s=28, color=color, alpha=0.85, zorder=3)
            smooth_dates, smooth_values = self.smooth_line(index_name, values)
            axis.plot(
                smooth_dates,
                smooth_values,
                color=color,
                linewidth=1.8,
                label=index_name,
            )

        if not by_index:
            axis.text(0.5, 0.5, "Нет валидных значений zonal_mean", ha="center", va="center", transform=axis.transAxes)

        axis.axhline(0, color="#888888", linewidth=0.8)
        axis.set_xlabel("Дата сцены")
        axis.set_ylabel("Зональное среднее")
        axis.grid(True, alpha=0.25)
        if by_index:
            axis.legend(loc="best")

    def values_by_date(self, values):
        import statistics
        from collections import defaultdict

        by_date = defaultdict(list)
        for date, value in values:
            by_date[date].append(value)
        return [(date, statistics.median(by_date[date])) for date in sorted(by_date)]

    def smooth_line(self, index_name: str, values):
        fitted = self.double_logistic_line(index_name, values)
        if not fitted:
            fitted = self.spline_line(values)
        if settings.DOUBLE_LOGISTIC_CHART_FIT["enforce_unimodal"]:
            dates, fitted_values = fitted
            return dates, self.unimodal_curve(fitted_values)
        return fitted

    def double_logistic_line(self, index_name: str, values):
        import datetime as dt

        import numpy as np
        from scipy.optimize import least_squares

        config = settings.DOUBLE_LOGISTIC_CHART_FIT
        if len(values) < config["min_observations"]:
            return None

        dates = [date for date, _ in values]
        original_y = np.array([value for _, value in values], dtype=float)
        y_min = float(np.nanpercentile(original_y, 5))
        y_max = float(np.nanpercentile(original_y, 95))
        amplitude = y_max - y_min
        if amplitude < config["amplitude_min"]:
            return None
        y = (original_y - y_min) / amplitude

        t = np.array([(date - dates[0]).days for date in dates], dtype=float)
        span = max(float(t[-1] - t[0]), 1.0)
        dense_t = np.linspace(float(t[0]), float(t[-1]), max(120, len(values) * 16))
        start_datetime = dt.datetime.combine(dates[0], dt.time())
        dense_dates = [start_datetime + dt.timedelta(days=float(day)) for day in dense_t]

        def model(params, x):
            b, upper, t_g, width, k_g, k_s = params
            t_s = t_g + width
            growth = 1.0 / (1.0 + np.exp(-k_g * (x - t_g)))
            senescence = 1.0 / (1.0 + np.exp(-k_s * (x - t_s)))
            return b + (upper - b) * (growth - senescence)

        b0 = float(np.nanpercentile(y, 10))
        upper0 = float(np.nanpercentile(y, 90))
        midpoint = b0 + 0.5 * (upper0 - b0)
        peak_pos = int(np.nanargmax(y))
        growth_candidates = t[: peak_pos + 1][y[: peak_pos + 1] >= midpoint]
        senescence_candidates = t[peak_pos:][y[peak_pos:] <= midpoint]
        t_g0 = float(growth_candidates[0]) if len(growth_candidates) else span * 0.35
        t_s0 = float(t[peak_pos] + span * 0.7) if not len(senescence_candidates) else float(senescence_candidates[0])
        width0 = max(10.0, t_s0 - t_g0)

        b_bounds = config["baseline_bounds"]
        upper_bounds = config["upper_bounds"]
        rate_bounds = config["rate_bounds"]
        min_tg = min(14.0, span * 0.25)
        min_width = max(10.0, span * 0.45)
        lower = [b_bounds[0], upper_bounds[0], min_tg, min_width, rate_bounds[0], rate_bounds[0]]
        upper = [b_bounds[1], upper_bounds[1], span + 30.0, span + 140.0, rate_bounds[1], rate_bounds[1]]
        base = [
            min(max(b0, lower[0]), upper[0]),
            min(max(upper0, lower[1]), upper[1]),
            min(max(t_g0, lower[2]), upper[2]),
            min(max(width0, lower[3]), upper[3]),
            0.08,
            0.08,
        ]

        starts = []
        for t_g_factor, width_factor in ((0.3, 0.8), (0.35, 1.0), (0.45, 1.2)):
            guess = list(base)
            guess[2] = min(max(span * t_g_factor, lower[2]), upper[2])
            guess[3] = min(max(span * width_factor, lower[3]), upper[3])
            starts.append(guess)
        starts.insert(0, base)

        best = None
        for guess in starts:
            result = least_squares(
                lambda params: model(params, t) - y,
                guess,
                bounds=(lower, upper),
                loss=config["loss"],
                max_nfev=config["max_nfev"],
            )
            if result.success and np.all(np.isfinite(result.x)):
                score = float(np.sum(np.square(model(result.x, t) - y)))
                if best is None or score < best[0]:
                    best = (score, result.x)

        if best is None:
            return None
        fitted = model(best[1], dense_t)
        if not np.all(np.isfinite(fitted)):
            return None
        if config["enforce_unimodal"]:
            fitted = self.unimodal_curve(fitted)
        return dense_dates, fitted * amplitude + y_min

    def unimodal_curve(self, values):
        import numpy as np

        fitted = np.array(values, dtype=float)
        peak = int(np.nanargmax(fitted))
        fitted[: peak + 1] = np.maximum.accumulate(fitted[: peak + 1])
        tail = fitted[peak:]
        fitted[peak:] = np.maximum.accumulate(tail[::-1])[::-1]
        return fitted

    def spline_line(self, values):
        import matplotlib.dates as mdates
        import numpy as np
        from scipy.interpolate import UnivariateSpline

        dates = [date for date, _ in values]
        means = [value for _, value in values]
        if len(values) < 4:
            return dates, means

        x = mdates.date2num(dates)
        dense_x = np.linspace(float(x[0]), float(x[-1]), max(80, len(values) * 12))
        dense_dates = mdates.num2date(dense_x)
        variance = float(np.var(means))
        smoothing = max(1e-5, len(values) * variance * 0.35)
        spline = UnivariateSpline(x, means, k=min(3, len(values) - 1), s=smoothing)
        return dense_dates, spline(dense_x)


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
            result = subprocess.run(
                self.command,
                cwd=settings.PROJECT_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
            self.returncode = result.returncode
            self.stdout = result.stdout
            self.stderr = result.stderr
            return result.returncode == 0
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
