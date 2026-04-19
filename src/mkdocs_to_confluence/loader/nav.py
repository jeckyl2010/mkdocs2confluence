"""Resolve the MkDocs nav structure into a typed tree of NavNode objects."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mkdocs_to_confluence.loader.config import MkDocsConfig


@dataclass(frozen=True)
class NavNode:
    """A single node in the resolved navigation tree.

    Leaf nodes (pages) have ``source_path`` set and ``children`` empty.
    Section nodes have ``source_path = None`` and a non-empty ``children`` list.
    """

    title: str
    # Relative to docs_dir, e.g. "guide/getting-started.md".  None for sections.
    docs_path: str | None
    # Absolute path on disk.  None for sections or when the file is missing.
    source_path: Path | None
    level: int
    children: tuple[NavNode, ...] = field(default_factory=tuple)

    @property
    def is_section(self) -> bool:
        """True if this node is a section header, not a concrete page."""
        return self.docs_path is None

    @property
    def is_page(self) -> bool:
        """True if this node refers to a concrete markdown file."""
        return self.docs_path is not None


def resolve_nav(config: MkDocsConfig, mkdocs_root: Path | None = None) -> list[NavNode]:
    """Resolve *config.nav* into a list of top-level :class:`NavNode` objects.

    When ``config.nav`` is ``None`` (e.g. projects using ``awesome-pages`` or
    ``literate-nav`` plugins), all ``.md`` files under ``docs_dir`` are
    discovered recursively and returned as a flat nav in sorted order.

    Args:
        config: Parsed :class:`~mkdocs_to_confluence.loader.config.MkDocsConfig`.
        mkdocs_root: Directory containing ``mkdocs.yml``.  Used only to compute
            ``docs_dir`` when it is not already absolute; defaults to CWD.

    Returns:
        List of top-level :class:`NavNode` instances.
    """
    docs_dir = config.docs_dir

    if config.nav is None:
        return _discover(docs_dir)

    return _traverse(config.nav, docs_dir, level=0)


def _discover(docs_dir: Path) -> list[NavNode]:
    """Auto-discover all .md files under *docs_dir* as a flat nav."""
    nodes: list[NavNode] = []
    for md_file in sorted(docs_dir.rglob("*.md")):
        docs_path = md_file.relative_to(docs_dir).as_posix()
        nodes.append(
            NavNode(
                title=md_file.stem.replace("-", " ").replace("_", " ").title(),
                docs_path=docs_path,
                source_path=md_file,
                level=0,
            )
        )
    return nodes


def _traverse(nav: list[Any], docs_dir: Path, level: int) -> list[NavNode]:
    nodes: list[NavNode] = []
    for item in nav:
        if not isinstance(item, dict):
            warnings.warn(
                f"Unexpected nav item (expected a mapping, got {type(item).__name__!r}): "
                f"{item!r} — skipping.",
                stacklevel=4,
            )
            continue

        if len(item) != 1:
            warnings.warn(
                f"Nav item has {len(item)} keys; expected exactly 1 — skipping: {item!r}",
                stacklevel=4,
            )
            continue

        title, value = next(iter(item.items()))

        if isinstance(value, list):
            # Section node — recurse
            children = _traverse(value, docs_dir, level=level + 1)
            nodes.append(
                NavNode(
                    title=title,
                    docs_path=None,
                    source_path=None,
                    level=level,
                    children=tuple(children),
                )
            )
        elif isinstance(value, str):
            # Leaf page node
            source_path = (docs_dir / value).resolve()
            if not source_path.exists():
                warnings.warn(
                    f"Nav page '{title}' not found at '{source_path}' — "
                    "it will be omitted from the resolved nav.",
                    stacklevel=4,
                )
                source_path_or_none: Path | None = None
            else:
                source_path_or_none = source_path

            nodes.append(
                NavNode(
                    title=title,
                    docs_path=value,
                    source_path=source_path_or_none,
                    level=level,
                )
            )
        else:
            warnings.warn(
                f"Nav item '{title}' has an unexpected value type "
                f"({type(value).__name__!r}) — skipping.",
                stacklevel=4,
            )

    return nodes


def flat_pages(nodes: list[NavNode]) -> list[NavNode]:
    """Return a depth-first flat list of all *page* nodes (no sections).

    Useful for iterating over every page in document order.
    """
    result: list[NavNode] = []
    for node in nodes:
        if node.is_page:
            result.append(node)
        result.extend(flat_pages(list(node.children)))
    return result
