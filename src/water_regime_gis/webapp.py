from __future__ import annotations

import html
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from .project import load_config, missing_required_dirs, project_root, selected_field_summary


WMS_CACHE_TTL_SECONDS = 300
WMS_CACHE_MAX_ITEMS = 256
WMS_CACHE: OrderedDict[str, tuple[float, str, bytes]] = OrderedDict()
WMS_CACHE_LOCK = threading.Lock()
BOOTSTRAP_STATE = {
    "running": False,
    "started_at": "",
    "finished_at": "",
    "steps": [],
}
BOOTSTRAP_LOCK = threading.Lock()
JOB_STATE = {
    "running": False,
    "kind": "",
    "label": "",
    "started_at": "",
    "finished_at": "",
    "status": "",
    "output": "",
}
JOB_LOCK = threading.Lock()
DEFAULT_PORT = 8765

STYLE = """
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#eef3f1;color:#14231f}
.shell{max-width:1180px;margin:0 auto;padding:28px}
.top{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:18px}
h1{margin:0;font-size:34px;letter-spacing:0}.sub{color:#53645f;margin-top:6px;font-size:16px}
.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}.panel{background:white;border:1px solid #d8e0dd;border-radius:8px;padding:18px}
.kpi{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}.tile{background:#f8fbfa;border:1px solid #dbe5e1;border-radius:8px;padding:14px}
.label{color:#60716c;font-size:13px}.value{font-size:18px;font-weight:700;margin-top:5px}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}.btn{display:inline-block;background:#176b5b;color:white;text-decoration:none;border-radius:7px;padding:11px 14px;font-weight:700}.btn.disabled{background:#8d9a95;cursor:not-allowed}
.map{height:360px;border:1px solid #d8e0dd;border-radius:8px;overflow:hidden;background:#dce7e3}.form{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.form input{padding:10px;border:1px solid #bdcac5;border-radius:7px;min-width:150px}.form button{border:0;cursor:pointer}
.result-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}.hint{color:#60716c;font-size:14px;margin:8px 0 0}
.status-list{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.status-item{background:#f8fbfa;border:1px solid #dbe5e1;border-radius:8px;padding:12px}.status-ok{color:#176b5b}.status-run{color:#8a5a00}.status-fail{color:#a33425}
.btn.secondary{background:#42526a}.btn.muted{background:#68757f}
pre{white-space:pre-wrap;background:#101816;color:#d8f5e9;border-radius:8px;padding:14px;min-height:180px;overflow:auto}
.preview{width:100%;border:1px solid #d8e0dd;border-radius:8px;margin-top:12px;background:#f8fbfa}
table{width:100%;border-collapse:collapse}td{padding:8px 0;border-bottom:1px solid #edf1ef}td:first-child{color:#60716c;width:160px}
@media(max-width:860px){.grid,.kpi,.status-list{grid-template-columns:1fr}.top{display:block}}
"""


def run_command(root: Path, command: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("PROJ_DATA", "/Applications/QGIS.app/Contents/Resources/qgis/proj")
    process = subprocess.run(command, cwd=root, text=True, capture_output=True, env=env)
    output = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part)
    return process.returncode, output or "(no output)"


