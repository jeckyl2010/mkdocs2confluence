"""Tests for reference-style link preprocessing."""

import pytest

from mkdocs_to_confluence.preprocess.linkdefs import (
    collect_link_defs,
    expand_link_refs,
    strip_link_defs,
)


# ── collect_link_defs ─────────────────────────────────────────────────────────


def test_collect_basic():
    text = "[spec]: references/spec.pdf"
    defs = collect_link_defs(text)
    assert defs == {"spec": "references/spec.pdf"}


def test_collect_with_title():
    text = '[docs]: https://example.com "Example Title"'
    defs = collect_link_defs(text)
    assert defs == {"docs": "https://example.com"}


def test_collect_multiple():
    text = """
[spec]: references/spec.pdf
[guide]: docs/guide.md
"""
    defs = collect_link_defs(text)
    assert defs == {"spec": "references/spec.pdf", "guide": "docs/guide.md"}


def test_collect_case_insensitive_label():
    text = "[SPEC]: references/spec.pdf"
    defs = collect_link_defs(text)
    assert "spec" in defs


def test_collect_empty():
    assert collect_link_defs("No definitions here.") == {}


def test_collect_allows_leading_spaces():
    text = "   [spec]: references/spec.pdf"
    defs = collect_link_defs(text)
    assert "spec" in defs


# ── expand_link_refs ──────────────────────────────────────────────────────────


def test_expand_full_reference():
    text = "[Download spec][spec]"
    defs = {"spec": "references/spec.pdf"}
    assert expand_link_refs(text, defs) == "[Download spec](references/spec.pdf)"


def test_expand_collapsed_reference():
    text = "[spec][]"
    defs = {"spec": "references/spec.pdf"}
    assert expand_link_refs(text, defs) == "[spec](references/spec.pdf)"


def test_expand_unresolved_left_unchanged():
    text = "[missing][ref]"
    defs = {}
    assert expand_link_refs(text, defs) == "[missing][ref]"


def test_expand_skips_inline_code():
    text = "`[skip][this]` but expand [real][link]"
    defs = {"link": "https://example.com"}
    result = expand_link_refs(text, defs)
    assert "`[skip][this]`" in result
    assert "[real](https://example.com)" in result


def test_expand_no_defs_returns_unchanged():
    text = "[text][ref]"
    assert expand_link_refs(text, {}) == text


def test_expand_multiple_refs_in_text():
    text = "See [spec][s1] and [guide][s2]."
    defs = {"s1": "spec.pdf", "s2": "guide.pdf"}
    result = expand_link_refs(text, defs)
    assert "[spec](spec.pdf)" in result
    assert "[guide](guide.pdf)" in result


def test_expand_in_list():
    text = "- [Download spec][spec]\n- [Read guide][guide]\n"
    defs = {"spec": "references/spec.pdf", "guide": "docs/guide.pdf"}
    result = expand_link_refs(text, defs)
    assert "- [Download spec](references/spec.pdf)" in result
    assert "- [Read guide](docs/guide.pdf)" in result


# ── strip_link_defs ───────────────────────────────────────────────────────────


def test_strip_removes_def_lines():
    text = "Some text.\n\n[spec]: references/spec.pdf\n\nMore text."
    result = strip_link_defs(text)
    assert "[spec]: references/spec.pdf" not in result
    assert "Some text." in result
    assert "More text." in result


def test_strip_leaves_normal_links_intact():
    text = "[inline](https://example.com) is fine.\n\n[label]: url.pdf"
    result = strip_link_defs(text)
    assert "[inline](https://example.com)" in result
    assert "[label]: url.pdf" not in result


# ── Integration: full pipeline ────────────────────────────────────────────────


def test_full_pipeline_reference_style():
    """collect → expand → strip should produce clean inline links."""
    text = (
        "- [Download spec][spec]\n"
        "- [Read guide][guide]\n"
        "\n"
        "[spec]: references/spec.pdf\n"
        "[guide]: docs/guide.pdf\n"
    )
    defs = collect_link_defs(text)
    expanded = expand_link_refs(text, defs)
    cleaned = strip_link_defs(expanded)

    assert "[Download spec](references/spec.pdf)" in cleaned
    assert "[Read guide](docs/guide.pdf)" in cleaned
    assert "[spec]: references/spec.pdf" not in cleaned
    assert "[guide]: docs/guide.pdf" not in cleaned


def test_full_pipeline_no_definitions():
    text = "Just [inline](url.pdf) links here."
    defs = collect_link_defs(text)
    expanded = expand_link_refs(text, defs)
    cleaned = strip_link_defs(expanded)
    assert cleaned == text
