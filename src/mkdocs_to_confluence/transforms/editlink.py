"""Edit-link injection transform.

Prepends a Confluence ``info`` macro to the page containing a link back to the
source file in the version-control repository.  This reinforces the
"Confluence is read-only" contract — readers see an immediate prompt to edit
the source rather than the Confluence page.

The banner is only injected when :meth:`~loader.config.MkDocsConfig.page_edit_url`
returns a non-empty URL (i.e. ``repo_url`` and ``edit_uri`` are both configured).
"""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import (
    Admonition,
    IRNode,
    LinkNode,
    Paragraph,
    TextNode,
)

_EDIT_TITLE = "Auto-generated page"


def inject_edit_link(
    nodes: tuple[IRNode, ...],
    edit_url: str,
    *,
    repo_url: str | None = None,
) -> tuple[IRNode, ...]:
    """Prepend an ``info`` admonition with a source-edit link to *nodes*.

    Parameters
    ----------
    nodes:
        Top-level IR nodes for the page.
    edit_url:
        Full URL to the source file edit view (e.g. GitHub edit URL).
    repo_url:
        Optional repository URL used to derive a short label like
        ``"Edit on GitHub"`` or ``"Edit on GitLab"``.

    Returns
    -------
    tuple[IRNode, ...]
        New nodes tuple with the banner prepended.
    """
    label = _edit_label(repo_url)
    banner = _make_banner(edit_url, label)
    return (banner,) + nodes


def _edit_label(repo_url: str | None) -> str:
    if repo_url:
        if "github.com" in repo_url:
            return "Edit on GitHub ↗"
        if "gitlab.com" in repo_url or "gitlab." in repo_url:
            return "Edit on GitLab ↗"
        if "bitbucket.org" in repo_url:
            return "Edit on Bitbucket ↗"
    return "Edit source ↗"


def _make_banner(edit_url: str, label: str) -> Admonition:
    """Return an ``info`` admonition containing the edit link."""
    link = LinkNode(href=edit_url, children=(TextNode(text=label),))
    intro = TextNode(text="This page is auto-generated from source.  ")
    body = Paragraph(children=(intro, link))
    return Admonition(
        kind="info",
        title=_EDIT_TITLE,
        children=(body,),
        collapsible=False,
    )
