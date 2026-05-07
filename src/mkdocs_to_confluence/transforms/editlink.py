"""Edit-link injection transform.

Attaches the published-page URL (from ``site_url``) to the page's
:class:`~ir.nodes.FrontMatter` node so it appears as a row in the
Confluence Page Properties table.

If the page has no front matter a minimal :class:`~ir.nodes.FrontMatter`
node is created and prepended so the row always appears.

The row is only injected when the URL is non-empty.
"""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import FrontMatter, IRNode


def attach_source_url(
    nodes: tuple[IRNode, ...],
    edit_url: str,
    site_url: str | None = None,
) -> tuple[IRNode, ...]:
    """Attach *site_url* to the page's FrontMatter for the Page Properties table.

    Parameters
    ----------
    nodes:
        Top-level IR nodes for the page.
    edit_url:
        Kept for backwards compatibility; no longer stored on FrontMatter.
        Pass an empty string or ``None`` — it is ignored.
    site_url:
        Full URL to the rendered page on the MkDocs site.  When provided,
        a "Published Page" row is added to the Page Properties table.

    Returns
    -------
    tuple[IRNode, ...]
        New nodes tuple with ``site_url`` attached to the FrontMatter.
    """
    if not site_url:
        return nodes

    if nodes and isinstance(nodes[0], FrontMatter):
        updated = FrontMatter(
            title=nodes[0].title,
            subtitle=nodes[0].subtitle,
            properties=nodes[0].properties,
            labels=nodes[0].labels,
            site_url=site_url,
            confluence_status=nodes[0].confluence_status,
        )
        return (updated,) + nodes[1:]

    # No existing front matter — create a minimal one just for the link row.
    minimal = FrontMatter(
        title=None,
        subtitle=None,
        properties=(),
        labels=(),
        site_url=site_url,
    )
    return (minimal,) + nodes
