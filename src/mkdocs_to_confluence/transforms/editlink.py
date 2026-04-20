"""Edit-link injection transform.

Attaches the source-file URL to the page's :class:`~ir.nodes.FrontMatter`
node so it appears as a **"Source"** row in the Confluence Page Properties
table.  This keeps the link as structured metadata rather than a noisy
banner admonition in the page body.

If the page has no front matter a minimal :class:`~ir.nodes.FrontMatter`
node is created and prepended so the row always appears.

The link is only injected when :meth:`~loader.config.MkDocsConfig.page_edit_url`
returns a non-empty URL (i.e. ``repo_url`` and ``edit_uri`` are both
configured).
"""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import FrontMatter, IRNode


def attach_source_url(
    nodes: tuple[IRNode, ...],
    edit_url: str,
) -> tuple[IRNode, ...]:
    """Attach *edit_url* to the page's FrontMatter as a Source row.

    If the first node is already a :class:`FrontMatter`, it is replaced with
    a copy that has ``source_url`` set.  Otherwise a minimal
    :class:`FrontMatter` is prepended.

    Parameters
    ----------
    nodes:
        Top-level IR nodes for the page.
    edit_url:
        Full URL to the source file edit view (e.g. GitHub edit URL).

    Returns
    -------
    tuple[IRNode, ...]
        New nodes tuple with ``source_url`` attached to the FrontMatter.
    """
    if nodes and isinstance(nodes[0], FrontMatter):
        updated = FrontMatter(
            title=nodes[0].title,
            subtitle=nodes[0].subtitle,
            properties=nodes[0].properties,
            labels=nodes[0].labels,
            source_url=edit_url,
        )
        return (updated,) + nodes[1:]

    # No existing front matter — create a minimal one just for the source row.
    minimal = FrontMatter(
        title=None,
        subtitle=None,
        properties=(),
        labels=(),
        source_url=edit_url,
    )
    return (minimal,) + nodes
