from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

from tkinter import END, BOTH, LEFT, RIGHT, X, Button, Frame, Label, Tk
from tkinter.scrolledtext import ScrolledText

from .project import aoi_summary, load_config, missing_required_dirs, project_root


def status_lines(root: Path, config: dict) -> list[str]:
    aoi = aoi_summary(root, config)
    missing = missing_required_dirs(root)
    return [
        f"Project: {config['project']['name']}",
        f"Stage: {config['project']['stage']}",
        f"Root: {root}",
        f"AOI: {aoi['name']}",
        f"AOI file: {aoi['path']}",
        f"AOI bbox: {aoi['bbox']}",
        f"AOI source: OpenStreetMap {aoi['osm']}",
        f"Analysis CRS: {aoi['analysis_crs']}",
        f"Indices: {', '.join(config['satellite']['indices'])}",
        f"DEM products: {', '.join(config['dem']['products'])}",
        "Required directories: OK" if not missing else f"Missing directories: {', '.join(missing)}",
    ]


class WaterRegimeApp:
    def __init__(self, root: Path) -> None:
        self.root_path = root
        self.config = load_config(root)
        self.window = Tk()
        self.window.title("water-regime-gis")
        self.window.geometry("980x640")
        self.window.minsize(820, 520)
        self._build()
        self.write("\n".join(status_lines(self.root_path, self.config)))

    def _build(self) -> None:
        header = Frame(self.window, padx=16, pady=14)
        header.pack(fill=X)
        Label(header, text="water-regime-gis", font=("Arial", 22, "bold")).pack(anchor="w")
        Label(
            header,
            text="QGIS-oriented control panel for AOI, checks and processing scripts",
            font=("Arial", 12),
        ).pack(anchor="w")

        actions = Frame(self.window, padx=16, pady=8)
        actions.pack(fill=X)
        Button(actions, text="Check project", command=self.run_project_check, width=18).pack(side=LEFT, padx=(0, 8))
        Button(actions, text="Run QGIS check", command=self.run_qgis_check, width=18).pack(side=LEFT, padx=(0, 8))
        Button(actions, text="Open AOI folder", command=self.open_aoi_folder, width=18).pack(side=LEFT, padx=(0, 8))
        Button(actions, text="Quit", command=self.window.destroy, width=12).pack(side=RIGHT)

        body = Frame(self.window, padx=16, pady=10)
        body.pack(fill=BOTH, expand=True)
        self.log = ScrolledText(body, wrap="word", font=("Menlo", 12))
        self.log.pack(fill=BOTH, expand=True)

    def write(self, text: str) -> None:
        self.log.insert(END, text + "\n")
        self.log.see(END)

    def run(self) -> None:
        self.window.mainloop()

    def run_command(self, command: list[str]) -> None:
        def worker() -> None:
            self.window.after(0, self.write, f"\n$ {' '.join(command)}")
            process = subprocess.run(command, cwd=self.root_path, text=True, capture_output=True)
            if process.stdout:
                self.window.after(0, self.write, process.stdout.rstrip())
            if process.stderr:
                self.window.after(0, self.write, process.stderr.rstrip())
            self.window.after(0, self.write, f"Exit code: {process.returncode}")

        threading.Thread(target=worker, daemon=True).start()

    def run_project_check(self) -> None:
        self.run_command([sys.executable, "scripts/check_project.py"])

    def run_qgis_check(self) -> None:
        qgis_python = self.config["qgis"].get("python_executable", "")
        script = self.config["qgis"].get("script_runner", "")
        if not qgis_python:
            self.write("\nQGIS Python is not configured. Set qgis.python_executable in configs/project.example.json.")
            return
        self.run_command([qgis_python, script])

    def open_aoi_folder(self) -> None:
        path = self.root_path / self.config["paths"]["aoi"]
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])


def main() -> int:
    WaterRegimeApp(project_root()).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
