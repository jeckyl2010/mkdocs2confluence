"""Mermaid diagram rendering transform.

Walks the IR tree, finds :class:`MermaidDiagram` nodes, renders each to PNG
via the Kroki rendering service, caches results locally, and returns updated
nodes with ``attachment_name`` set plus a list of PNG paths to upload.

The cache lives at ``~/.cache/mk2conf/mermaid/`` and is keyed by the SHA-256
of the Mermaid source so unchanged diagrams are never re-fetched.
"""

from __future__ import annotations

import dataclasses
import hashlib
import urllib.error
import urllib.request
import warnings
from pathlib import Path

from mkdocs_to_confluence.ir.nodes import IRNode, MermaidDiagram, walk
from mkdocs_to_confluence.ir.treeutil import replace_nodes

_CACHE_DIR = Path.home() / ".cache" / "mk2conf" / "mermaid"
DEFAULT_KROKI_URL = "https://kroki.io"


def _kroki_png(source: str, kroki_url: str) -> bytes:
    """Fetch a PNG rendering of *source* from the Kroki service (POST)."""
    url = f"{kroki_url.rstrip('/')}/mermaid/png"
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
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return resp.read()


def _cache_path(source: str) -> Path:
    digest = hashlib.sha256(source.encode()).hexdigest()
    return _CACHE_DIR / f"mermaid_{digest}.png"


def render_mermaid_diagrams(
    nodes: tuple[IRNode, ...],
    kroki_url: str = DEFAULT_KROKI_URL,
) -> tuple[tuple[IRNode, ...], list[Path]]:
    """Render all :class:`MermaidDiagram` nodes to PNG via Kroki.

    Returns the updated IR node tuple (with ``attachment_name`` set on each
    successfully rendered diagram) and a list of PNG :class:`Path` objects to
    upload as page attachments.

    Diagrams that fail to render are left unchanged (code-block fallback).
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    attachments: list[Path] = []
    replacements: dict[int, IRNode] = {}
    seen_paths: set[Path] = set()

    for top_node in nodes:
        for node in walk(top_node):
            if not isinstance(node, MermaidDiagram):
                continue
            if node.attachment_name is not None:
                continue  # already resolved

            path = _cache_path(node.source)
            if not path.exists():
                try:
                    print(f"        rendering  mermaid diagram via Kroki ({kroki_url})")
                    png = _kroki_png(node.source, kroki_url)
                    path.write_bytes(png)
                except (urllib.error.URLError, OSError) as exc:
                    warnings.warn(
                        f"Mermaid rendering failed (falling back to code block): {exc}",
                        stacklevel=2,
                    )
                    continue
            else:
                print("        rendering  mermaid diagram (cached)")

            if path not in seen_paths:
                attachments.append(path)
                seen_paths.add(path)

            replacements[id(node)] = dataclasses.replace(
                node, attachment_name=path.name, local_path=path
            )

    if not replacements:
        return nodes, attachments

    return replace_nodes(nodes, replacements), attachments