def find_available_port(host: str = "127.0.0.1", start: int = DEFAULT_PORT, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port found from {start} to {start + attempts - 1}")


def start_bootstrap(root: Path) -> None:
    with BOOTSTRAP_LOCK:
        if BOOTSTRAP_STATE["running"]:
            return
    thread = threading.Thread(target=bootstrap_system, args=(root,), daemon=True)
    thread.start()


def bootstrap_system(root: Path) -> None:
    config = load_config(root)
    with BOOTSTRAP_LOCK:
        BOOTSTRAP_STATE["running"] = True
        BOOTSTRAP_STATE["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        BOOTSTRAP_STATE["finished_at"] = ""
        BOOTSTRAP_STATE["steps"] = []

    for label, command in [
        ("Проверка структуры", [sys.executable, "scripts/check_project.py"]),
        ("Подготовка кадастрового модуля", [sys.executable, "scripts/install_nspd_plugin.py"]),
    ]:
        code, output = run_command(root, command)
        record_bootstrap_step(label, code, output)
        if code:
            finish_bootstrap()
            return

    qgis = qgis_python(config)
    if not qgis:
        record_bootstrap_step("Проверка геодвижка", 1, "Геодвижок не найден. Установите QGIS 3.40+ и повторите запуск.")
        finish_bootstrap()
        return

    for label, command in [
        ("Проверка геодвижка", [qgis, config["qgis"]["script_runner"]]),
        ("Проверка кадастровых данных", [qgis, config["qgis"]["nspd_plugin_check_script"]]),
    ]:
        code, output = run_command(root, command)
        record_bootstrap_step(label, code, output)
        if code:
            finish_bootstrap()
            return

    finish_bootstrap()


def record_bootstrap_step(label: str, code: int, output: str) -> None:
    with BOOTSTRAP_LOCK:
        BOOTSTRAP_STATE["steps"].append(
            {
                "label": label,
                "status": "OK" if code == 0 else "FAILED",
                "message": public_output(label, output, code),
            }
        )


def finish_bootstrap() -> None:
    with BOOTSTRAP_LOCK:
        BOOTSTRAP_STATE["running"] = False
        BOOTSTRAP_STATE["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")


def start_panel_job(root: Path, kind: str) -> dict:
    labels = {
        "check-system": "Проверка системы",
        "prepare-result": "Подготовка результата",
        "select-field": "Выбор поля",
    }
    if kind not in labels:
        return {"started": False, "error": "Неизвестная задача.", "job": job_status()}
    if kind == "select-field":
        return {"started": False, "error": "Укажите координаты выбранной точки.", "job": job_status()}
    if kind == "prepare-result":
        config = load_config(root)
        if not selected_field_summary(root, config)["selected"]:
            return {"started": False, "error": "Сначала выберите точку поля.", "job": job_status()}
    with JOB_LOCK:
        if JOB_STATE["running"]:
            return {"started": False, "error": "Задача уже выполняется.", "job": dict(JOB_STATE)}
        JOB_STATE.update(
            {
                "running": True,
                "kind": kind,
                "label": labels[kind],
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "finished_at": "",
                "status": "RUNNING",
                "output": f"{labels[kind]} запущена. Панель обновит лог автоматически.",
            }
        )
    thread = threading.Thread(target=run_panel_job, args=(root, kind), daemon=True)
    thread.start()
    return {"started": True, "job": job_status()}


def start_select_field_job(root: Path, lon: str, lat: str) -> dict:
    if not lon or not lat:
        return {"started": False, "error": "Выберите точку на карте.", "job": job_status()}
    with JOB_LOCK:
        if JOB_STATE["running"]:
            return {"started": False, "error": "Задача уже выполняется.", "job": dict(JOB_STATE)}
        JOB_STATE.update(
            {
                "running": True,
                "kind": "select-field",
                "label": "Выбор поля",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "finished_at": "",
                "status": "RUNNING",
                "output": "Выбор поля запущен. Панель обновит лог автоматически.",
            }
        )
    thread = threading.Thread(target=run_select_field_job, args=(root, lon, lat), daemon=True)
    thread.start()
    return {"started": True, "job": job_status()}


def run_panel_job(root: Path, kind: str) -> None:
    output = run_workflow(root, create_project=kind == "prepare-result")
    failed = "FAILED" in output
    with JOB_LOCK:
        JOB_STATE["running"] = False
        JOB_STATE["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        JOB_STATE["status"] = "FAILED" if failed else "OK"
        JOB_STATE["output"] = output


def run_select_field_job(root: Path, lon: str, lat: str) -> None:
    output = select_field(root, lon, lat)
    failed = "FAILED" in output
    with JOB_LOCK:
        JOB_STATE["running"] = False
        JOB_STATE["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        JOB_STATE["status"] = "FAILED" if failed else "OK"
        JOB_STATE["output"] = output


def job_status() -> dict:
    with JOB_LOCK:
        return dict(JOB_STATE)


def qgis_python(config: dict) -> str:
    configured = config["qgis"].get("python_executable", "")
    if configured:
        return configured
    candidates = [
        "/Applications/QGIS.app/Contents/MacOS/python",
        "/Applications/QGIS.app/Contents/MacOS/bin/python",
        "/Applications/QGIS.app/Contents/MacOS/python3.12",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def page(root: Path, output: str = "") -> str:
    config = load_config(root)
    field = selected_field_summary(root, config)
    missing = missing_required_dirs(root)
    contour = "не выбран"
    if field["selected"]:
        contour = "кадастровый контур" if field.get("source") == "nspd_getfeatureinfo" else "временная рабочая область"
    rows = {
        "Проект": config["project"]["name"],
        "Этап": config["project"]["stage"],
        "Поле": field["name"],
        "Контур": contour,
        "Долгота": field["lon"],
        "Широта": field["lat"],
        "Рабочая CRS": field["analysis_crs"],
        "Индексы": ", ".join(config["satellite"]["indices"]),
    }
    table = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows.items())
    status = "OK" if not missing else ", ".join(missing)
    latest_job = job_status()
    visible_output = output or latest_job.get("output") or "Нажмите кнопку, чтобы запустить проверку."
    escaped_output = html.escape(visible_output)
    preview = root / "outputs/maps/water_regime_gis_preview.png"
    preview_html = '<img class="preview" src="/preview.png" alt="preview результата">' if preview.exists() else ""
    system_html = system_panel(root, config)
    results_html = result_panel(root, config)
    prepare_action = (
        '<a class="btn" href="/run/prepare-result" data-job="prepare-result">Подготовить результат</a>'
        if field["selected"]
        else '<span class="btn disabled" title="Сначала выберите точку поля">Подготовить результат</span>'
    )
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>water-regime-gis</title><style>{STYLE}</style></head>
<body><main class="shell">
<section class="top"><div><h1>water-regime-gis</h1><div class="sub">Панель выбора поля, кадастровых границ и результатов обработки</div></div></section>
<section class="kpi">
  <div class="tile"><div class="label">Структура</div><div class="value">{html.escape(status)}</div></div>
  <div class="tile"><div class="label">Поле</div><div class="value">{'выбрано' if field['selected'] else 'не выбрано'}</div></div>
  <div class="tile"><div class="label">Рабочая CRS</div><div class="value">{html.escape(field['analysis_crs'])}</div></div>
</section>
{system_html}
<section class="panel">
  <h2>Выбор поля</h2>
  <div id="map" class="map"></div>
  <form class="form" action="/run/select-field" method="get">
    <input id="lat" name="lat" placeholder="Широта" value="{html.escape(str(field['lat']))}" required>
    <input id="lon" name="lon" placeholder="Долгота" value="{html.escape(str(field['lon']))}" required>
    <button class="btn" type="submit">Сохранить выбранное поле</button>
  </form>
</section>
<div class="actions">
  {prepare_action}
  <a class="btn secondary" href="/run/check-system" data-job="check-system">Проверить систему</a>
</div>
<section class="grid">
  <div class="panel"><h2>Состояние</h2><table>{table}</table></div>
  <div class="panel"><h2>Лог</h2><pre id="run-log">{escaped_output}</pre>{preview_html}</div>
</section>
{results_html}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const latInput = document.getElementById("lat");
const lonInput = document.getElementById("lon");
const start = [{field['lat'] or 53.84}, {field['lon'] or 38.107}];
const map = L.map("map").setView(start, {13 if field['selected'] else 11});
L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{maxZoom: 19, attribution: "&copy; OpenStreetMap"}}).addTo(map);
L.tileLayer.wms("/nspd/wms", {{
  layers: "36048",
  format: "image/png",
  transparent: true,
  version: "1.3.0",
  attribution: "НСПД"
}}).addTo(map);
let marker = {f"L.marker(start).addTo(map)" if field['selected'] else "null"};
let selectedLayer = null;
const selectedStyle = {{color: "#f57c00", weight: 3, fillColor: "#ffd54f", fillOpacity: 0.24}};
const hoverStyle = {{color: "#00a6a6", weight: 5, fillColor: "#80cbc4", fillOpacity: 0.34}};
fetch("/selected-field-area.geojson")
  .then((response) => response.ok ? response.json() : null)
  .then((geojson) => {{
    if (!geojson) return;
    selectedLayer = L.geoJSON(geojson, {{
      style: selectedStyle,
      onEachFeature: (_feature, layer) => {{
        layer.on("mouseover", () => layer.setStyle(hoverStyle));
        layer.on("mouseout", () => layer.setStyle(selectedStyle));
        layer.on("click", () => selectedLayer.bringToFront());
      }}
    }}).addTo(map);
    selectedLayer.bringToFront();
  }})
  .catch(() => {{}});
map.on("click", (event) => {{
  const p = event.latlng;
  latInput.value = p.lat.toFixed(7);
  lonInput.value = p.lng.toFixed(7);
  if (marker) marker.setLatLng(p);
  else marker = L.marker(p).addTo(map);
}});
const systemStatus = document.getElementById("system-status");
const runLog = document.getElementById("run-log");
function statusText(status) {{
  if (status === "OK") return "готово";
  if (status === "RUNNING") return "выполняется";
  return "требует внимания";
}}
function statusClass(status) {{
  if (status === "OK") return "status-ok";
  if (status === "RUNNING") return "status-run";
  return "status-fail";
}}
function renderSystemStatus(payload) {{
  if (!systemStatus || !payload || !Array.isArray(payload.steps)) return;
  systemStatus.innerHTML = payload.steps.map((step) => `
    <div class="status-item">
      <div class="label">${{step.label || ""}}</div>
      <div class="value ${{statusClass(step.status)}}">${{statusText(step.status)}}</div>
      <div class="hint">${{step.message || ""}}</div>
    </div>
  `).join("");
}}
function refreshSystemStatus() {{
  fetch("/status.json")
    .then((response) => response.ok ? response.json() : null)
    .then(renderSystemStatus)
    .catch(() => {{}});
}}
refreshSystemStatus();
setInterval(refreshSystemStatus, 3000);
function renderJob(payload) {{
  const job = payload && payload.job ? payload.job : payload;
  if (!job || !runLog) return;
  if (job.output) runLog.textContent = job.output;
  if (!job.running && job.kind === "select-field" && sessionStorage.getItem("wrgJobStarted") === "select-field") {{
    sessionStorage.removeItem("wrgJobStarted");
    setTimeout(() => window.location.reload(), 800);
  }}
  if (!job.running && job.kind === "prepare-result" && sessionStorage.getItem("wrgJobStarted") === "prepare-result") {{
    sessionStorage.removeItem("wrgJobStarted");
    setTimeout(() => window.location.reload(), 800);
  }}
}}
function pollJob() {{
  fetch("/job/status")
    .then((response) => response.ok ? response.json() : null)
    .then((payload) => {{
      renderJob(payload);
      if (payload && payload.running) setTimeout(pollJob, 1500);
    }})
    .catch(() => {{}});
}}
document.querySelectorAll("[data-job]").forEach((button) => {{
  button.addEventListener("click", (event) => {{
    event.preventDefault();
    const kind = button.getAttribute("data-job");
    fetch(`/job/start?kind=${{encodeURIComponent(kind)}}`)
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => {{
        if (payload && payload.started) sessionStorage.setItem("wrgJobStarted", kind);
        renderJob(payload);
        pollJob();
      }})
      .catch(() => {{
        window.location.href = button.getAttribute("href");
      }});
  }});
}});
document.querySelector(".form").addEventListener("submit", (event) => {{
  event.preventDefault();
  const params = new URLSearchParams({{kind: "select-field", lat: latInput.value, lon: lonInput.value}});
  fetch(`/job/start?${{params.toString()}}`)
    .then((response) => response.ok ? response.json() : null)
    .then((payload) => {{
      if (payload && payload.started) sessionStorage.setItem("wrgJobStarted", "select-field");
      renderJob(payload);
      pollJob();
    }})
    .catch(() => {{
      event.target.submit();
    }});
}});
</script>
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    root_path: Path

    def do_GET(self) -> None:
        root = self.root_path
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        output = ""
        if path == "/preview.png":
            self.send_file(root / "outputs/maps/water_regime_gis_preview.png", "image/png")
            return
        if path == "/result.json":
            self.send_file(root / load_config(root)["paths"]["latest_report"], "application/json")
            return
        if path == "/status.json":
            self.send_json(system_status(root, load_config(root)))
            return
        if path == "/job/status":
            self.send_json(job_status())
            return
        if path == "/job/start":
            kind = (query.get("kind") or [""])[0]
            if kind == "select-field":
                self.send_json(start_select_field_job(root, (query.get("lon") or [""])[0], (query.get("lat") or [""])[0]))
            else:
                self.send_json(start_panel_job(root, kind))
            return
        if path == "/download/field.geojson":
            self.send_download(root / load_config(root)["paths"]["selected_field_area"], "selected_field_area.geojson", "application/geo+json")
            return
        if path == "/download/preview.png":
            self.send_download(root / "outputs/maps/water_regime_gis_preview.png", "water_regime_gis_preview.png", "image/png")
            return
        if path == "/download/report.json":
            self.send_download(root / load_config(root)["paths"]["latest_report"], "latest_result.json", "application/json")
            return
        if path == "/selected-field-area.geojson":
            self.send_file(root / load_config(root)["paths"]["selected_field_area"], "application/geo+json")
            return
        if path == "/nspd/wms":
            self.send_nspd_wms(root, parsed.query)
            return
        if path == "/run/check-project":
            _, output = run_command(root, [sys.executable, "scripts/check_project.py"])
        elif path == "/run/check-system":
            output = run_workflow(root, create_project=False)
        elif path == "/run/prepare-result":
            output = run_workflow(root, create_project=True)
        elif path == "/run/select-field":
            lon = (query.get("lon") or [""])[0]
            lat = (query.get("lat") or [""])[0]
            output = select_field(root, lon, lat)
        elif path == "/run/check-qgis":
            config = load_config(root)
            qgis = qgis_python(config)
            if qgis:
                _, output = run_command(root, [qgis, config["qgis"]["script_runner"]])
            else:
                output = "Геодвижок не найден. Установите QGIS 3.40+ и повторите запуск."
        elif path == "/run/check-nspd-plugin":
            config = load_config(root)
            qgis = qgis_python(config)
            if qgis:
                _, output = run_command(root, [qgis, config["qgis"]["nspd_plugin_check_script"]])
            else:
                output = "Геодвижок не найден. Установите QGIS 3.40+ и повторите запуск."
        elif path == "/run/create-demo-project":
            config = load_config(root)
            qgis = qgis_python(config)
            if qgis:
                _, output = run_command(root, [qgis, config["qgis"]["demo_project_script"]])
            else:
                output = "Геодвижок не найден. Установите QGIS 3.40+ и повторите запуск."
        elif path != "/":
            self.send_error(404)
            return
        body = page(root, output).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:
        if urlparse(self.path).path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            return
        self.send_error(404)

    def send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_download(self, path: Path, filename: str, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_nspd_wms(self, root: Path, query: str) -> None:
        cached = get_wms_cache(query)
        if cached:
            content_type, body = cached
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-WRG-Cache", "hit")
            self.end_headers()
            self.wfile.write(body)
            return

        config = load_config(root)
        layer_id = config["nspd"]["parcels_wms_layer_id"]
        url = f"https://nspd.gov.ru/api/aeggis/v3/{layer_id}/wms?{query}"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
                "Referer": "https://nspd.gov.ru/map?active_layers=%E8%B3%90",
            },
        )
        cert = nspd_ca_bundle(config)
        context = ssl.create_default_context(cafile=str(cert)) if cert.exists() else ssl.create_default_context()
        for attempt in range(2):
            try:
                with urlopen(request, timeout=20, context=context) as response:
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "image/png")
                set_wms_cache(query, content_type, body)
                self.send_response(200)
                break
            except Exception as exc:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                body = f"NSPD WMS error: {exc}".encode("utf-8")
                content_type = "text/plain; charset=utf-8"
                self.send_response(502)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-WRG-Cache", "miss")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def run_workflow(root: Path, create_project: bool) -> str:
    config = load_config(root)
    parts = []

    for label, command in [
        ("Проверка структуры", [sys.executable, "scripts/check_project.py"]),
        ("Подготовка кадастрового модуля", [sys.executable, "scripts/install_nspd_plugin.py"]),
    ]:
        code, output = run_command(root, command)
        parts.append(format_step(label, code, public_output(label, output, code)))
        if code:
            return "\n\n".join(parts)

    qgis = qgis_python(config)
    if not qgis:
        parts.append("Геодвижок: FAILED\nГеодвижок не найден. Установите QGIS 3.40+ и повторите запуск.")
        return "\n\n".join(parts)

    for label, command in [
        ("Проверка геодвижка", [qgis, config["qgis"]["script_runner"]]),
        ("Проверка кадастровых данных", [qgis, config["qgis"]["nspd_plugin_check_script"]]),
    ]:
        code, output = run_command(root, command)
        parts.append(format_step(label, code, public_output(label, output, code)))
        if code:
            return "\n\n".join(parts)

    if create_project:
        field = selected_field_summary(root, config)
        if not field["selected"]:
            parts.append("Подготовка результата: FAILED\nСначала выберите точку поля на карте и нажмите 'Сохранить выбранное поле'.")
            return "\n\n".join(parts)
        code, output = run_command(root, [qgis, config["qgis"]["resolve_boundary_script"]])
        parts.append(format_step("Уточнение контура", code, public_output("Уточнение контура", output, code)))
        if code:
            return "\n\n".join(parts)
        code, output = run_command(root, [qgis, config["qgis"]["demo_project_script"]])
        parts.append(format_step("Подготовка результата", code, public_output("Подготовка результата", output, code)))
        if code == 0:
            write_result_report(root, config, "\n\n".join(parts))

    return "\n\n".join(parts)


