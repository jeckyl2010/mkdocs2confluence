"""Load raw markdown content for a single page from the nav tree."""

from __future__ import annotations

from pathlib import Path

from mkdocs_to_confluence.loader.nav import NavNode


class PageLoadError(Exception):
    """Raised when a page cannot be loaded from disk.

    Typical cause: the nav entry existed but the file was missing at resolution
    time, so ``NavNode.source_path`` is ``None``.
    """


def find_page(nodes: list[NavNode], docs_path: str) -> NavNode | None:
    """Search *nodes* (and their descendants) for a node matching *docs_path*.

    Performs a depth-first search so that page order is preserved.

    Args:
        nodes: Top-level nav nodes as returned by :func:`~loader.nav.resolve_nav`.
        docs_path: Path relative to ``docs_dir``, e.g. ``"guide/installation.md"``.

    Returns:
        The matching :class:`~loader.nav.NavNode`, or ``None`` if not found.
    """
    for node in nodes:
        if node.docs_path == docs_path:
            return node
        found = find_page(list(node.children), docs_path)
        if found is not None:
            return found
    return None


def load_page(node: NavNode) -> str:
    """Read and return the raw UTF-8 markdown content of *node*.

    Args:
        node: A resolved :class:`~loader.nav.NavNode` whose ``source_path``
            points to a ``.md`` file on disk.

    Returns:
        The full text content of the markdown file.

    Raises:
        PageLoadError: If ``node.source_path`` is ``None`` (file was absent
            when the nav was resolved).
        OSError: If the file exists in the nav but cannot be read.
    """
    if node.source_path is None:
        raise PageLoadError(
            f"Cannot load page '{node.title}' ({node.docs_path!r}): "
            "source file was not found when the nav was resolved."
        )
    return Path(node.source_path).read_text(encoding="utf-8")
