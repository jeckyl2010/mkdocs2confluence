"""PlantUML diagram rendering transform.

Walks the IR tree, finds :class:`PlantUMLDiagram` nodes, renders each to SVG
via the Kroki rendering service, caches results locally, and returns updated
nodes with ``attachment_name`` set plus a list of SVG paths to upload.

SVG (vector) output is used rather than PNG because PlantUML caps raster output
at ``PLANTUML_LIMIT_SIZE`` pixels (default 4096) per dimension, which causes
large diagrams to fail rendering.  SVG is not subject to that limit, scales
crisply, and is supported by Confluence attachments.

The cache lives at ``~/.cache/mk2conf/plantuml/`` and is keyed by the SHA-256
of the PlantUML source so unchanged diagrams are never re-fetched.

When Kroki is unavailable (network error, HTTP error, timeout, or bad response)
each affected diagram is left unchanged so the emitter falls back to a fenced
code block.  The rest of the pipeline continues unaffected.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
from pathlib import Path

from mkdocs_to_confluence.ir.nodes import IRNode, PlantUMLDiagram
from mkdocs_to_confluence.transforms._kroki import (
    _CACHE_LOCK,
    _RETRY_ATTEMPTS,
    _RETRY_BACKOFF,
    _RETRYABLE_HTTP,
    DEFAULT_KROKI_URL,
    kroki_post,
    render_diagrams,
)
from mkdocs_to_confluence.transforms._kroki import (
    warn as _warn,
)

_CACHE_DIR = Path.home() / ".cache" / "mk2conf" / "plantuml"


def _looks_like_svg(data: bytes) -> bool:
    """Heuristic: does *data* look like a valid SVG document?"""
    head = data[:512].lstrip()
    return head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in head


def _cache_path(source: str) -> Path:
    digest = hashlib.sha256(source.encode()).hexdigest()
    return _CACHE_DIR / f"plantuml_{digest}.svg"


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
            svg = kroki_post(source, "plantuml", kroki_url, fmt="svg")
            if not _looks_like_svg(svg):
                raise ValueError(f"Kroki returned {len(svg)} bytes (expected a valid SVG)")
            with _CACHE_LOCK:
                path.write_bytes(svg)
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
    """Render all :class:`PlantUMLDiagram` nodes to SVG via Kroki.

    Diagrams are rendered concurrently (up to ``_MAX_WORKERS`` threads).
    Returns the updated IR node tuple (with ``attachment_name`` set on each
    successfully rendered diagram) and a list of SVG :class:`Path` objects to
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
