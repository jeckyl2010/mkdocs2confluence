"""Minimal HTTP server with livereload support for ``mk2conf preview --watch``."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Monotonically increasing counter — clients reload when they see a new value.
_reload_version: int = 0
_reload_lock = threading.Lock()


def bump_version() -> None:
    """Increment the reload version (triggers connected browser clients to reload)."""
    global _reload_version
    with _reload_lock:
        _reload_version += 1


class _Handler(BaseHTTPRequestHandler):
    serve_dir: Path  # set on the class before calling start_server()

    def log_message(self, fmt: str, *args: object) -> None:  # silence request logs
        pass

    def do_GET(self) -> None:
        if self.path == "/__livereload":
            self._send_version()
            return
        rel = self.path.lstrip("/") or "index.html"
        try:
            path = (self.serve_dir / rel).resolve()
            path.relative_to(self.serve_dir)
        except ValueError:
            self.send_error(403)
            return
        if path.exists() and path.is_file():
            self._serve_file(path)
        else:
            self.send_error(404)

    def _send_version(self) -> None:
        with _reload_lock:
            ver = str(_reload_version).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(ver)))
        self.end_headers()
        self.wfile.write(ver)

    def _serve_file(self, path: Path) -> None:
        content = path.read_bytes()
        ctype = "text/html; charset=utf-8" if path.suffix == ".html" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def start_server(serve_dir: Path, port: int = 8765) -> HTTPServer:
    """Start the HTTP server in a daemon thread. Returns the server object."""
    _Handler.serve_dir = serve_dir.resolve()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def watch_and_rebuild(
    docs_dir: Path,
    rebuild: Callable[[], None],
    interval: float = 0.8,
) -> None:
    """Poll *docs_dir* for ``.md`` file changes and rebuild on any change.

    Calls *rebuild()* then :func:`bump_version` whenever files are added,
    removed, or modified.  Blocks indefinitely — run after starting the server
    and opening the browser, as the main-thread event loop.
    """

    def _mtimes() -> dict[Path, float]:
        return {p: p.stat().st_mtime for p in docs_dir.rglob("*.md")}

    prev = _mtimes()
    while True:
        time.sleep(interval)
        curr = _mtimes()
        if curr != prev:
            prev = curr
            try:
                rebuild()
            except Exception as exc:
                print(f"\n  rebuild error: {exc}", file=sys.stderr)
            bump_version()
