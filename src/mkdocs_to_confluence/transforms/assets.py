"""Asset resolution transform.

Walks the IR tree and resolves relative ``ImageNode.src`` and local-file
``LinkNode.href`` paths to absolute paths.  A collision-safe
``attachment_name`` is derived for each local asset so the publisher can
upload them to Confluence without name collisions.

URLs (``http://``, ``https://``, ``//``, ``data:``) are left unchanged.
Links to other ``.md`` pages are skipped (handled by the link-resolution
transform).
"""

from __future__ import annotations

import dataclasses
import warnings
from pathlib import Path

from mkdocs_to_confluence.ir.nodes import (
    IRNode,
    ImageNode,
    LinkNode,
    walk,
)


def is_url(value: str) -> bool:
    """Return True if *value* is an external URL or data URI."""
    return value.startswith(("http://", "https://", "//", "data:"))


def _make_attachment_name(abs_path: Path, docs_dir: Path) -> str:
    """Compute a collision-safe attachment filename from an absolute path.

    Joins the path parts relative to ``docs_dir`` with underscores so that
    ``assets/images/logo.png`` becomes ``assets_images_logo.png``.
    Falls back to the bare filename when the path is outside ``docs_dir``.
    """
    try:
        rel = abs_path.relative_to(docs_dir)
        parts = rel.parts
        return "_".join(parts)
    except ValueError:
        return abs_path.name


def resolve_local_assets(
    nodes: tuple[IRNode, ...],
    *,
    page_path: Path,
    docs_dir: Path,
) -> tuple[tuple[IRNode, ...], list[Path]]:
    """Resolve local image and file-link paths; collect attachment paths.

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
        Updated IR nodes with resolved paths and ``attachment_name`` set.
    list[Path]
        Absolute paths to all local asset files found.
    """
    attachments: list[Path] = []
    replacements: dict[int, IRNode] = {}
    page_dir = page_path.parent

    for top_node in nodes:
        for node in walk(top_node):
            if isinstance(node, ImageNode):
                if is_url(node.src):
                    continue
                candidate = _resolve_path(node.src, page_dir, docs_dir)
                if candidate is None:
                    continue
                attachment_name = _make_attachment_name(candidate, docs_dir)
                attachments.append(candidate)
                replacements[id(node)] = dataclasses.replace(
                    node,
                    src=str(candidate),
                    attachment_name=attachment_name,
                )

            elif isinstance(node, LinkNode):
                href = node.href
                # Skip URLs and internal .md links
                if is_url(href) or href.endswith(".md") or href.endswith(".md#"):
                    continue
                # Skip fragment-only links and anchors into .md files
                if href.startswith("#"):
                    continue
                if ".md#" in href:
                    continue
                # Only handle links that look like local file paths
                if "/" not in href and "." not in href:
                    # Bare word with no extension/slash — skip
                    continue
                candidate = _resolve_path(href.split("#")[0], page_dir, docs_dir)
                if candidate is None:
                    warnings.warn(
                        f"Local file link not found and will render as plain text: {href!r}",
                        stacklevel=2,
                    )
                    continue
                attachment_name = _make_attachment_name(candidate, docs_dir)
                attachments.append(candidate)
                replacements[id(node)] = dataclasses.replace(
                    node,
                    attachment_name=attachment_name,
                )

    if not replacements:
        return nodes, attachments

    updated = _replace_nodes(nodes, replacements)
    return updated, attachments


def _resolve_path(src: str, page_dir: Path, docs_dir: Path) -> Path | None:
    """Try to find *src* relative to *page_dir* then *docs_dir*.

    Returns the resolved absolute path, or ``None`` when the file cannot be
    found in either location.
    """
    candidate = (page_dir / src).resolve()
    if candidate.exists():
        return candidate
    candidate = (docs_dir / src).resolve()
    if candidate.exists():
        return candidate
    return None


def _replace_nodes(
    nodes: tuple[IRNode, ...],
    replacements: dict[int, IRNode],
) -> tuple[IRNode, ...]:
    result: list[IRNode] = []
    for node in nodes:
        if id(node) in replacements:
            result.append(replacements[id(node)])
            continue
        updated = _rebuild(node, replacements)
        result.append(updated)
    return tuple(result)


def _rebuild(node: IRNode, replacements: dict[int, IRNode]) -> IRNode:
    changes: dict[str, object] = {}
    for field in dataclasses.fields(node):
        value = getattr(node, field.name)
        if isinstance(value, IRNode):
            replaced = replacements.get(id(value), _rebuild(value, replacements))
            if replaced is not value:
                changes[field.name] = replaced
        elif isinstance(value, tuple) and value and isinstance(value[0], IRNode):
            rebuilt = _replace_nodes(value, replacements)
            if rebuilt is not value:
                changes[field.name] = rebuilt
    if changes:
        return dataclasses.replace(node, **changes)
    return node
