"""Tests for the ChildrenMacro IR node, emitter, and pipeline integration."""

from pathlib import Path
from unittest.mock import patch

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import ChildrenMacro
from mkdocs_to_confluence.publisher.planner import compile_page

# ── Emitter ───────────────────────────────────────────────────────────────────


def test_children_macro_emits_structured_macro() -> None:
    """ChildrenMacro must emit the Confluence children structured macro."""
    xhtml = emit((ChildrenMacro(),))
    assert 'ac:name="children"' in xhtml
    assert 'ac:parameter ac:name="depth"' in xhtml
    assert ">1<" in xhtml


def test_children_macro_no_extra_params() -> None:
    """Children macro must not emit sort/style params — Confluence defaults are fine."""
    xhtml = emit((ChildrenMacro(),))
    assert "sort" not in xhtml
    assert "style" not in xhtml


# ── Pipeline integration ──────────────────────────────────────────────────────


def test_compile_page_section_index_includes_children_macro(tmp_path: Path) -> None:
    """is_section_index=True must inject ChildrenMacro into emitted XHTML."""
    from mkdocs_to_confluence.loader.config import MkDocsConfig

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "index.md"
    md.write_text("# Section\n\nIntro text.\n", encoding="utf-8")

    node = _page_node("Section", md)
    config = MkDocsConfig(site_name="Test", docs_dir=docs, repo_url=None, edit_uri=None, nav=None)

    xhtml, _, _, _, _ = compile_page(node, config, is_section_index=True)

    assert 'ac:name="children"' in xhtml


def test_compile_page_non_index_excludes_children_macro(tmp_path: Path) -> None:
    """Regular pages must NOT include the ChildrenMacro."""
    from mkdocs_to_confluence.loader.config import MkDocsConfig

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "guide.md"
    md.write_text("# Guide\n\nContent.\n", encoding="utf-8")

    node = _page_node("Guide", md)
    config = MkDocsConfig(site_name="Test", docs_dir=docs, repo_url=None, edit_uri=None, nav=None)

    xhtml, _, _, _, _ = compile_page(node, config, is_section_index=False)

    assert 'ac:name="children"' not in xhtml


def test_compile_page_children_macro_before_footer(tmp_path: Path) -> None:
    """ChildrenMacro must appear before the source footer in the XHTML."""
    from mkdocs_to_confluence.loader.config import MkDocsConfig

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "index.md"
    md.write_text("# Section\n\nIntro.\n", encoding="utf-8")

    node = _page_node("Section", md)
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=docs,
        repo_url="https://github.com/org/repo",
        edit_uri="edit/main/docs/",
        nav=None,
    )

    with patch(
        "mkdocs_to_confluence.transforms.footer._last_commit_info", return_value=None
    ):
        xhtml, _, _, _, _ = compile_page(node, config, is_section_index=True)

    children_pos = xhtml.find('ac:name="children"')
    panel_pos = xhtml.find('ac:name="panel"')
    assert children_pos != -1
    assert panel_pos != -1
    assert children_pos < panel_pos


# ── Helpers ───────────────────────────────────────────────────────────────────


def _page_node(title: str, path: Path) -> object:
    from mkdocs_to_confluence.loader.nav import NavNode

    return NavNode(
        title=title,
        docs_path=path.name,
        source_path=path,
        level=0,
        children=(),
    )
