from __future__ import annotations

import html
import os
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

STYLE = """
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#eef3f1;color:#14231f}
.shell{max-width:1180px;margin:0 auto;padding:28px}
.top{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:18px}
h1{margin:0;font-size:34px;letter-spacing:0}.sub{color:#53645f;margin-top:6px;font-size:16px}
.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}.panel{background:white;border:1px solid #d8e0dd;border-radius:8px;padding:18px}
.kpi{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}.tile{background:#f8fbfa;border:1px solid #dbe5e1;border-radius:8px;padding:14px}
.label{color:#60716c;font-size:13px}.value{font-size:18px;font-weight:700;margin-top:5px}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}.btn{display:inline-block;background:#176b5b;color:white;text-decoration:none;border-radius:7px;padding:11px 14px;font-weight:700}
.map{height:360px;border:1px solid #d8e0dd;border-radius:8px;overflow:hidden;background:#dce7e3}.form{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.form input{padding:10px;border:1px solid #bdcac5;border-radius:7px;min-width:150px}.form button{border:0;cursor:pointer}
.btn.secondary{background:#42526a}.btn.muted{background:#68757f}
pre{white-space:pre-wrap;background:#101816;color:#d8f5e9;border-radius:8px;padding:14px;min-height:180px;overflow:auto}
.preview{width:100%;border:1px solid #d8e0dd;border-radius:8px;margin-top:12px;background:#f8fbfa}
table{width:100%;border-collapse:collapse}td{padding:8px 0;border-bottom:1px solid #edf1ef}td:first-child{color:#60716c;width:160px}
@media(max-width:860px){.grid,.kpi{grid-template-columns:1fr}.top{display:block}}
"""


def run_command(root: Path, command: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("PROJ_DATA", "/Applications/QGIS.app/Contents/Resources/qgis/proj")
    process = subprocess.run(command, cwd=root, text=True, capture_output=True, env=env)
    output = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part)
    return process.returncode, output or "(no output)"


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
    project_file = root / config["qgis"]["project_file"]
    rows = {
        "Project": config["project"]["name"],
        "Stage": config["project"]["stage"],
        "Selected field": field["name"],
        "Field point": field["point_path"],
        "Working area": field["path"],
        "Result project": project_file,
        "Point lon": field["lon"],
        "Point lat": field["lat"],
        "Analysis CRS": field["analysis_crs"],
        "Indices": ", ".join(config["satellite"]["indices"]),
    }
    table = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows.items())
    status = "OK" if not missing else ", ".join(missing)
    escaped_output = html.escape(output or "Нажмите кнопку, чтобы запустить проверку.")
    preview = root / "outputs/maps/water_regime_gis_preview.png"
    preview_html = '<img class="preview" src="/preview.png" alt="QGIS preview">' if preview.exists() else ""
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
  <a class="btn" href="/run/prepare-result">Подготовить результат</a>
  <a class="btn secondary" href="/run/check-system">Проверить систему</a>
</div>
<section class="grid">
  <div class="panel"><h2>Состояние</h2><table>{table}</table></div>
  <div class="panel"><h2>Лог</h2><pre>{escaped_output}</pre>{preview_html}</div>
</section>
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
            config = load_config(root)
            qgis = qgis_python(config)
            lon = (query.get("lon") or [""])[0]
            lat = (query.get("lat") or [""])[0]
            if not qgis:
                output = "QGIS Python не найден. Укажите qgis.python_executable в configs/project.example.json."
            elif not lon or not lat:
                output = "Выберите точку на карте или введите широту и долготу."
            else:
                _, output = run_command(root, [qgis, config["qgis"]["select_field_script"], "--lon", lon, "--lat", lat])
        elif path == "/run/check-qgis":
            config = load_config(root)
            qgis = qgis_python(config)
            if qgis:
                _, output = run_command(root, [qgis, config["qgis"]["script_runner"]])
            else:
                output = "QGIS Python не найден. Укажите qgis.python_executable в configs/project.example.json."
        elif path == "/run/check-nspd-plugin":
            config = load_config(root)
            qgis = qgis_python(config)
            if qgis:
                _, output = run_command(root, [qgis, config["qgis"]["nspd_plugin_check_script"]])
            else:
                output = "QGIS Python не найден. Укажите qgis.python_executable в configs/project.example.json."
        elif path == "/run/create-demo-project":
            config = load_config(root)
            qgis = qgis_python(config)
            if qgis:
                _, output = run_command(root, [qgis, config["qgis"]["demo_project_script"]])
            else:
                output = "QGIS Python не найден. Укажите qgis.python_executable в configs/project.example.json."
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
        parts.append(format_step(label, code, output))
        if code:
            return "\n\n".join(parts)

    qgis = qgis_python(config)
    if not qgis:
        parts.append("Геодвижок: FAILED\nQGIS не найден. Установите QGIS 3.40+ и повторите запуск.")
        return "\n\n".join(parts)

    for label, command in [
        ("Проверка геодвижка", [qgis, config["qgis"]["script_runner"]]),
        ("Проверка кадастровых данных", [qgis, config["qgis"]["nspd_plugin_check_script"]]),
    ]:
        code, output = run_command(root, command)
        parts.append(format_step(label, code, output))
        if code:
            return "\n\n".join(parts)

    if create_project:
        field = selected_field_summary(root, config)
        if not field["selected"]:
            parts.append("Подготовка результата: FAILED\nСначала выберите точку поля на карте и нажмите 'Сохранить выбранное поле'.")
            return "\n\n".join(parts)
        code, output = run_command(root, [qgis, config["qgis"]["demo_project_script"]])
        parts.append(format_step("Подготовка результата", code, output))

    return "\n\n".join(parts)


def format_step(label: str, code: int, output: str) -> str:
    status = "OK" if code == 0 else "FAILED"
    return f"{label}: {status}\n{output}"


def nspd_ca_bundle(config: dict) -> Path:
    plugin_id = config["nspd"]["plugin_id"]
    plugin_name = config["nspd"]["plugin_name"]
    base = Path.home() / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
    for name in (plugin_id, plugin_name):
        cert = base / name / "certs/nspd-ca-bundle.pem"
        if cert.exists():
            return cert
    return base / plugin_id / "certs/nspd-ca-bundle.pem"


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