def select_field(root: Path, lon: str, lat: str) -> str:
    config = load_config(root)
    qgis = qgis_python(config)
    if not qgis:
        return "Выбор поля: FAILED\nГеодвижок недоступен. Установите QGIS 3.40+ и перезапустите панель."
    if not lon or not lat:
        return "Выбор поля: FAILED\nВыберите точку на карте или введите широту и долготу."

    select_code, select_output = run_command(root, [qgis, config["qgis"]["select_field_script"], "--lon", lon, "--lat", lat])
    if select_code:
        return format_step("Выбор поля", select_code, public_output("Выбор поля", select_output, select_code))

    boundary_code, boundary_output = run_command(root, [qgis, config["qgis"]["resolve_boundary_script"]])
    return "\n\n".join(
        [
            format_step("Выбор поля", 0, public_output("Выбор поля", select_output, 0)),
            format_step("Уточнение контура", boundary_code, public_output("Уточнение контура", boundary_output, boundary_code)),
        ]
    )


def format_step(label: str, code: int, output: str) -> str:
    status = "OK" if code == 0 else "FAILED"
    return f"{label}: {status}\n{output}"


def public_output(label: str, output: str, code: int) -> str:
    if code:
        if label == "Проверка структуры":
            return "Не найдены необходимые рабочие папки проекта."
        if label == "Подготовка кадастрового модуля":
            return "Не удалось подготовить кадастровый модуль. Проверьте интернет-соединение и повторите запуск."
        if label == "Проверка геодвижка":
            return "Геодвижок недоступен. Установите QGIS 3.40+ и перезапустите панель."
        if label == "Проверка кадастровых данных":
            return "Кадастровый модуль недоступен. Панель попробует подготовить его при следующем запуске."
        if label == "Выбор поля":
            return "Не удалось сохранить выбранную точку поля."
        if label == "Уточнение контура":
            return "Не удалось уточнить кадастровый контур. Повторите позже."
        if label == "Подготовка результата":
            return "Не удалось подготовить карту результата."
        return output
    if label == "Проверка структуры":
        return "Структура проекта готова."
    if label == "Подготовка кадастрового модуля":
        return "Кадастровый модуль готов."
    if label == "Проверка геодвижка":
        return "Геодвижок доступен."
    if label == "Проверка кадастровых данных":
        return "Кадастровые данные доступны."
    if label == "Выбор поля":
        return "Точка поля сохранена."
    if label == "Уточнение контура":
        if "Boundary source: nspd_getfeatureinfo" in output:
            return "Кадастровый контур найден по выбранной точке."
        if "Boundary source: map_point_buffer" in output:
            return "Кадастровый контур пока недоступен, используется временная рабочая область вокруг точки."
        return "Контур проверен."
    if label == "Подготовка результата":
        lines = []
        for line in output.splitlines():
            if line.startswith("Preview:"):
                lines.append("Карта результата подготовлена.")
            elif line.startswith("Project CRS:"):
                lines.append(f"CRS результата: {line.split(':', 1)[1].strip()}.")
        return "\n".join(lines) or "Карта результата подготовлена."
    return output


