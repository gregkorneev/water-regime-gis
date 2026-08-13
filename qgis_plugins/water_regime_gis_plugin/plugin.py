from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAction,
    QDockWidget,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from qgis.core import Qgis, QgsApplication, QgsProject, QgsRasterLayer, QgsTask, QgsVectorLayer
from qgis.gui import QgsMapToolEmitPoint

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
        self.active_task = None

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Личный QGIS-сценарий анализа поля"))

        self.check_button = self.add_button(layout, "Проверить среду", self.check_environment)
        self.pick_button = self.add_button(layout, "Взять точку с карты", self.enable_point_capture)
        self.boundary_button = self.add_button(layout, "Уточнить границу", self.resolve_boundary)
        self.indices_button = self.add_button(layout, "Рассчитать индексы", self.process_indices)
        self.project_button = self.add_button(layout, "Собрать проект/слои", self.build_project)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(260)
        layout.addWidget(self.output)
        self.setWidget(panel)

    def add_button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
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
        ]
        for key in ("aoi", "interim", "processed", "maps", "reports", "rasters"):
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

    def build_project(self):
        self.run_task(
            "Build QGIS project",
            [settings.QGIS_PYTHON, settings.CREATE_PROJECT_SCRIPT],
            after_success=self.open_generated_project,
        )

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
            self.project_button,
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

    def open_generated_project(self):
        config = self.read_config()
        path = settings.PROJECT_ROOT / config["qgis"]["project_file"]
        if path.exists() and QgsProject.instance().read(str(path)):
            self.log(f"Opened project: {path}")
        else:
            self.log(f"Could not open generated project: {path}")
            self.load_field_layers()
            self.load_raster_layers()

    def add_vector_layer(self, path: Path, name: str):
        if not path.exists():
            self.log(f"Layer missing: {path}")
            return
        layer = QgsVectorLayer(str(path), name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"Loaded layer: {path}")
        else:
            self.log(f"Invalid vector layer: {path}")

    def add_raster_layer(self, path: Path, name: str):
        layer = QgsRasterLayer(str(path), name, "gdal")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"Loaded raster: {path}")
        else:
            self.log(f"Invalid raster layer: {path}")


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
        env["WATER_REGIME_GIS_SKIP_NSPD_WMS"] = "1"
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
