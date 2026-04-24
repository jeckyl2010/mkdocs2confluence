"""Tests for extra_css loader and emitter style injection."""

from __future__ import annotations

from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.extra_css import (
    ExtraStyles,
    load_extra_styles,
    styles_to_attr,
)


# ── styles_to_attr ────────────────────────────────────────────────────────────

class TestStylesToAttr:
    def test_empty(self) -> None:
        assert styles_to_attr({}) == ""

    def test_single_prop(self) -> None:
        assert styles_to_attr({"color": "red"}) == ' style="color: red"'

    def test_multiple_props(self) -> None:
        attr = styles_to_attr({"background-color": "#fff", "color": "black"})
        assert 'background-color: #fff' in attr
        assert 'color: black' in attr
        assert attr.startswith(' style="')


# ── load_extra_styles ─────────────────────────────────────────────────────────

class TestLoadExtraStyles:
    def test_missing_file_is_ignored(self, tmp_path: Path) -> None:
        styles = load_extra_styles(tmp_path, ["nonexistent.css"])
        assert styles.is_empty()

    def test_url_is_skipped(self, tmp_path: Path) -> None:
        styles = load_extra_styles(tmp_path, ["https://example.com/extra.css"])
        assert styles.is_empty()

    def test_th_background_color(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("th { background-color: #1e88e5; color: white; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["background-color"] == "#1e88e5"
        assert styles.th["color"] == "white"
        assert not styles.td

    def test_td_styles(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("td { color: #333; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.td["color"] == "#333"

    def test_thead_th_selector(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("thead th { background-color: navy; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["background-color"] == "navy"

    def test_heading_styles(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("h1 { color: purple; } h2 { color: teal; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.headings["h1"]["color"] == "purple"
        assert styles.headings["h2"]["color"] == "teal"
        assert "h3" not in styles.headings

    def test_code_inline_styles(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("code { background-color: #f5f5f5; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.code_inline["background-color"] == "#f5f5f5"

    def test_pre_code_is_skipped(self, tmp_path: Path) -> None:
        """pre code targets code blocks, not inline code — should be ignored."""
        css = (tmp_path / "extra.css")
        css.write_text("pre code { background-color: #000; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert not styles.code_inline

    def test_hover_pseudo_skipped(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("th:hover { background-color: red; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert not styles.th

    def test_unknown_property_ignored(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("th { z-index: 99; background-color: blue; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert "z-index" not in styles.th
        assert styles.th["background-color"] == "blue"

    def test_comma_separated_selectors(self, tmp_path: Path) -> None:
        css = (tmp_path / "extra.css")
        css.write_text("th, td { color: #333; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["color"] == "#333"
        assert styles.td["color"] == "#333"

    def test_multiple_files_merged(self, tmp_path: Path) -> None:
        (tmp_path / "a.css").write_text("th { color: red; }")
        (tmp_path / "b.css").write_text("th { background-color: blue; }")
        styles = load_extra_styles(tmp_path, ["a.css", "b.css"])
        assert styles.th["color"] == "red"
        assert styles.th["background-color"] == "blue"


# ── Emitter integration ───────────────────────────────────────────────────────

class TestEmitterStyleInjection:
    """Tests that configure_styles() feeds through to the emitter output."""

    def setup_method(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_styles
        configure_styles(None)  # reset between tests

    def teardown_method(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_styles
        configure_styles(None)

    def test_th_style_injected(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_styles, emit
        from mkdocs_to_confluence.ir.nodes import Table, TableCell, TableRow, TextNode
        styles = ExtraStyles(th={"background-color": "#1e88e5", "color": "white"})
        configure_styles(styles)
        table = Table(
            header=TableRow(cells=(TableCell(children=(TextNode("H"),), is_header=True, align=None),)),
            rows=[],
        )
        out = emit((table,))
        assert 'background-color: #1e88e5' in out
        assert 'color: white' in out
        assert '<th' in out

    def test_th_align_merged_with_style(self) -> None:
        """Cell align should be merged with global th styles."""
        from mkdocs_to_confluence.emitter.xhtml import configure_styles, emit
        from mkdocs_to_confluence.ir.nodes import Table, TableCell, TableRow, TextNode
        styles = ExtraStyles(th={"background-color": "navy"})
        configure_styles(styles)
        table = Table(
            header=TableRow(cells=(TableCell(children=(TextNode("H"),), is_header=True, align="center"),)),
            rows=[],
        )
        out = emit((table,))
        assert 'background-color: navy' in out
        assert 'text-align: center' in out

    def test_heading_style_injected(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_styles, emit
        from mkdocs_to_confluence.ir.nodes import Section, TextNode
        styles = ExtraStyles(headings={"h2": {"color": "purple"}})
        configure_styles(styles)
        node = Section(level=2, title=(TextNode("Title"),), anchor="title", children=())
        out = emit((node,))
        assert '<h2 style="color: purple">' in out

    def test_code_inline_style_injected(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_styles, emit
        from mkdocs_to_confluence.ir.nodes import CodeInlineNode, Paragraph
        styles = ExtraStyles(code_inline={"background-color": "#f5f5f5"})
        configure_styles(styles)
        out = emit((Paragraph((CodeInlineNode(code="x"),),),))
        assert '<code style="background-color: #f5f5f5">x</code>' in out

    def test_no_styles_no_change(self) -> None:
        """With no styles configured, output is unchanged."""
        from mkdocs_to_confluence.emitter.xhtml import configure_styles, emit
        from mkdocs_to_confluence.ir.nodes import CodeInlineNode, Paragraph
        configure_styles(None)
        out = emit((Paragraph((CodeInlineNode(code="x"),),),))
        assert '<code>x</code>' in out


# ── CSS var() resolution ──────────────────────────────────────────────────────

class TestVarResolution:
    """Tests for CSS custom property (var()) resolution in load_extra_styles."""

    def test_simple_var_resolved(self, tmp_path: Path) -> None:
        """var(--primary) defined in :root is substituted."""
        css = (tmp_path / "extra.css")
        css.write_text(":root { --primary: #1e88e5; } th { background-color: var(--primary); }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["background-color"] == "#1e88e5"

    def test_nested_var_resolved(self, tmp_path: Path) -> None:
        """--a references --b; --b is a literal — should chain-resolve."""
        css = (tmp_path / "extra.css")
        css.write_text(":root { --b: navy; --a: var(--b); } th { color: var(--a); }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["color"] == "navy"

    def test_unresolved_var_skips_property(self, tmp_path: Path) -> None:
        """var(--undefined) with no fallback — property is silently skipped."""
        css = (tmp_path / "extra.css")
        css.write_text("th { background-color: var(--no-such-var); color: red; }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert "background-color" not in styles.th
        assert styles.th["color"] == "red"  # other properties still applied

    def test_fallback_used_when_var_missing(self, tmp_path: Path) -> None:
        """var(--x, #fff) uses fallback when --x is not defined."""
        css = (tmp_path / "extra.css")
        css.write_text("th { background-color: var(--x, #ffffff); }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["background-color"] == "#ffffff"

    def test_fallback_ignored_when_var_defined(self, tmp_path: Path) -> None:
        """var(--x, fallback) uses the variable, not the fallback, when --x is set."""
        css = (tmp_path / "extra.css")
        css.write_text(":root { --x: blue; } th { color: var(--x, red); }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["color"] == "blue"

    def test_cycle_guard(self, tmp_path: Path) -> None:
        """Cyclic vars (--a: var(--b), --b: var(--a)) skip the property rather than looping."""
        css = (tmp_path / "extra.css")
        css.write_text(":root { --a: var(--b); --b: var(--a); } th { color: var(--a); }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert "color" not in styles.th

    def test_var_in_non_root_rule_collected(self, tmp_path: Path) -> None:
        """Custom properties defined outside :root are also collected."""
        css = (tmp_path / "extra.css")
        css.write_text("[data-md-color-scheme] { --accent: #e91e63; } th { color: var(--accent); }")
        styles = load_extra_styles(tmp_path, ["extra.css"])
        assert styles.th["color"] == "#e91e63"