def system_panel(root: Path, config: dict) -> str:
    status = system_status(root, config)
    steps = status["steps"]
    items = []
    for step in steps:
        state = step["status"]
        css = "status-ok" if state == "OK" else "status-run" if state == "RUNNING" else "status-fail"
        text = "готово" if state == "OK" else "выполняется" if state == "RUNNING" else "требует внимания"
        items.append(
            '<div class="status-item">'
            f'<div class="label">{html.escape(step["label"])}</div>'
            f'<div class="value {css}">{html.escape(text)}</div>'
            f'<div class="hint">{html.escape(step.get("message", ""))}</div>'
            "</div>"
        )
    finished = f'<p class="hint">Последняя автоподготовка: {html.escape(status["finished_at"])}</p>' if status["finished_at"] else ""
    return f"""
<section class="panel">
  <h2>Готовность системы</h2>
  <div id="system-status" class="status-list">{''.join(items)}</div>
  {finished}
</section>"""


def system_status(root: Path, config: dict) -> dict:
    with BOOTSTRAP_LOCK:
        state = {
            "running": BOOTSTRAP_STATE["running"],
            "started_at": BOOTSTRAP_STATE["started_at"],
            "finished_at": BOOTSTRAP_STATE["finished_at"],
            "steps": list(BOOTSTRAP_STATE["steps"]),
        }

    steps = state["steps"]
    if not steps:
        steps = lightweight_status(root, config)
        if state["running"]:
            steps.insert(0, {"label": "Автоподготовка", "status": "RUNNING", "message": "Выполняется."})
    return {
        "running": state["running"],
        "started_at": state["started_at"],
        "finished_at": state["finished_at"],
        "steps": steps,
    }


