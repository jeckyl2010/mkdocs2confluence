"""PlantUML diagram rendering transform.

Walks the IR tree, finds :class:`PlantUMLDiagram` nodes, renders each to PNG
via the Kroki rendering service, caches results locally, and returns updated
nodes with ``attachment_name`` set plus a list of PNG paths to upload.

The cache lives at ``~/.cache/mk2conf/plantuml/`` and is keyed by the SHA-256
of the PlantUML source so unchanged diagrams are never re-fetched.

When Kroki is unavailable (network error, HTTP error, timeout, or bad response)
each affected diagram is left unchanged so the emitter falls back to a fenced
code block.  The rest of the pipeline continues unaffected.
"""

from __future__ import annotations

import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

from mkdocs_to_confluence.ir.nodes import IRNode, PlantUMLDiagram
from mkdocs_to_confluence.transforms._kroki import (
    _CACHE_LOCK,
    _MIN_PNG_BYTES,
    _RETRY_ATTEMPTS,
    _RETRY_BACKOFF,
    _RETRYABLE_HTTP,
    _TIMEOUT,
    DEFAULT_KROKI_URL,
    render_diagrams,
)

_CACHE_DIR = Path.home() / ".cache" / "mk2conf" / "plantuml"


def _kroki_png(source: str, kroki_url: str) -> bytes:
    """Fetch a PNG rendering of *source* from the Kroki service (POST)."""
    url = f"{kroki_url.rstrip('/')}/plantuml/png"
    body = source.encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "text/plain",
            "Accept": "image/png",
            "User-Agent": "mk2conf/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310  # nosec B310
        return cast(bytes, resp.read())


def _cache_path(source: str) -> Path:
    digest = hashlib.sha256(source.encode()).hexdigest()
    return _CACHE_DIR / f"plantuml_{digest}.png"


def _warn(msg: str) -> None:
    print(f"  warning    {msg}", file=sys.stderr)


def _render_one(source: str, kroki_url: str, *, quiet: bool = False) -> Path | None:
    """Render a single PlantUML diagram to cache.

    Returns the cache :class:`Path` on success, ``None`` on failure.
    Transient HTTP errors (429, 5xx) and network blips are retried up to
    ``_RETRY_ATTEMPTS`` times with exponential backoff.
    """
    path = _cache_path(source)
    if path.exists():
        if not quiet:
            print("        rendering  plantuml diagram (cached)")
        return path

    last_exc: Exception | None = None

    for attempt in range(_RETRY_ATTEMPTS):
        if attempt > 0:
            delay = _RETRY_BACKOFF * (2 ** (attempt - 1))
            _warn(f"plantuml diagram: retrying in {delay:.0f}s (attempt {attempt + 1}/{_RETRY_ATTEMPTS})")
            time.sleep(delay)
        try:
            if not quiet:
                print(f"        rendering  plantuml diagram via Kroki ({kroki_url})")
            png = _kroki_png(source, kroki_url)
            if len(png) < _MIN_PNG_BYTES:
                raise ValueError(f"Kroki returned {len(png)} bytes (expected a valid PNG)")
            with _CACHE_LOCK:
                path.write_bytes(png)
            return path
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRYABLE_HTTP:
                last_exc = exc
                continue  # retry
            _warn(f"plantuml diagram: Kroki returned HTTP {exc.code} {exc.reason} — falling back to code block")
            return None
        except (urllib.error.URLError, OSError) as exc:
            last_exc = exc
            continue  # retry — network blip
        except ValueError as exc:
            _warn(f"plantuml diagram: {exc} — falling back to code block")
            return None

    _warn(f"plantuml diagram: failed after {_RETRY_ATTEMPTS} attempts ({last_exc}) — falling back to code block")
    return None


def render_plantuml_diagrams(
    nodes: tuple[IRNode, ...],
    kroki_url: str = DEFAULT_KROKI_URL,
    *,
    quiet: bool = False,
) -> tuple[tuple[IRNode, ...], list[Path]]:
    """Render all :class:`PlantUMLDiagram` nodes to PNG via Kroki.

    Diagrams are rendered concurrently (up to ``_MAX_WORKERS`` threads).
    Returns the updated IR node tuple (with ``attachment_name`` set on each
    successfully rendered diagram) and a list of PNG :class:`Path` objects to
    upload as page attachments.

    Diagrams that fail to render are left unchanged (code-block fallback).
    The pipeline always produces valid output regardless of service availability.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _warn(f"cannot create plantuml cache dir {_CACHE_DIR}: {exc} — all diagrams will fall back to code blocks")

    def render_fn(source: str, q: bool) -> Path | None:
        return _render_one(source, kroki_url, quiet=q)

    return render_diagrams(nodes, PlantUMLDiagram, render_fn, quiet=quiet)
