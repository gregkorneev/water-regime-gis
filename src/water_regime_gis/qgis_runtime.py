from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path


def qgis_python_candidates() -> list[Path]:
    env = os.environ.get("WATER_REGIME_GIS_QGIS_PYTHON", "")
    candidates = [Path(env)] if env else []
    system = platform.system()
    if system == "Darwin":
        candidates.extend(
            [
                Path("/Applications/QGIS.app/Contents/MacOS/python"),
                Path("/Applications/QGIS.app/Contents/MacOS/bin/python"),
                Path("/Applications/QGIS.app/Contents/MacOS/python3.12"),
            ]
        )
    elif system == "Windows":
        candidates.extend(sorted(Path("C:/Program Files").glob("QGIS*/bin/python-qgis.bat"), reverse=True))
        candidates.extend(sorted(Path("C:/OSGeo4W").glob("bin/python-qgis.bat"), reverse=True))
    else:
        python = shutil.which("python3")
        if python and Path("/usr/lib/python3/dist-packages/qgis").exists():
            candidates.append(Path(python))
        for candidate in ("/usr/bin/python3", "/usr/local/bin/python3"):
            path = Path(candidate)
            if path.exists() and Path("/usr/lib/python3/dist-packages/qgis").exists():
                candidates.append(path)
    return candidates


def find_qgis_python(configured: str = "") -> str:
    if configured:
        return configured if Path(configured).exists() else ""
    for candidate in qgis_python_candidates():
        if candidate.exists():
            return str(candidate)
    return ""


def qgis_install_hint(system: str = "") -> str:
    system = system or platform.system()
    if system == "Darwin":
        return "Установите QGIS в /Applications/QGIS.app и перезапустите панель."
    if system == "Windows":
        return "Установите QGIS или OSGeo4W и перезапустите панель."
    return "Установите QGIS/PyQGIS или запустите Docker-вариант приложения."


def qgis_prefix_path() -> Path:
    configured = os.environ.get("QGIS_PREFIX_PATH", "")
    if configured:
        return Path(configured)
    system = platform.system()
    if system == "Darwin":
        return Path("/Applications/QGIS.app")
    if system == "Windows":
        qgis_python = find_qgis_python()
        if qgis_python:
            return Path(qgis_python).parents[1]
        return Path("C:/Program Files/QGIS")
    return Path("/usr")


def qgis_project_data_path() -> Path:
    configured = os.environ.get("PROJ_DATA", "")
    if configured:
        return Path(configured)
    system = platform.system()
    if system == "Darwin":
        return Path("/Applications/QGIS.app/Contents/Resources/qgis/proj")
    if system == "Windows":
        prefix = qgis_prefix_path()
        return prefix / "share/proj"
    return Path("/usr/share/proj")


def qgis_profile_plugins() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
    if system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "QGIS/QGIS3/profiles/default/python/plugins"
    return Path.home() / ".local/share/QGIS/QGIS3/profiles/default/python/plugins"


def configure_qgis_environment() -> None:
    os.environ.setdefault("PROJ_DATA", str(qgis_project_data_path()))
    os.environ.setdefault("QGIS_PREFIX_PATH", str(qgis_prefix_path()))
    if platform.system() == "Linux":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = Path(__file__).resolve().parents[2]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