def lightweight_status(root: Path, config: dict) -> list[dict]:
    missing = missing_required_dirs(root)
    qgis = qgis_python(config)
    plugin_dir = nspd_plugin_dir(config)
    field = selected_field_summary(root, config)
    return [
        {
            "label": "Структура",
            "status": "OK" if not missing else "FAILED",
            "message": "Структура проекта готова." if not missing else "Не найдены рабочие папки.",
        },
        {
            "label": "Геодвижок",
            "status": "OK" if qgis else "FAILED",
            "message": "Геодвижок найден." if qgis else "Установите QGIS 3.40+ и перезапустите панель.",
        },
        {
            "label": "Кадастровый модуль",
            "status": "OK" if plugin_dir.exists() else "RUNNING",
            "message": "Кадастровый модуль готов." if plugin_dir.exists() else "Будет установлен автоматически.",
        },
        {
            "label": "Поле",
            "status": "OK" if field["selected"] else "RUNNING",
            "message": "Поле выбрано." if field["selected"] else "Выберите точку на карте.",
        },
    ]


def result_panel(root: Path, config: dict) -> str:
    report_path = root / config["paths"]["latest_report"]
    preview_path = root / "outputs/maps/water_regime_gis_preview.png"
    field_path = root / config["paths"]["selected_field_area"]
    if not report_path.exists() and not preview_path.exists():
        return ""

    rows = []
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
        rows.extend(
            [
                ("Статус", report.get("status", "готово")),
                ("Время подготовки", report.get("created_at", "")),
                ("Площадь области", f"{report.get('field', {}).get('area_ha', '')} га"),
                ("CRS", report.get("field", {}).get("analysis_crs", "")),
            ]
        )
    else:
        rows.append(("Статус", "preview готов"))

    table = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows if str(v))
    links = []
    if preview_path.exists():
        links.append('<a class="btn secondary" href="/download/preview.png">Скачать preview</a>')
    if field_path.exists():
        links.append('<a class="btn secondary" href="/download/field.geojson">Скачать контур</a>')
    if report_path.exists():
        links.append('<a class="btn muted" href="/download/report.json">Скачать отчет JSON</a>')
    actions = "".join(links)
    return f"""
<section class="panel">
  <h2>Результаты</h2>
  <table>{table}</table>
  <div class="result-actions">{actions}</div>
  <p class="hint">Все данные подготовлены автоматически. Открывать внешние программы для этого не нужно.</p>
</section>"""


