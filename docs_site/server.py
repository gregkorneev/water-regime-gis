"""Dependency-free localhost server for the project documentation."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = ROOT / "docs"
STATIC_ROOT = Path(__file__).resolve().parent / "static"


def documents() -> list[dict[str, str]]:
    """Return all project Markdown documents, ordered for the navigation."""
    result = []
    for path in sorted(DOCS_ROOT.rglob("*.md")):
        relative = path.relative_to(ROOT).as_posix()
        title = next(
            (line[2:].strip() for line in path.read_text(encoding="utf-8").splitlines()
             if line.startswith("# ")),
            path.stem.replace("_", " "),
        )
        result.append({"path": relative, "title": title, "section": path.parent.name})
    return result


def document_path(value: str) -> Path | None:
    """Resolve only existing Markdown files inside docs/ (no path traversal)."""
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(DOCS_ROOT.resolve())
    except ValueError:
        return None
    return candidate if candidate.suffix == ".md" and candidate.is_file() else None


class WikiHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by http.server
        request = urlparse(self.path)
        if request.path == "/api/documents":
            return self.send_json(documents())
        if request.path == "/api/document":
            path = document_path(parse_qs(request.query).get("path", [""])[0])
            if not path:
                self.send_error(HTTPStatus.NOT_FOUND, "Документ не найден")
                return
            return self.send_text(path.read_text(encoding="utf-8"))
        if request.path in {"/", "/index.html"}:
            self.path = "/index.html"
        return super().do_GET()

    def send_json(self, value: object) -> None:
        self.send_text(json.dumps(value, ensure_ascii=False), "application/json; charset=utf-8")

    def send_text(self, value: str, content_type: str = "text/plain; charset=utf-8") -> None:
        encoded = value.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def translate_path(self, path: str) -> str:
        return str(STATIC_ROOT / Path(super().translate_path(path)).name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальный просмотрщик wiki Water Regime GIS")
    parser.add_argument("--host", default="127.0.0.1", help="адрес сервера (по умолчанию: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="порт сервера (по умолчанию: 8000)")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), WikiHandler)
    print(f"Wiki доступна: http://{args.host}:{args.port}")
    print("Для остановки нажмите Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.server_close()
