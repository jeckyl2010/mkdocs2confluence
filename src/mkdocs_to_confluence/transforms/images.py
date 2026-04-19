"""Image resolution transform.

Walks the IR tree and resolves relative ``ImageNode.src`` paths to absolute
file paths.  Nodes that reference local files are updated in-place; HTTP(S)
URLs are left unchanged.

The resolved absolute paths are also returned as a set so the caller can
register them on ``Document.attachments`` for the publisher.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from mkdocs_to_confluence.ir.nodes import (
    IRNode,
    ImageNode,
    walk,
)


def is_local(src: str) -> bool:
    """Return True if *src* is a local file reference (not a URL)."""
    return not src.startswith(("http://", "https://", "//", "data:"))


def resolve_images(
    nodes: tuple[IRNode, ...],
    *,
    page_path: Path,
    docs_dir: Path,
) -> tuple[tuple[IRNode, ...], list[Path]]:
    """Resolve relative image paths and collect local attachments.

    Parameters
    ----------
    nodes:
        Top-level IR nodes for the page.
    page_path:
        Absolute path to the source Markdown file.
    docs_dir:
        Absolute path to the MkDocs ``docs/`` directory.

    Returns
    -------
    tuple[IRNode, ...]
        Updated IR nodes with resolved ``ImageNode.src`` paths.
    list[Path]
        Absolute paths to all local image files found.
    """
    attachments: list[Path] = []

    # Build a mapping of old ImageNode id → replacement for the tree rebuild.
    replacements: dict[int, ImageNode] = {}

    for top_node in nodes:
        for node in walk(top_node):
            if not isinstance(node, ImageNode):
                continue
            src = node.src
            if not is_local(src):
                continue

            # Resolve relative to the page's directory first; fall back to docs_dir.
            page_dir = page_path.parent
            candidate = (page_dir / src).resolve()
            if not candidate.exists():
                candidate = (docs_dir / src).resolve()
            if not candidate.exists():
                # Can't find the file — leave src as-is, don't register.
                continue

            attachments.append(candidate)
            replacements[id(node)] = dataclasses.replace(node, src=str(candidate))

    if not replacements:
        return nodes, attachments

    updated = _replace_nodes(nodes, replacements)
    return updated, attachments


def _replace_nodes(
    nodes: tuple[IRNode, ...],
    replacements: dict[int, IRNode],
) -> tuple[IRNode, ...]:
    """Recursively rebuild *nodes*, substituting entries from *replacements*."""
    result: list[IRNode] = []
    for node in nodes:
        if id(node) in replacements:
            result.append(replacements[id(node)])
            continue
        # Rebuild children if the node has them.
        updated = _rebuild(node, replacements)
        result.append(updated)
    return tuple(result)


def _rebuild(node: IRNode, replacements: dict[int, IRNode]) -> IRNode:
    """Return *node* with any matching descendants replaced."""
    changes: dict[str, object] = {}
    for field in dataclasses.fields(node):  # type: ignore[arg-type]
        value = getattr(node, field.name)
        if isinstance(value, tuple) and value and isinstance(value[0], IRNode):
            new_value = _replace_nodes(value, replacements)
            if new_value is not value:
                changes[field.name] = new_value
    if changes:
        return dataclasses.replace(node, **changes)
    return node
