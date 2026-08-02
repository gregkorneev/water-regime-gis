from __future__ import annotations

import html
import os
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .project import aoi_summary, load_config, missing_required_dirs, project_root


STYLE = """
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#eef3f1;color:#14231f}
.shell{max-width:1180px;margin:0 auto;padding:28px}
.top{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:18px}
h1{margin:0;font-size:34px;letter-spacing:0}.sub{color:#53645f;margin-top:6px;font-size:16px}
.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}.panel{background:white;border:1px solid #d8e0dd;border-radius:8px;padding:18px}
.kpi{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}.tile{background:#f8fbfa;border:1px solid #dbe5e1;border-radius:8px;padding:14px}
.label{color:#60716c;font-size:13px}.value{font-size:18px;font-weight:700;margin-top:5px}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}.btn{display:inline-block;background:#176b5b;color:white;text-decoration:none;border-radius:7px;padding:11px 14px;font-weight:700}
.btn.secondary{background:#42526a}.btn.muted{background:#68757f}
pre{white-space:pre-wrap;background:#101816;color:#d8f5e9;border-radius:8px;padding:14px;min-height:180px;overflow:auto}
table{width:100%;border-collapse:collapse}td{padding:8px 0;border-bottom:1px solid #edf1ef}td:first-child{color:#60716c;width:160px}
@media(max-width:860px){.grid,.kpi{grid-template-columns:1fr}.top{display:block}}
"""


def run_command(root: Path, command: list[str]) -> tuple[int, str]:
    process = subprocess.run(command, cwd=root, text=True, capture_output=True)
    output = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part)
    return process.returncode, output or "(no output)"


def page(root: Path, output: str = "") -> str:
    config = load_config(root)
    aoi = aoi_summary(root, config)
    missing = missing_required_dirs(root)
    rows = {
        "Project": config["project"]["name"],
        "Stage": config["project"]["stage"],
        "AOI": aoi["name"],
        "AOI file": aoi["path"],
        "AOI source": f"OpenStreetMap {aoi['osm']}",
        "BBox": aoi["bbox"],
        "Analysis CRS": aoi["analysis_crs"],
        "Indices": ", ".join(config["satellite"]["indices"]),
    }
    table = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows.items())
    status = "OK" if not missing else ", ".join(missing)
    escaped_output = html.escape(output or "Нажмите кнопку, чтобы запустить проверку.")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>water-regime-gis</title><style>{STYLE}</style></head>
<body><main class="shell">
<section class="top"><div><h1>water-regime-gis</h1><div class="sub">Панель запуска проверок, AOI и будущих QGIS-скриптов</div></div></section>
<section class="kpi">
  <div class="tile"><div class="label">Структура</div><div class="value">{html.escape(status)}</div></div>
  <div class="tile"><div class="label">Площадь AOI</div><div class="value">~{aoi['area_ha']} га</div></div>
  <div class="tile"><div class="label">Рабочая CRS</div><div class="value">{html.escape(aoi['analysis_crs'])}</div></div>
</section>
<div class="actions">
  <a class="btn" href="/run/check-project">Проверить проект</a>
  <a class="btn" href="/run/check-aoi">Проверить AOI</a>
  <a class="btn secondary" href="/run/check-qgis">Проверить QGIS</a>
  <a class="btn muted" href="/open-aoi">Открыть AOI</a>
</div>
<section class="grid">
  <div class="panel"><h2>Состояние</h2><table>{table}</table></div>
  <div class="panel"><h2>Лог</h2><pre>{escaped_output}</pre></div>
</section>
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    root_path: Path

    def do_GET(self) -> None:
        root = self.root_path
        path = urlparse(self.path).path
        output = ""
        if path == "/run/check-project":
            _, output = run_command(root, [sys.executable, "scripts/check_project.py"])
        elif path == "/run/check-aoi":
            _, output = run_command(root, [sys.executable, "scripts/check_aoi.py", "--write-normalized"])
        elif path == "/run/check-qgis":
            config = load_config(root)
            qgis_python = config["qgis"].get("python_executable", "")
            if qgis_python:
                _, output = run_command(root, [qgis_python, config["qgis"]["script_runner"]])
            else:
                output = "QGIS Python не настроен. Укажите qgis.python_executable в configs/project.example.json."
        elif path == "/open-aoi":
            open_path(root / load_config(root)["paths"]["aoi"])
            output = "Папка AOI открыта."
        elif path != "/":
            self.send_error(404)
            return
        body = page(root, output).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def open_path(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def main() -> int:
    root = project_root()
    Handler.root_path = root
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    url = "http://127.0.0.1:8765"
    print(f"water-regime-gis app: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
