"""Tests for the internal link resolution transform."""

from __future__ import annotations

from pathlib import Path

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


def test_internal_link_in_table_header_is_resolved():
    """Links inside Table.header cells must be transformed by _rebuild()."""
    from mkdocs_to_confluence.ir.nodes import Table, TableCell, TableRow
    from mkdocs_to_confluence.transforms.internallinks import resolve_internal_links

    link = LinkNode(href="guide.md", children=(TextNode("Guide"),))
    header_cell = TableCell(children=(link,), is_header=True)
    header_row = TableRow(cells=(header_cell,))
    body_cell = TableCell(children=(TextNode("val"),))
    body_row = TableRow(cells=(body_cell,))
    table = Table(header=header_row, rows=(body_row,))

    link_map = {"guide.md": "Setup Guide"}
    result = resolve_internal_links((table,), link_map, "index.md")

    from mkdocs_to_confluence.ir.nodes import walk
    links = [n for n in walk(result[0]) if isinstance(n, LinkNode)]
    assert len(links) == 1
    assert links[0].is_internal is True
    assert links[0].href == "Setup Guide"


def test_asset_in_table_header_is_resolved(tmp_path: Path):
    """Images inside Table.header cells must be resolved by resolve_local_assets."""
    from mkdocs_to_confluence.ir.nodes import ImageNode, Table, TableCell, TableRow
    from mkdocs_to_confluence.transforms.assets import resolve_local_assets

    docs_dir = tmp_path / "docs"
    img_dir = docs_dir / "assets"
    img_dir.mkdir(parents=True)
    img_file = img_dir / "logo.png"
    img_file.write_bytes(b"PNG")
    page_path = docs_dir / "index.md"

    img = ImageNode(src="assets/logo.png", alt="logo")
    header_cell = TableCell(children=(img,), is_header=True)
    header_row = TableRow(cells=(header_cell,))
    table = Table(header=header_row, rows=())

    result_nodes, attachments = resolve_local_assets(
        (table,), page_path=page_path, docs_dir=docs_dir
    )

    from mkdocs_to_confluence.ir.nodes import walk
    images = [n for n in walk(result_nodes[0]) if isinstance(n, ImageNode)]
    assert len(images) == 1
    assert images[0].attachment_name == "assets_logo.png"
    assert len(attachments) == 1


def test_duplicate_asset_references_upload_once(tmp_path: Path):
    """The same file referenced multiple times on a page should appear only once
    in the attachments list so it is uploaded exactly once."""
    from mkdocs_to_confluence.ir.nodes import ImageNode, Paragraph
    from mkdocs_to_confluence.transforms.assets import resolve_local_assets

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    img = docs_dir / "logo.png"
    img.write_bytes(b"PNG")
    page_path = docs_dir / "index.md"

    node1 = ImageNode(src="logo.png", alt="first")
    node2 = ImageNode(src="logo.png", alt="second")
    para = Paragraph(children=(node1, node2))

    _nodes, attachments = resolve_local_assets(
        (para,), page_path=page_path, docs_dir=docs_dir
    )

    assert len(attachments) == 1
    assert attachments[0] == img


# ── URL-encoding ──────────────────────────────────────────────────────────────


def test_url_encoded_internal_link():
    """Percent-encoded hrefs like 'my%20page.md' resolve against real file paths."""
    nav = _make_nav([("my page.md", "My Page")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("my%20page.md")
    result = resolve_internal_links(nodes, link_map, "index.md")
    link = result[0].children[0]
    assert link.is_internal is True
    assert link.href == "My Page"


def test_url_encoded_path_segment():
    """Percent-encoded path segments are decoded before lookup."""
    nav = _make_nav([("sub folder/page.md", "Sub Page")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("sub%20folder/page.md")
    result = resolve_internal_links(nodes, link_map, "index.md")
    link = result[0].children[0]
    assert link.is_internal is True
    assert link.href == "Sub Page"


def test_url_encoded_with_anchor():
    """Percent-encoded href with fragment decodes before lookup; anchor is kept."""
    nav = _make_nav([("my page.md", "My Page")])
    link_map = build_link_map(nav)
    nodes = _nodes_with_link("my%20page.md#section-one")
    result = resolve_internal_links(nodes, link_map, "index.md")
    link = result[0].children[0]
    assert link.is_internal is True
    assert link.href == "My Page"
    assert link.anchor == "section-one"
