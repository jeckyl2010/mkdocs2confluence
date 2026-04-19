"""Tests for the internal link resolution transform."""

from __future__ import annotations

import pytest

from mkdocs_to_confluence.ir.nodes import (
    BulletList,
    LinkNode,
    ListItem,
    Paragraph,
    TextNode,
)
from mkdocs_to_confluence.transforms.internallinks import (
    _resolve_md_href,
    build_link_map,
    resolve_internal_links,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_nav(pages: list[tuple[str, str]]):
    """Build a minimal list of NavNode-like objects from (docs_path, title) pairs."""
    from pathlib import Path
    from mkdocs_to_confluence.loader.nav import NavNode
    return [
        NavNode(title=title, docs_path=dp, source_path=Path("/docs") / dp, level=0)
        for dp, title in pages
    ]


def _link(href: str, text: str = "click") -> LinkNode:
    return LinkNode(href=href, children=(TextNode(text=text),))


# ── build_link_map ────────────────────────────────────────────────────────────


def test_build_link_map_simple():
    nav = _make_nav([("index.md", "Home"), ("guide/setup.md", "Setup Guide")])
    m = build_link_map(nav)
    assert m == {"index.md": "Home", "guide/setup.md": "Setup Guide"}


def test_build_link_map_skips_sections():
    from mkdocs_to_confluence.loader.nav import NavNode
    child = NavNode(title="Child", docs_path="child.md", source_path=None, level=1)
    section = NavNode(
        title="Section", docs_path=None, source_path=None, level=0,
        children=(child,),
    )
    m = build_link_map([section])
    assert "child.md" in m
    assert None not in m


# ── _resolve_md_href ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("href,current,expected_path,expected_anchor", [
    # same-dir sibling
    ("setup.md", "guide/index.md", "guide/setup.md", ""),
    # parent-dir relative
    ("../index.md", "guide/setup.md", "index.md", ""),
    # same file anchor only — not a .md link
    ("#section", "index.md", None, None),
    # explicit docs-root absolute
    ("/guide/setup.md", "index.md", "guide/setup.md", ""),
    # with fragment
    ("setup.md#configuration", "guide/index.md", "guide/setup.md", "configuration"),
    # non-md extension — should return None
    ("logo.png", "index.md", None, None),
])
def test_resolve_md_href(href, current, expected_path, expected_anchor):
    result = _resolve_md_href(href, current)
    if expected_path is None:
        assert result is None
    else:
        assert result is not None
        assert result[0] == expected_path
        assert result[1] == expected_anchor


# ── resolve_internal_links ────────────────────────────────────────────────────


def _nodes_with_link(href: str) -> tuple:
    return (Paragraph(children=(_link(href),)),)


def test_resolves_same_dir_link():
    nav = _make_nav([("index.md", "Home"), ("guide/setup.md", "Setup Guide")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("setup.md")
    result = resolve_internal_links(nodes, link_map, "guide/index.md")
    para = result[0]
    link = para.children[0]
    assert isinstance(link, LinkNode)
    assert link.is_internal is True
    assert link.href == "Setup Guide"
    assert link.anchor is None


def test_resolves_parent_relative_link():
    nav = _make_nav([("index.md", "Home"), ("guide/setup.md", "Setup Guide")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("../index.md")
    result = resolve_internal_links(nodes, link_map, "guide/setup.md")
    link = result[0].children[0]
    assert link.is_internal is True
    assert link.href == "Home"


def test_preserves_anchor():
    nav = _make_nav([("guide/setup.md", "Setup Guide")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("setup.md#configuration")
    result = resolve_internal_links(nodes, link_map, "guide/index.md")
    link = result[0].children[0]
    assert link.is_internal is True
    assert link.href == "Setup Guide"
    assert link.anchor == "configuration"


def test_leaves_unknown_page_unchanged():
    """Links to pages not in the nav are left as raw .md hrefs."""
    nav = _make_nav([("index.md", "Home")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("missing.md")
    result = resolve_internal_links(nodes, link_map, "index.md")
    link = result[0].children[0]
    assert link.is_internal is False
    assert link.href == "missing.md"


def test_leaves_external_url_unchanged():
    nav = _make_nav([("index.md", "Home")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("https://example.com")
    result = resolve_internal_links(nodes, link_map, "index.md")
    link = result[0].children[0]
    assert link.is_internal is False
    assert link.href == "https://example.com"


def test_leaves_attachment_link_unchanged():
    """Links that already have attachment_name set are not touched."""
    nav = _make_nav([("index.md", "Home")])
    link_map = build_link_map(nav)
    att_link = LinkNode(
        href="guide/setup.md",
        children=(TextNode(text="spec"),),
        attachment_name="guide_setup.md",
    )
    nodes = (Paragraph(children=(att_link,)),)
    result = resolve_internal_links(nodes, link_map, "index.md")
    link = result[0].children[0]
    assert link.is_internal is False
    assert link.attachment_name == "guide_setup.md"


def test_nested_link_in_list():
    """Links nested inside list items are resolved."""
    nav = _make_nav([("guide/setup.md", "Setup Guide")])
    link_map = build_link_map(nav)
    item = ListItem(children=(Paragraph(children=(_link("guide/setup.md"),)),))
    nodes = (BulletList(items=(item,)),)
    result = resolve_internal_links(nodes, link_map, "index.md")
    link = result[0].items[0].children[0].children[0]
    assert isinstance(link, LinkNode)
    assert link.is_internal is True
    assert link.href == "Setup Guide"


# ── Emitter output ────────────────────────────────────────────────────────────


def test_emitter_internal_link_no_anchor():
    from mkdocs_to_confluence.emitter.xhtml import emit
    link = LinkNode(
        href="Setup Guide",
        children=(TextNode(text="Setup"),),
        is_internal=True,
    )
    xhtml = emit((Paragraph(children=(link,)),))
    assert '<ri:page ac:title="Setup Guide"/>' in xhtml
    assert "<ac:link>" in xhtml
    assert "ac:anchor" not in xhtml


def test_emitter_internal_link_with_anchor():
    from mkdocs_to_confluence.emitter.xhtml import emit
    link = LinkNode(
        href="Setup Guide",
        children=(TextNode(text="Config"),),
        is_internal=True,
        anchor="configuration",
    )
    xhtml = emit((Paragraph(children=(link,)),))
    assert 'ac:anchor="configuration"' in xhtml
    assert '<ri:page ac:title="Setup Guide"/>' in xhtml


def test_emitter_plain_link_unchanged():
    from mkdocs_to_confluence.emitter.xhtml import emit
    link = LinkNode(href="https://example.com", children=(TextNode(text="ext"),))
    xhtml = emit((Paragraph(children=(link,)),))
    assert '<a href="https://example.com">ext</a>' in xhtml
