"""Internal link resolution transform.

Rewrites ``LinkNode`` instances whose ``href`` points to another ``.md`` page
in the same MkDocs site to native Confluence page links.

After this transform:
* ``node.is_internal`` is ``True``
* ``node.href`` holds the **Confluence page title** (used as ``<ri:page ac:title="..."/>``
* ``node.anchor`` holds the URL fragment (``#section``) if present, or ``None``

Links to pages not found in the nav map are left unchanged so that authors
can notice them (they will render as raw ``.md`` hrefs — clearly wrong but not
silently lost).
"""

from __future__ import annotations

import dataclasses
import posixpath

from mkdocs_to_confluence.ir.nodes import IRNode, LinkNode, walk
from mkdocs_to_confluence.loader.nav import NavNode, flat_pages


def build_link_map(nav_nodes: list[NavNode]) -> dict[str, str]:
    """Return a ``{docs_path: title}`` mapping for every page in the nav.

    Parameters
    ----------
    nav_nodes:
        Top-level nav nodes as returned by :func:`~loader.nav.resolve_nav`.

    Returns
    -------
    dict[str, str]
        Maps e.g. ``"guide/installation.md"`` → ``"Installation Guide"``.
    """
    return {
        node.docs_path: node.title
        for node in flat_pages(nav_nodes)
        if node.docs_path is not None
    }


def resolve_internal_links(
    nodes: tuple[IRNode, ...],
    link_map: dict[str, str],
    current_docs_path: str,
) -> tuple[IRNode, ...]:
    """Replace ``.md`` ``LinkNode`` hrefs with Confluence page titles.

    Parameters
    ----------
    nodes:
        Top-level IR nodes for the page being processed.
    link_map:
        Mapping from ``docs_path`` to page title, built by :func:`build_link_map`.
    current_docs_path:
        The ``docs_path`` of the page being processed (e.g. ``"guide/setup.md"``).
        Used to resolve relative hrefs.

    Returns
    -------
    tuple[IRNode, ...]
        Updated IR nodes with internal links rewritten.
    """
    replacements: dict[int, IRNode] = {}

    for top_node in nodes:
        for node in walk(top_node):
            if not isinstance(node, LinkNode):
                continue
            href = node.href
            # Skip external URLs and fragment-only links
            if href.startswith(("http://", "https://", "//", "data:", "#")):
                continue
            # Skip already-resolved attachment links
            if node.attachment_name is not None:
                continue

            result = _resolve_md_href(href, current_docs_path)
            if result is None:
                continue
            resolved_path, anchor = result

            title = link_map.get(resolved_path)
            if title is None:
                # Page not in nav — leave link as-is so the author notices
                continue

            replacements[id(node)] = dataclasses.replace(
                node,
                href=title,
                is_internal=True,
                anchor=anchor or None,
            )

    if not replacements:
        return nodes

    return _replace_nodes(nodes, replacements)


def _resolve_md_href(href: str, current_docs_path: str) -> tuple[str, str] | None:
    """Resolve a relative ``.md`` href to ``(docs_root_relative_path, anchor)``.

    Returns ``None`` when *href* does not reference a ``.md`` file.
    """
    # Split off fragment
    if "#" in href:
        path_part, anchor = href.split("#", 1)
    else:
        path_part, anchor = href, ""

    if not path_part.endswith(".md"):
        return None

    # Absolute from docs root (e.g. /guide/index.md)
    if path_part.startswith("/"):
        return path_part.lstrip("/"), anchor

    # Relative: resolve against the directory of the current page
    current_dir = posixpath.dirname(current_docs_path)
    joined = posixpath.join(current_dir, path_part) if current_dir else path_part
    normalized = posixpath.normpath(joined)
    return normalized, anchor


# ── Tree rewriting (same pattern as transforms/assets.py) ────────────────────


def _replace_nodes(
    nodes: tuple[IRNode, ...],
    replacements: dict[int, IRNode],
) -> tuple[IRNode, ...]:
    result: list[IRNode] = []
    for node in nodes:
        if id(node) in replacements:
            result.append(replacements[id(node)])
            continue
        result.append(_rebuild(node, replacements))
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
