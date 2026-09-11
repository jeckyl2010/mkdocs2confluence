"""Tests for the admonition-title link degradation transform."""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import Admonition, Section, TextNode
from mkdocs_to_confluence.transforms.admonition_titles import (
    strip_links_in_admonition_titles,
)


def _adm(title: str | None) -> Admonition:
    return Admonition(kind="warning", title=title, children=())


def test_link_in_title_stripped_to_text() -> None:
    nodes = (_adm("Conflict - see [Hello](foobar.md#hello)"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "Conflict - see Hello"


def test_warning_emitted_with_page_and_title(capsys) -> None:
    nodes = (_adm("see [Hello](foobar.md#hello)"),)
    strip_links_in_admonition_titles(nodes, "guide/index.md")
    err = capsys.readouterr().err
    assert "warning" in err
    assert "guide/index.md" in err
    assert "see [Hello](foobar.md#hello)" in err


def test_title_without_link_unchanged_and_no_warning(capsys) -> None:
    nodes = (_adm("Just a plain title"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "Just a plain title"
    assert capsys.readouterr().err == ""


def test_none_title_is_safe(capsys) -> None:
    nodes = (_adm(None),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title is None
    assert capsys.readouterr().err == ""


def test_multiple_links_all_stripped() -> None:
    nodes = (_adm("[A](a.md) and [B](b.md#x)"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "A and B"


def test_nested_admonition_in_section_processed() -> None:
    inner = _adm("see [Hello](foobar.md#hello)")
    section = Section(level=2, anchor="s", title=(TextNode("S"),), children=(inner,))
    out = strip_links_in_admonition_titles((section,), "index.md")
    nested = out[0].children[0]
    assert isinstance(nested, Admonition)
    assert nested.title == "see Hello"


def test_image_in_title_not_mangled() -> None:
    nodes = (_adm("look ![alt](img.png)"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "look ![alt](img.png)"


class TestCustomAdmonitionKinds:
    """`confluence.admonitions` config, then built-ins, then a `success` default."""

    def setup_method(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_admonitions
        configure_admonitions(None)

    teardown_method = setup_method

    def _macro(self, src: str) -> str:
        import re

        from mkdocs_to_confluence.emitter.xhtml import emit
        from mkdocs_to_confluence.parser import parse
        m = re.search(r'ac:name="(\w+)"', emit(parse(src)))
        return m.group(1) if m else ""

    def test_hyphenated_kind_parses_as_an_admonition(self) -> None:
        """`!!! value-driver` must not fall through to a paragraph."""
        assert self._macro('!!! value-driver\n\n    Body.\n') != ""

    def test_unknown_kind_defaults_to_success(self) -> None:
        assert self._macro('!!! value-driver\n\n    Body.\n') == "tip"  # success -> tip

    def test_builtin_kind_is_unaffected(self) -> None:
        assert self._macro('!!! note\n\n    Body.\n') == "info"
        assert self._macro('!!! warning\n\n    Body.\n') == "warning"

    def test_config_alias_wins_over_the_default(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_admonitions
        configure_admonitions({"value-driver": "warning"})
        assert self._macro('!!! value-driver\n\n    Body.\n') == "warning"

    def test_config_alias_can_target_a_danger_panel(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_admonitions
        configure_admonitions({"risk": "danger"})
        assert self._macro('!!! risk\n\n    Body.\n') == "panel"

    def test_config_alias_can_override_a_builtin(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_admonitions
        configure_admonitions({"note": "warning"})
        assert self._macro('!!! note\n\n    Body.\n') == "warning"

    def test_title_keeps_the_authors_kind_not_the_alias(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import configure_admonitions, emit
        from mkdocs_to_confluence.parser import parse
        configure_admonitions({"value-driver": "warning"})
        assert "Value-driver" in emit(parse('!!! value-driver\n\n    Body.\n'))

    def test_unknown_alias_target_warns_and_degrades(self, capsys) -> None:  # type: ignore[no-untyped-def]
        from mkdocs_to_confluence.emitter.xhtml import configure_admonitions
        configure_admonitions({"oops": "nonsense"})
        assert "unknown admonition kind" in capsys.readouterr().err
        assert self._macro('!!! oops\n\n    Body.\n') == "tip"
