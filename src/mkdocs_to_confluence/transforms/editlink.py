"""Edit-link injection transform.

Attaches the source-file URL and optional published-page URL to the page's
:class:`~ir.nodes.FrontMatter` node so they appear as rows in the Confluence
Page Properties table.

- **Source** row: the VCS edit URL (from ``repo_url`` + ``edit_uri``)
- **Published Page** row: the rendered MkDocs URL (from ``site_url``)

If the page has no front matter a minimal :class:`~ir.nodes.FrontMatter`
node is created and prepended so the rows always appear.

Rows are only injected when the corresponding URL is non-empty.
"""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import FrontMatter, IRNode


def attach_source_url(
    nodes: tuple[IRNode, ...],
    edit_url: str,
    site_url: str | None = None,
) -> tuple[IRNode, ...]:
    """Attach *edit_url* (and optionally *site_url*) to the page's FrontMatter.

    Parameters
    ----------
    nodes:
        Top-level IR nodes for the page.
    edit_url:
        Full URL to the source file edit view (e.g. GitHub edit URL).
    site_url:
        Full URL to the rendered page on the MkDocs site.  When provided,
        a "Published Page" row is added after the "Source" row.

    Returns
    -------
    tuple[IRNode, ...]
        New nodes tuple with URL(s) attached to the FrontMatter.
    """
    if nodes and isinstance(nodes[0], FrontMatter):
        updated = FrontMatter(
            title=nodes[0].title,
            subtitle=nodes[0].subtitle,
            properties=nodes[0].properties,
            labels=nodes[0].labels,
            source_url=edit_url,
            site_url=site_url,
        )
        return (updated,) + nodes[1:]

    # No existing front matter — create a minimal one just for the link rows.
    minimal = FrontMatter(
        title=None,
        subtitle=None,
        properties=(),
        labels=(),
        source_url=edit_url,
        site_url=site_url,
    )
    return (minimal,) + nodes
