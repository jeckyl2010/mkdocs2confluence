"""Generic Kroki diagram rendering utilities shared by all diagram transforms.

Provides:
- :func:`kroki_post` — low-level HTTP POST to Kroki for any diagram type and format.
- :func:`render_diagrams` — concurrent deduplication/replacement loop used by
  every diagram-type transform.  Each transform supplies its own ``render_fn``
  that handles type-specific caching and retry behaviour.

Shared constants (timeouts, retry counts, etc.) are defined here so diagram
transforms stay in sync without duplication.
"""

from __future__ import annotations

import dataclasses
import sys
import threading
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

from mkdocs_to_confluence.ir.nodes import IRNode, walk
from mkdocs_to_confluence.ir.treeutil import replace_nodes

DEFAULT_KROKI_URL = "https://kroki.io"

_TIMEOUT = 30  # seconds
_MIN_PNG_BYTES = 67  # smallest valid PNG (1×1 px) is 67 bytes
_CACHE_LOCK = threading.Lock()
_MAX_WORKERS = 8
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 1.0  # seconds; doubles each attempt
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


class _DiagramNode(Protocol):
    """Structural protocol for diagram IR nodes (Mermaid, PlantUML, …)."""

    source: str
    attachment_name: str | None
    local_path: Path | None


_D = TypeVar("_D", bound="_DiagramNode")


_ACCEPT: dict[str, str] = {"png": "image/png", "svg": "image/svg+xml"}


def kroki_post(source: str, diagram_type: str, kroki_url: str, fmt: str = "png") -> bytes:
    """POST *source* to Kroki for *diagram_type* and return rendered bytes."""
    url = f"{kroki_url.rstrip('/')}/{diagram_type}/{fmt}"
    body = source.encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "text/plain",
            "Accept": _ACCEPT.get(fmt, f"image/{fmt}"),
            "User-Agent": "mk2conf/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310  # nosec B310
        return cast(bytes, resp.read())


def warn(msg: str) -> None:
    print(f"  warning    {msg}", file=sys.stderr)


def render_diagrams(
    nodes: tuple[IRNode, ...],
    node_class: type[Any],
    render_fn: Callable[[str, bool], Path | None],
    *,
    quiet: bool = False,
) -> tuple[tuple[IRNode, ...], list[Path]]:
    """Render all *node_class* nodes to PNG concurrently.

    *render_fn* is called as ``render_fn(source, quiet)`` for each unique
    diagram source; it must return a :class:`Path` on success or ``None`` on
    failure.  Each diagram type supplies its own ``render_fn`` that handles
    caching, retries, and any type-specific fallback.

    Returns the updated IR node tuple (``attachment_name`` set on successful
    renders) and a list of PNG paths to upload as page attachments.  Failed
    nodes are left unchanged so the emitter can fall back to a code block.
    """
    diagrams: list[Any] = []
    seen_sources: set[str] = set()
    for top_node in nodes:
        for node in walk(top_node):
            if isinstance(node, node_class) and node.attachment_name is None:
                if node.source not in seen_sources:
                    diagrams.append(node)
                    seen_sources.add(node.source)

    if not diagrams:
        return nodes, []

    source_to_path: dict[str, Path | None] = {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(diagrams))) as pool:
        future_to_source = {
            pool.submit(render_fn, d.source, quiet): d.source
            for d in diagrams
        }
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            source_to_path[source] = future.result()

    attachments: list[Path] = []
    replacements: dict[int, IRNode] = {}
    seen_paths: set[Path] = set()

    for top_node in nodes:
        for node in walk(top_node):
            if not isinstance(node, node_class) or node.attachment_name is not None:
                continue
            path = source_to_path.get(node.source)
            if path is None:
                continue
            if path not in seen_paths:
                attachments.append(path)
                seen_paths.add(path)
            replacements[id(node)] = dataclasses.replace(node, attachment_name=path.name, local_path=path)

    if not replacements:
        return nodes, attachments

    return replace_nodes(nodes, replacements), attachments


