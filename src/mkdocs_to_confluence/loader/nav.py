"""Resolve the MkDocs nav structure into a typed tree of NavNode objects."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

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


def resolve_nav(config: MkDocsConfig) -> list[NavNode]:
    """Resolve *config.nav* into a list of top-level :class:`NavNode` objects.

    When ``config.nav`` is ``None`` (e.g. projects using ``awesome-pages`` or
    ``literate-nav`` plugins), all ``.md`` files under ``docs_dir`` are
    discovered using ``nav_file`` (default: ``.pages``) if present.

    Args:
        config: Parsed :class:`~mkdocs_to_confluence.loader.config.MkDocsConfig`.

    Returns:
        List of top-level :class:`NavNode` instances.
    """
    docs_dir = config.docs_dir
    nav_file = config.confluence.nav_file if config.confluence else ".pages"

    if config.nav is None:
        return _discover(docs_dir, nav_file)

    return _traverse(config.nav, docs_dir, level=0, nav_file=nav_file)


def _discover(docs_dir: Path, nav_file: str) -> list[NavNode]:
    """Auto-discover pages, respecting nav_file files (e.g. .pages) when present."""
    nav_entries = _read_nav_file(docs_dir, nav_file)
    if nav_entries is not None:
        return _traverse_nav_dir(nav_entries, docs_dir, docs_dir, level=0, nav_file=nav_file)
    # No nav_file at root — fall back to flat rglob
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


def _read_nav_file(directory: Path, nav_file: str) -> list[Any] | None:
    """Return the nav list from *directory*/<nav_file>, or None if absent.

    Raises ValueError if the file exists but cannot be parsed or has an
    unexpected format — a present-but-broken nav file is a configuration
    error, not a reason to silently fall back to full discovery.
    """
    path = directory / nav_file
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Could not parse nav file {path}: {exc}") from exc
    if isinstance(data, dict) and isinstance(data.get("nav"), list):
        return cast(list[Any], data["nav"])
    if isinstance(data, list):
        return data
    raise ValueError(
        f"Nav file {path} has unexpected format (expected a list or a dict with a 'nav' key, got {type(data).__name__})"
    )


def _traverse_nav_dir(
    nav: list[Any], base_dir: Path, docs_dir: Path, level: int, nav_file: str
) -> list[NavNode]:
    """Traverse a nav_file entry list where paths are relative to *base_dir*."""
    nodes: list[NavNode] = []
    for item in nav:
        if isinstance(item, str):
            # Bare string — could be a .md file or a bare directory reference
            target = (base_dir / item).resolve()
            if target.is_dir():
                # Bare directory: expand using its nav_file, title from dirname
                children = _resolve_nav_dir(target, docs_dir, level + 1, nav_file)
                title = target.name.replace("-", " ").replace("_", " ").title()
                nodes.append(
                    NavNode(
                        title=title,
                        docs_path=None,
                        source_path=None,
                        level=level,
                        children=tuple(children),
                    )
                )
            elif target.suffix == ".md" and target.exists():
                docs_path = target.relative_to(docs_dir).as_posix()
                title = target.stem.replace("-", " ").replace("_", " ").title()
                nodes.append(
                    NavNode(
                        title=title,
                        docs_path=docs_path,
                        source_path=target,
                        level=level,
                    )
                )
        elif isinstance(item, dict) and len(item) == 1:
            title, value = next(iter(item.items()))
            if isinstance(value, str):
                target = (base_dir / value).resolve()
                if target.is_dir():
                    children = _resolve_nav_dir(target, docs_dir, level + 1, nav_file)
                    nodes.append(
                        NavNode(
                            title=title,
                            docs_path=None,
                            source_path=None,
                            level=level,
                            children=tuple(children),
                        )
                    )
                else:
                    docs_path = target.relative_to(docs_dir).as_posix() if target.exists() else value
                    nodes.append(
                        NavNode(
                            title=title,
                            docs_path=docs_path,
                            source_path=target if target.exists() else None,
                            level=level,
                        )
                    )
    return nodes


def _resolve_nav_dir(dir_path: Path, docs_dir: Path, level: int, nav_file: str) -> list[NavNode]:
    """Expand *dir_path* into NavNodes using its nav_file, or flat .md discovery."""
    nav_entries = _read_nav_file(dir_path, nav_file)
    if nav_entries is not None:
        return _traverse_nav_dir(nav_entries, dir_path, docs_dir, level, nav_file)
    # No nav_file — return .md files in this directory only (non-recursive)
    nodes: list[NavNode] = []
    for md_file in sorted(dir_path.glob("*.md")):
        docs_path = md_file.relative_to(docs_dir).as_posix()
        nodes.append(
            NavNode(
                title=md_file.stem.replace("-", " ").replace("_", " ").title(),
                docs_path=docs_path,
                source_path=md_file,
                level=level,
            )
        )
    return nodes


def _traverse(nav: list[Any], docs_dir: Path, level: int, nav_file: str = ".pages") -> list[NavNode]:
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
            children = _traverse(value, docs_dir, level=level + 1, nav_file=nav_file)
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
            # Could be a page file or a directory reference (awesome-pages style)
            target = (docs_dir / value).resolve()
            if target.is_dir():
                children = _resolve_nav_dir(target, docs_dir, level + 1, nav_file)
                nodes.append(
                    NavNode(
                        title=title,
                        docs_path=None,
                        source_path=None,
                        level=level,
                        children=tuple(children),
                    )
                )
            else:
                if not target.exists():
                    warnings.warn(
                        f"Nav page '{title}' not found at '{target}' — "
                        "it will be omitted from the resolved nav.",
                        stacklevel=4,
                    )
                nodes.append(
                    NavNode(
                        title=title,
                        docs_path=value,
                        source_path=target if target.exists() else None,
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


def find_section(nodes: list[NavNode], path: str) -> NavNode | None:
    """Find a nav node by slash-separated title path.

    Each segment is matched against node titles, case-insensitively.  An exact
    match is preferred over a partial (contains) match at each level.

    When the path is not found starting from the top level, the search recurses
    into all section children so that ``find_section(nav, "appendix")`` works
    even when "appendix" is nested under another section.

    Examples::

        find_section(nav, "Guide")
        find_section(nav, "Guide/Getting Started")

    Returns the matched :class:`NavNode`, or ``None`` when not found.
    """
    segments = [s.strip() for s in path.split("/") if s.strip()]
    if not segments:
        return None

    result = _match_path(nodes, segments)
    if result is not None:
        return result

    # Not found at this level — recurse into section children (DFS).
    for node in nodes:
        if node.is_section and node.children:
            result = find_section(list(node.children), path)
            if result is not None:
                return result

    return None


def _match_path(nodes: list[NavNode], segments: list[str]) -> NavNode | None:
    """Try to match a multi-segment path starting at *nodes* (non-recursive)."""
    current = nodes
    matched: NavNode | None = None
    for segment in segments:
        seg_lower = segment.lower()
        exact = next((n for n in current if n.title.lower() == seg_lower), None)
        partial = next((n for n in current if seg_lower in n.title.lower()), None)
        matched = exact or partial
        if matched is None:
            return None
        current = list(matched.children)
    return matched


def find_section_by_folder(nodes: list[NavNode], folder: str) -> NavNode | None:
    """Find all nav pages whose ``docs_path`` lives under *folder*.

    Matches any page whose relative docs path starts with ``folder/``
    (case-insensitive, leading/trailing slashes ignored).  Returns a synthetic
    section :class:`NavNode` whose children are the matched pages, preserving
    their original metadata.

    Example::

        find_section_by_folder(nav, "guide")          # matches guide/...
        find_section_by_folder(nav, "guide/advanced")  # matches guide/advanced/...

    Returns ``None`` when no pages match.
    """
    folder_prefix = folder.strip("/").lower() + "/"
    matched = [
        node
        for node in flat_pages(nodes)
        if node.docs_path and node.docs_path.lower().startswith(folder_prefix)
    ]
    if not matched:
        return None

    return NavNode(
        title=folder.strip("/"),
        docs_path=None,
        source_path=None,
        level=0,
        children=tuple(matched),
    )
