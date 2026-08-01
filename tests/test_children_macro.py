"""Tests for the ChildrenMacro IR node, emitter, and pipeline integration."""

from pathlib import Path
from unittest.mock import patch

from mkdocs_to_confluence.compiler.page import compile_page
from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import ChildrenMacro

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

    xhtml = compile_page(node, config, is_section_index=True).xhtml

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

    xhtml = compile_page(node, config, is_section_index=False).xhtml

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
        xhtml = compile_page(node, config, is_section_index=True).xhtml

    children_pos = xhtml.find('ac:name="children"')
    panel_pos = xhtml.find('ac:name="panel"')
    assert children_pos != -1
    assert panel_pos != -1
    assert children_pos < panel_pos


# ── children_macro config flag ────────────────────────────────────────────────


def test_children_macro_disabled_omits_macro(tmp_path: Path) -> None:
    """confluence.children_macro=false must suppress the macro on section indexes."""
    xhtml = _compile_index(tmp_path, children_macro=False)

    assert 'ac:name="children"' not in xhtml


def test_children_macro_enabled_by_default(tmp_path: Path) -> None:
    """A confluence block without children_macro must keep the macro."""
    xhtml = _compile_index(tmp_path, children_macro=True)

    assert 'ac:name="children"' in xhtml


def test_children_macro_config_default_true(tmp_path: Path) -> None:
    from mkdocs_to_confluence.loader.config import load_config

    cfg = load_config(_write_mkdocs(tmp_path, _CONF))
    assert cfg.confluence.children_macro is True


def test_children_macro_config_false(tmp_path: Path) -> None:
    from mkdocs_to_confluence.loader.config import load_config

    cfg = load_config(_write_mkdocs(tmp_path, _CONF + "  children_macro: false\n"))
    assert cfg.confluence.children_macro is False


def test_children_macro_config_non_bool_raises(tmp_path: Path) -> None:
    import pytest

    from mkdocs_to_confluence.loader.config import ConfigError, load_config

    with pytest.raises(ConfigError, match="children_macro"):
        load_config(_write_mkdocs(tmp_path, _CONF + "  children_macro: maybe\n"))


# ── Helpers ───────────────────────────────────────────────────────────────────


_CONF = (
    "confluence:\n"
    "  base_url: https://x.atlassian.net/wiki\n"
    "  email: a@b.test\n"
    "  space_key: TECH\n"
)


def _write_mkdocs(tmp_path: Path, extra: str = "") -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "mkdocs.yml").write_text(f"site_name: Test Site\n{extra}", encoding="utf-8")
    return tmp_path / "mkdocs.yml"


def _compile_index(tmp_path: Path, *, children_macro: bool) -> str:
    """Compile a section index page with a confluence block set to *children_macro*."""
    from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "index.md"
    md.write_text("# Section\n\nIntro.\n", encoding="utf-8")

    config = MkDocsConfig(
        site_name="Test",
        docs_dir=docs,
        repo_url=None,
        edit_uri=None,
        nav=None,
        confluence=ConfluenceConfig(
            base_url="https://x.atlassian.net/wiki",
            email="a@b.test",
            token="",
            space_key="TECH",
            children_macro=children_macro,
        ),
    )
    return compile_page(_page_node("Section", md), config, is_section_index=True).xhtml


def _page_node(title: str, path: Path) -> object:
    from mkdocs_to_confluence.loader.nav import NavNode

    return NavNode(
        title=title,
        docs_path=path.name,
        source_path=path,
        level=0,
        children=(),
    )
