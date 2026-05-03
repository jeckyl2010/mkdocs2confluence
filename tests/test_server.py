"""Tests for the livereload HTTP server (preview/server.py)."""

from __future__ import annotations

import http.client
import threading
import time
from pathlib import Path

import mkdocs_to_confluence.preview.server as _srv_module
from mkdocs_to_confluence.preview.server import (
    HTTPServer,
    _Handler,
    bump_version,
    start_server,
    watch_and_rebuild,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _start(serve_dir: Path) -> tuple[HTTPServer, int]:
    """Start a server on an OS-assigned port; return (server, port)."""
    _Handler.serve_dir = serve_dir.resolve()
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _get(port: int, path: str) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    conn.request("GET", path)
    return conn.getresponse()


# ── bump_version ──────────────────────────────────────────────────────────────


class TestBumpVersion:
    def test_increments_counter(self) -> None:
        before = _srv_module._reload_version
        bump_version()
        assert _srv_module._reload_version == before + 1

    def test_thread_safe(self) -> None:
        """Concurrent bumps must not lose counts."""
        start = _srv_module._reload_version
        threads = [threading.Thread(target=bump_version) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert _srv_module._reload_version == start + 20


# ── HTTP handler ──────────────────────────────────────────────────────────────


class TestLivereloadEndpoint:
    def test_returns_numeric_body(self, tmp_path: Path) -> None:
        server, port = _start(tmp_path)
        try:
            resp = _get(port, "/__livereload")
            assert resp.status == 200
            body = resp.read().decode()
            assert body.isdigit()
        finally:
            server.shutdown()

    def test_returns_current_version(self, tmp_path: Path) -> None:
        server, port = _start(tmp_path)
        try:
            before = int(_get(port, "/__livereload").read())
            bump_version()
            after = int(_get(port, "/__livereload").read())
            assert after == before + 1
        finally:
            server.shutdown()

    def test_cache_control_no_store(self, tmp_path: Path) -> None:
        server, port = _start(tmp_path)
        try:
            resp = _get(port, "/__livereload")
            resp.read()
            assert resp.getheader("Cache-Control") == "no-store"
        finally:
            server.shutdown()


class TestFileServing:
    def test_serves_html_file(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
        server, port = _start(tmp_path)
        try:
            resp = _get(port, "/index.html")
            assert resp.status == 200
            assert "<h1>Hello</h1>" in resp.read().decode()
            assert "text/html" in resp.getheader("Content-Type", "")
        finally:
            server.shutdown()

    def test_root_serves_index_html(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<p>root</p>", encoding="utf-8")
        server, port = _start(tmp_path)
        try:
            resp = _get(port, "/")
            assert resp.status == 200
            assert "<p>root</p>" in resp.read().decode()
        finally:
            server.shutdown()

    def test_missing_file_returns_404(self, tmp_path: Path) -> None:
        server, port = _start(tmp_path)
        try:
            resp = _get(port, "/nonexistent.html")
            resp.read()
            assert resp.status == 404
        finally:
            server.shutdown()

    def test_path_traversal_returns_403(self, tmp_path: Path) -> None:
        """Requests that escape serve_dir must be rejected with 403."""
        server, port = _start(tmp_path)
        try:
            resp = _get(port, "/../etc/passwd")
            resp.read()
            assert resp.status == 403
        finally:
            server.shutdown()


# ── watch_and_rebuild ─────────────────────────────────────────────────────────


class TestWatchAndRebuild:
    _INTERVAL = 0.05  # short polling interval for tests

    def test_rebuild_called_on_mtime_change(self, tmp_path: Path) -> None:
        md = tmp_path / "page.md"
        md.write_text("# Before", encoding="utf-8")

        calls: list[bool] = []

        def rebuild() -> None:
            calls.append(True)

        t = threading.Thread(
            target=watch_and_rebuild,
            args=(tmp_path, rebuild, self._INTERVAL),
            daemon=True,
        )
        t.start()
        time.sleep(self._INTERVAL * 2)  # let watcher take initial snapshot

        md.write_text("# After", encoding="utf-8")
        time.sleep(self._INTERVAL * 6)  # wait for detection + bump

        assert len(calls) >= 1

    def test_no_rebuild_when_files_unchanged(self, tmp_path: Path) -> None:
        (tmp_path / "page.md").write_text("# Hello", encoding="utf-8")

        calls: list[bool] = []

        def rebuild() -> None:
            calls.append(True)

        t = threading.Thread(
            target=watch_and_rebuild,
            args=(tmp_path, rebuild, self._INTERVAL),
            daemon=True,
        )
        t.start()
        time.sleep(self._INTERVAL * 6)  # watch but never change anything

        assert calls == []

    def test_rebuild_error_does_not_crash_loop(self, tmp_path: Path) -> None:
        """An exception in rebuild() must be caught; the loop must continue."""
        md = tmp_path / "page.md"
        md.write_text("# Before", encoding="utf-8")

        attempt = [0]

        def flaky_rebuild() -> None:
            attempt[0] += 1
            raise RuntimeError("boom")

        t = threading.Thread(
            target=watch_and_rebuild,
            args=(tmp_path, flaky_rebuild, self._INTERVAL),
            daemon=True,
        )
        t.start()
        time.sleep(self._INTERVAL * 2)

        md.write_text("# Changed", encoding="utf-8")
        time.sleep(self._INTERVAL * 6)

        assert t.is_alive(), "watch_and_rebuild thread must survive a rebuild exception"
        assert attempt[0] >= 1

    def test_bump_version_called_after_rebuild(self, tmp_path: Path) -> None:
        """bump_version() must be called even when rebuild() raises."""
        md = tmp_path / "page.md"
        md.write_text("# Before", encoding="utf-8")

        before = _srv_module._reload_version

        def rebuild() -> None:
            pass

        t = threading.Thread(
            target=watch_and_rebuild,
            args=(tmp_path, rebuild, self._INTERVAL),
            daemon=True,
        )
        t.start()
        time.sleep(self._INTERVAL * 2)

        md.write_text("# After", encoding="utf-8")
        time.sleep(self._INTERVAL * 6)

        assert _srv_module._reload_version > before


# ── start_server ──────────────────────────────────────────────────────────────


class TestStartServer:
    def test_returns_server_object(self, tmp_path: Path) -> None:
        server = start_server(tmp_path, port=0)
        try:
            assert isinstance(server, HTTPServer)
        finally:
            server.shutdown()

    def test_server_responds_on_assigned_port(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<p>ok</p>", encoding="utf-8")
        server = start_server(tmp_path, port=0)
        port = server.server_address[1]
        try:
            resp = _get(port, "/index.html")
            assert resp.status == 200
            resp.read()
        finally:
            server.shutdown()