def write_result_report(root: Path, config: dict, log: str) -> None:
    field = selected_field_summary(root, config)
    paths = {
        "preview": (root / "outputs/maps/water_regime_gis_preview.png", "/download/preview.png"),
        "field_area": (root / config["paths"]["selected_field_area"], "/download/field.geojson"),
    }
    report = {
        "status": "OK",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "field": {
            "name": field["name"],
            "lon": field["lon"],
            "lat": field["lat"],
            "area_ha": field["area_ha"],
            "analysis_crs": field["analysis_crs"],
            "source": field.get("source", ""),
        },
        "artifacts": {
            name: {"url": url, "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0}
            for name, (path, url) in paths.items()
        },
        "log": log,
    }
    report_path = root / config["paths"]["latest_report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nspd_ca_bundle(config: dict) -> Path:
    plugin_dir = nspd_plugin_dir(config)
    cert = plugin_dir / "certs/nspd-ca-bundle.pem"
    if cert.exists():
        return cert
    return plugin_dir / "certs/nspd-ca-bundle.pem"


def nspd_plugin_dir(config: dict) -> Path:
    plugin_id = config["nspd"]["plugin_id"]
    plugin_name = config["nspd"]["plugin_name"]
    base = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
    for name in (plugin_id, plugin_name):
        plugin = base / name
        if plugin.exists():
            return plugin
    return base / plugin_id


def get_wms_cache(key: str) -> tuple[str, bytes] | None:
    now = time.time()
    with WMS_CACHE_LOCK:
        cached = WMS_CACHE.get(key)
        if not cached:
            return None
        created, content_type, body = cached
        if now - created > WMS_CACHE_TTL_SECONDS:
            WMS_CACHE.pop(key, None)
            return None
        WMS_CACHE.move_to_end(key)
        return content_type, body


def set_wms_cache(key: str, content_type: str, body: bytes) -> None:
    with WMS_CACHE_LOCK:
        WMS_CACHE[key] = (time.time(), content_type, body)
        WMS_CACHE.move_to_end(key)
        while len(WMS_CACHE) > WMS_CACHE_MAX_ITEMS:
            WMS_CACHE.popitem(last=False)


def main() -> int:
    root = project_root()
    Handler.root_path = root
    port = find_available_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    os.environ["WATER_REGIME_GIS_APP_URL"] = url
    print(f"water-regime-gis app: {url}")
    start_bootstrap(root)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
