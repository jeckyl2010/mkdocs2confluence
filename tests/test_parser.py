"""Tests for parser.markdown — Milestone 5.

Coverage:
- headings: levels, anchors, nesting
- paragraphs: single, multi-line, multiple
- fenced code blocks: no attrs, language, full attrs, tilde fences
- section tree structure
- mixed content
- integration against real fixture files
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mkdocs_to_confluence.ir import (
    Admonition,
    CodeBlock,
    IRNode,
    Paragraph,
    Section,
    TextNode,
    walk,
)
from mkdocs_to_confluence.parser import parse
from mkdocs_to_confluence.parser.markdown import _make_anchor, _parse_info_string

# ── Helpers ───────────────────────────────────────────────────────────────────


def only(nodes: tuple[IRNode, ...], kind: type) -> list[IRNode]:
    """Return all nodes of *kind* from a depth-first walk of *nodes*."""
    result = []
    for root in nodes:
        result.extend(n for n in walk(root) if isinstance(n, kind))
    return result


def first(nodes: tuple[IRNode, ...], kind: type) -> IRNode:
    """Return the first node of *kind* found by depth-first walk."""
    found = only(nodes, kind)
    assert found, f"No {kind.__name__} found in tree"
    return found[0]


# ── _make_anchor ─────────────────────────────────────────────────────────────


class TestMakeAnchor:
    def test_simple_lowercase(self) -> None:
        assert _make_anchor("Hello World") == "hello-world"

    def test_already_lowercase(self) -> None:
        assert _make_anchor("hello world") == "hello-world"

    def test_punctuation_stripped(self) -> None:
        assert _make_anchor("Hello, World!") == "hello-world"

    def test_multiple_spaces_collapsed(self) -> None:
        assert _make_anchor("Hello   World") == "hello-world"

    def test_leading_trailing_stripped(self) -> None:
        assert _make_anchor("  Hello  ") == "hello"

    def test_special_chars_removed(self) -> None:
        assert _make_anchor("C++ Guide") == "c-guide"

    def test_hyphen_preserved(self) -> None:
        assert _make_anchor("Step-by-step Guide") == "step-by-step-guide"

    def test_numbers_preserved(self) -> None:
        assert _make_anchor("Section 1.2") == "section-12"

    def test_unicode_letters_preserved(self) -> None:
        # \w matches unicode letters in Python
        result = _make_anchor("Über Guide")
        assert "ber" in result or "über" in result  # platform-dependent unicode


# ── _parse_info_string ────────────────────────────────────────────────────────


class TestParseInfoString:
    def test_empty_string(self) -> None:
        lang, title, linenums, ln_start, hl = _parse_info_string("")
        assert lang is None
        assert title is None
        assert linenums is False
        assert ln_start == 1
        assert hl == ()

    def test_language_only(self) -> None:
        lang, title, linenums, ln_start, hl = _parse_info_string("python")
        assert lang == "python"
        assert title is None
        assert linenums is False

    def test_bash_language(self) -> None:
        lang, *_ = _parse_info_string("bash")
        assert lang == "bash"

    def test_language_with_title(self) -> None:
        lang, title, *_ = _parse_info_string('python title="main.py"')
        assert lang == "python"
        assert title == "main.py"

    def test_linenums_enables_line_numbers(self) -> None:
        _, _, linenums, ln_start, _ = _parse_info_string('python linenums="1"')
        assert linenums is True
        assert ln_start == 1

    def test_linenums_custom_start(self) -> None:
        _, _, linenums, ln_start, _ = _parse_info_string('python linenums="5"')
        assert linenums is True
        assert ln_start == 5

    def test_hl_lines_single(self) -> None:
        _, _, _, _, hl = _parse_info_string('python hl_lines="3"')
        assert hl == (3,)

    def test_hl_lines_multiple(self) -> None:
        _, _, _, _, hl = _parse_info_string('python hl_lines="2 3 5"')
        assert hl == (2, 3, 5)

    def test_full_attrs(self) -> None:
        lang, title, linenums, ln_start, hl = _parse_info_string(
            'python title="example.py" linenums="1" hl_lines="2 3"'
        )
        assert lang == "python"
        assert title == "example.py"
        assert linenums is True
        assert ln_start == 1
        assert hl == (2, 3)

    def test_no_language_with_title(self) -> None:
        lang, title, *_ = _parse_info_string('title="README.md"')
        assert lang is None
        assert title == "README.md"

    def test_single_quotes(self) -> None:
        lang, title, *_ = _parse_info_string("python title='main.py'")
        assert title == "main.py"


# ── Heading parsing ───────────────────────────────────────────────────────────


class TestHeadings:
    def test_h1_creates_section(self) -> None:
        nodes = parse("# Hello\n")
        assert len(nodes) == 1
        assert isinstance(nodes[0], Section)

    def test_h1_level(self) -> None:
        nodes = parse("# Hello\n")
        assert nodes[0].level == 1  # type: ignore[union-attr]

    def test_h2_level(self) -> None:
        nodes = parse("## Hello\n")
        assert nodes[0].level == 2  # type: ignore[union-attr]

    def test_h6_level(self) -> None:
        nodes = parse("###### Deep\n")
        assert nodes[0].level == 6  # type: ignore[union-attr]

    def test_heading_title_text(self) -> None:
        nodes = parse("# My Title\n")
        section = nodes[0]
        assert isinstance(section, Section)
        assert len(section.title) == 1
        assert isinstance(section.title[0], TextNode)
        assert section.title[0].text == "My Title"

    def test_heading_anchor_generated(self) -> None:
        nodes = parse("# My Title\n")
        section = nodes[0]
        assert isinstance(section, Section)
        assert section.anchor == "my-title"

    def test_heading_anchor_with_punctuation(self) -> None:
        nodes = parse("## Hello, World!\n")
        section = nodes[0]
        assert isinstance(section, Section)
        assert section.anchor == "hello-world"

    def test_multiple_top_level_headings(self) -> None:
        nodes = parse("# One\n## Two\n## Three\n")
        # One H1 containing two H2 sections
        assert len(nodes) == 1
        assert isinstance(nodes[0], Section)
        assert nodes[0].level == 1
        assert len(nodes[0].children) == 2

    def test_sibling_h2_headings(self) -> None:
        nodes = parse("# Root\n## A\n## B\n")
        root = nodes[0]
        assert isinstance(root, Section)
        sections = [c for c in root.children if isinstance(c, Section)]
        assert len(sections) == 2
        assert sections[0].title[0].text == "A"
        assert sections[1].title[0].text == "B"

    def test_h3_nested_inside_h2(self) -> None:
        nodes = parse("## Parent\n### Child\n")
        parent = nodes[0]
        assert isinstance(parent, Section)
        assert parent.level == 2
        child = parent.children[0]
        assert isinstance(child, Section)
        assert child.level == 3

    def test_content_before_heading_goes_to_root(self) -> None:
        nodes = parse("Intro text.\n\n# Heading\n")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Paragraph)
        assert isinstance(nodes[1], Section)


# ── Paragraph parsing ─────────────────────────────────────────────────────────


class TestParagraphs:
    def test_single_line_paragraph(self) -> None:
        nodes = parse("Hello world.\n")
        assert len(nodes) == 1
        assert isinstance(nodes[0], Paragraph)

    def test_paragraph_contains_text_node(self) -> None:
        nodes = parse("Hello world.\n")
        para = nodes[0]
        assert isinstance(para, Paragraph)
        assert len(para.children) == 1
        assert isinstance(para.children[0], TextNode)

    def test_paragraph_text_content(self) -> None:
        nodes = parse("Hello world.\n")
        para = nodes[0]
        assert isinstance(para, Paragraph)
        assert para.children[0].text == "Hello world."

    def test_multi_line_paragraph_joined(self) -> None:
        nodes = parse("Line one.\nLine two.\n")
        para = nodes[0]
        assert isinstance(para, Paragraph)
        assert "Line one." in para.children[0].text
        assert "Line two." in para.children[0].text

    def test_blank_line_separates_paragraphs(self) -> None:
        nodes = parse("First.\n\nSecond.\n")
        paras = [n for n in nodes if isinstance(n, Paragraph)]
        assert len(paras) == 2

    def test_multiple_blank_lines_same_as_one(self) -> None:
        nodes = parse("First.\n\n\nSecond.\n")
        paras = [n for n in nodes if isinstance(n, Paragraph)]
        assert len(paras) == 2

    def test_paragraph_inside_section(self) -> None:
        nodes = parse("# Heading\n\nParagraph text.\n")
        section = nodes[0]
        assert isinstance(section, Section)
        assert len(section.children) == 1
        assert isinstance(section.children[0], Paragraph)

    def test_two_paragraphs_inside_section(self) -> None:
        nodes = parse("# Heading\n\nFirst.\n\nSecond.\n")
        section = nodes[0]
        assert isinstance(section, Section)
        paras = [c for c in section.children if isinstance(c, Paragraph)]
        assert len(paras) == 2


# ── Code block parsing ────────────────────────────────────────────────────────


class TestCodeBlocks:
    def test_basic_code_block(self) -> None:
        md = "```\nprint('hi')\n```\n"
        nodes = parse(md)
        assert len(nodes) == 1
        assert isinstance(nodes[0], CodeBlock)

    def test_code_content_preserved(self) -> None:
        md = "```\nhello\nworld\n```\n"
        cb = first(parse(md), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert "hello" in cb.code
        assert "world" in cb.code

    def test_code_block_no_language(self) -> None:
        cb = first(parse("```\ncode\n```\n"), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.language is None

    def test_code_block_with_language(self) -> None:
        cb = first(parse("```python\ncode\n```\n"), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.language == "python"

    def test_code_block_bash(self) -> None:
        cb = first(parse("```bash\npip install x\n```\n"), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.language == "bash"

    def test_code_block_with_title(self) -> None:
        cb = first(parse('```python title="main.py"\ncode\n```\n'), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.title == "main.py"

    def test_code_block_with_linenums(self) -> None:
        cb = first(parse('```python linenums="1"\ncode\n```\n'), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.linenums is True
        assert cb.linenums_start == 1

    def test_code_block_linenums_custom_start(self) -> None:
        cb = first(parse('```python linenums="5"\ncode\n```\n'), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.linenums_start == 5

    def test_code_block_hl_lines(self) -> None:
        cb = first(parse('```python hl_lines="2 3"\nA\nB\nC\n```\n'), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.highlight_lines == (2, 3)

    def test_code_block_full_attrs(self) -> None:
        md = '```python title="ex.py" linenums="1" hl_lines="2 3"\nA\nB\nC\n```\n'
        cb = first(parse(md), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.language == "python"
        assert cb.title == "ex.py"
        assert cb.linenums is True
        assert cb.highlight_lines == (2, 3)

    def test_tilde_fence(self) -> None:
        cb = first(parse("~~~python\ncode\n~~~\n"), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.language == "python"

    def test_longer_fence_marker(self) -> None:
        cb = first(parse("````python\ncode\n````\n"), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.language == "python"

    def test_code_block_inside_section(self) -> None:
        md = "# Heading\n\n```python\ncode\n```\n"
        nodes = parse(md)
        section = nodes[0]
        assert isinstance(section, Section)
        cb = section.children[0]
        assert isinstance(cb, CodeBlock)

    def test_code_block_multiline_code(self) -> None:
        md = "```python\ndef f():\n    return 1\n\nprint(f())\n```\n"
        cb = first(parse(md), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert "def f():" in cb.code
        assert "return 1" in cb.code
        assert "print(f())" in cb.code

    def test_heading_inside_fence_not_parsed(self) -> None:
        md = "```\n# Not a heading\n```\n"
        nodes = parse(md)
        # Should be one CodeBlock, no Section
        assert len(nodes) == 1
        assert isinstance(nodes[0], CodeBlock)

    def test_code_block_default_values(self) -> None:
        cb = first(parse("```\ncode\n```\n"), CodeBlock)
        assert isinstance(cb, CodeBlock)
        assert cb.linenums is False
        assert cb.linenums_start == 1
        assert cb.highlight_lines == ()
        assert cb.title is None


# ── Section tree structure ────────────────────────────────────────────────────


class TestSectionTree:
    def test_empty_document(self) -> None:
        nodes = parse("")
        assert nodes == ()

    def test_blank_only_document(self) -> None:
        nodes = parse("\n\n\n")
        assert nodes == ()

    def test_single_h1_empty_body(self) -> None:
        nodes = parse("# Title\n")
        assert len(nodes) == 1
        section = nodes[0]
        assert isinstance(section, Section)
        assert section.children == ()

    def test_h1_contains_h2_and_h3(self) -> None:
        md = "# H1\n## H2\n### H3\n"
        nodes = parse(md)
        assert len(nodes) == 1
        h1 = nodes[0]
        assert isinstance(h1, Section)
        assert h1.level == 1
        assert len(h1.children) == 1
        h2 = h1.children[0]
        assert isinstance(h2, Section)
        assert h2.level == 2
        assert len(h2.children) == 1
        h3 = h2.children[0]
        assert isinstance(h3, Section)
        assert h3.level == 3

    def test_two_h1s_produce_two_top_level_sections(self) -> None:
        nodes = parse("# First\n# Second\n")
        assert len(nodes) == 2
        assert all(isinstance(n, Section) and n.level == 1 for n in nodes)

    def test_h2_after_h1_then_another_h2_both_children_of_h1(self) -> None:
        md = "# Root\n## Alpha\n\nContent A.\n## Beta\n\nContent B.\n"
        nodes = parse(md)
        root = nodes[0]
        assert isinstance(root, Section)
        sections = [c for c in root.children if isinstance(c, Section)]
        assert len(sections) == 2
        assert sections[0].title[0].text == "Alpha"
        assert sections[1].title[0].text == "Beta"

    def test_content_before_first_heading_is_in_root(self) -> None:
        md = "Preamble.\n\n# Section\n"
        nodes = parse(md)
        assert len(nodes) == 2
        assert isinstance(nodes[0], Paragraph)
        assert isinstance(nodes[1], Section)

    def test_walk_collects_all_code_blocks(self) -> None:
        md = "# A\n```py\ncode1\n```\n## B\n```js\ncode2\n```\n"
        nodes = parse(md)
        blocks = only(nodes, CodeBlock)
        assert len(blocks) == 2

    def test_walk_collects_all_paragraphs(self) -> None:
        md = "# A\n\nPara 1.\n\n## B\n\nPara 2.\n\nPara 3.\n"
        nodes = parse(md)
        paras = only(nodes, Paragraph)
        assert len(paras) == 3

    def test_section_is_immutable(self) -> None:
        import dataclasses

        nodes = parse("# Hello\n")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nodes[0].level = 99  # type: ignore[misc]


# ── Admonition parsing ────────────────────────────────────────────────────────


class TestAdmonitions:
    def test_basic_note_is_admonition(self) -> None:
        nodes = parse("!!! note\n    Body text.\n")
        assert len(nodes) == 1
        assert isinstance(nodes[0], Admonition)

    def test_kind_parsed(self) -> None:
        adm = first(parse("!!! warning\n    Body.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.kind == "warning"

    def test_all_known_kinds(self) -> None:
        kinds = ["note", "tip", "warning", "danger", "info", "success",
                 "failure", "bug", "abstract", "quote", "example"]
        for kind in kinds:
            adm = first(parse(f"!!! {kind}\n    Body.\n"), Admonition)
            assert isinstance(adm, Admonition)
            assert adm.kind == kind

    def test_no_title_gives_none(self) -> None:
        adm = first(parse("!!! note\n    Body.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.title is None

    def test_double_quoted_title(self) -> None:
        adm = first(parse('!!! warning "Be careful"\n    Body.\n'), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.title == "Be careful"

    def test_single_quoted_title(self) -> None:
        adm = first(parse("!!! tip 'Pro tip'\n    Body.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.title == "Pro tip"

    def test_bang_not_collapsible(self) -> None:
        adm = first(parse("!!! note\n    Body.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.collapsible is False

    def test_question_mark_is_collapsible(self) -> None:
        adm = first(parse("??? note\n    Body.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.collapsible is True

    def test_question_mark_plus_is_collapsible(self) -> None:
        adm = first(parse("???+ note\n    Body.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.collapsible is True

    def test_body_paragraph_parsed(self) -> None:
        adm = first(parse("!!! note\n    Body text here.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert len(adm.children) == 1
        assert isinstance(adm.children[0], Paragraph)

    def test_body_paragraph_text(self) -> None:
        adm = first(parse("!!! note\n    Hello world.\n"), Admonition)
        assert isinstance(adm, Admonition)
        para = adm.children[0]
        assert isinstance(para, Paragraph)
        assert para.children[0].text == "Hello world."

    def test_body_two_paragraphs(self) -> None:
        md = "!!! note\n    First para.\n\n    Second para.\n"
        adm = first(parse(md), Admonition)
        assert isinstance(adm, Admonition)
        paras = [c for c in adm.children if isinstance(c, Paragraph)]
        assert len(paras) == 2

    def test_body_code_block(self) -> None:
        md = (
            "!!! info\n"
            "    ```python\n"
            "    print('hi')\n"
            "    ```\n"
        )
        adm = first(parse(md), Admonition)
        assert isinstance(adm, Admonition)
        cb = adm.children[0]
        assert isinstance(cb, CodeBlock)
        assert cb.language == "python"

    def test_body_paragraph_then_code_block(self) -> None:
        md = (
            "!!! warning\n"
            "    Read this first.\n"
            "\n"
            "    ```bash\n"
            "    rm -rf /\n"
            "    ```\n"
        )
        adm = first(parse(md), Admonition)
        assert isinstance(adm, Admonition)
        assert len(adm.children) == 2
        assert isinstance(adm.children[0], Paragraph)
        assert isinstance(adm.children[1], CodeBlock)

    def test_empty_body_gives_empty_children(self) -> None:
        adm = first(parse("!!! note\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.children == ()

    def test_admonition_followed_by_paragraph(self) -> None:
        md = "!!! note\n    Body.\n\nFollowing paragraph.\n"
        nodes = parse(md)
        assert len(nodes) == 2
        assert isinstance(nodes[0], Admonition)
        assert isinstance(nodes[1], Paragraph)

    def test_admonition_inside_section(self) -> None:
        md = "# Heading\n\n!!! tip\n    Tip body.\n"
        nodes = parse(md)
        section = nodes[0]
        assert isinstance(section, Section)
        adm = section.children[0]
        assert isinstance(adm, Admonition)

    def test_multiple_admonitions(self) -> None:
        md = "!!! note\n    Note body.\n\n!!! warning\n    Warning body.\n"
        nodes = parse(md)
        assert len(nodes) == 2
        assert all(isinstance(n, Admonition) for n in nodes)
        assert nodes[0].kind == "note"  # type: ignore[union-attr]
        assert nodes[1].kind == "warning"  # type: ignore[union-attr]

    def test_walk_finds_nested_code_in_admonition(self) -> None:
        md = "!!! info\n    ```python\n    pass\n    ```\n"
        nodes = parse(md)
        blocks = only(nodes, CodeBlock)
        assert len(blocks) == 1

    def test_admonition_is_immutable(self) -> None:
        import dataclasses
        adm = first(parse("!!! note\n    Body.\n"), Admonition)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            adm.kind = "warning"  # type: ignore[misc]

    def test_unknown_kind_still_parsed(self) -> None:
        adm = first(parse("!!! mycustomtype\n    Body.\n"), Admonition)
        assert isinstance(adm, Admonition)
        assert adm.kind == "mycustomtype"

    def test_paragraph_before_admonition_not_merged(self) -> None:
        md = "Intro text.\n!!! note\n    Body.\n"
        nodes = parse(md)
        assert len(nodes) == 2
        assert isinstance(nodes[0], Paragraph)
        assert isinstance(nodes[1], Admonition)


# ── Integration: real fixture files ──────────────────────────────────────────


class TestFixtureIntegration:
    def test_headings_fixture(self, docs_dir: Path) -> None:
        text = (docs_dir / "headings.md").read_text(encoding="utf-8")
        nodes = parse(text)
        assert len(nodes) == 1
        root = nodes[0]
        assert isinstance(root, Section)
        assert root.title[0].text == "Main Title"

    def test_headings_fixture_h2_children(self, docs_dir: Path) -> None:
        text = (docs_dir / "headings.md").read_text(encoding="utf-8")
        nodes = parse(text)
        root = nodes[0]
        assert isinstance(root, Section)
        h2s = [c for c in root.children if isinstance(c, Section) and c.level == 2]
        assert len(h2s) == 2
        assert h2s[0].title[0].text == "Section One"
        assert h2s[1].title[0].text == "Section Two"

    def test_headings_fixture_h3_nested(self, docs_dir: Path) -> None:
        text = (docs_dir / "headings.md").read_text(encoding="utf-8")
        nodes = parse(text)
        root = nodes[0]
        assert isinstance(root, Section)
        section_one = next(
            c for c in root.children if isinstance(c, Section) and c.level == 2
        )
        h3s = [c for c in section_one.children if isinstance(c, Section)]
        assert len(h3s) == 2

    def test_mixed_fixture_parses(self, docs_dir: Path) -> None:
        text = (docs_dir / "mixed.md").read_text(encoding="utf-8")
        nodes = parse(text)
        assert len(nodes) > 0

    def test_mixed_fixture_has_code_blocks(self, docs_dir: Path) -> None:
        text = (docs_dir / "mixed.md").read_text(encoding="utf-8")
        nodes = parse(text)
        blocks = only(nodes, CodeBlock)
        assert len(blocks) == 2

    def test_mixed_fixture_bash_block(self, docs_dir: Path) -> None:
        text = (docs_dir / "mixed.md").read_text(encoding="utf-8")
        nodes = parse(text)
        blocks = only(nodes, CodeBlock)
        langs = [b.language for b in blocks if isinstance(b, CodeBlock)]
        assert "bash" in langs

    def test_mixed_fixture_python_block_attrs(self, docs_dir: Path) -> None:
        text = (docs_dir / "mixed.md").read_text(encoding="utf-8")
        nodes = parse(text)
        blocks = only(nodes, CodeBlock)
        py_block = next(
            b for b in blocks if isinstance(b, CodeBlock) and b.language == "python"
        )
        assert py_block.title == "main.py"
        assert py_block.linenums is True
        assert py_block.highlight_lines == (2, 3)

    def test_sample_getting_started(self) -> None:
        path = (
            Path(__file__).parent.parent
            / "samples"
            / "tech-docs"
            / "docs"
            / "getting-started.md"
        )
        text = path.read_text(encoding="utf-8")
        nodes = parse(text)
        # Should have at least one section and at least one code block
        sections = only(nodes, Section)
        blocks = only(nodes, CodeBlock)
        assert len(sections) >= 1
        assert len(blocks) >= 1

    def test_admonitions_fixture(self, docs_dir: Path) -> None:
        text = (docs_dir / "admonitions.md").read_text(encoding="utf-8")
        nodes = parse(text)
        admonitions = only(nodes, Admonition)
        assert len(admonitions) >= 8  # fixture has many admonition types

    def test_admonitions_fixture_has_collapsible(self, docs_dir: Path) -> None:
        text = (docs_dir / "admonitions.md").read_text(encoding="utf-8")
        nodes = parse(text)
        admonitions = only(nodes, Admonition)
        collapsible = [a for a in admonitions if isinstance(a, Admonition) and a.collapsible]
        assert len(collapsible) >= 1

    def test_admonitions_fixture_nested_code_block(self, docs_dir: Path) -> None:
        text = (docs_dir / "admonitions.md").read_text(encoding="utf-8")
        nodes = parse(text)
        # The info admonition contains a fenced code block inside
        info_adm = next(
            a for a in only(nodes, Admonition)
            if isinstance(a, Admonition) and a.kind == "info"
        )
        nested_blocks = [c for c in info_adm.children if isinstance(c, CodeBlock)]
        assert len(nested_blocks) == 1
        assert nested_blocks[0].language == "python"

    def test_sample_getting_started_has_admonition(self) -> None:
        path = (
            Path(__file__).parent.parent
            / "samples"
            / "tech-docs"
            / "docs"
            / "getting-started.md"
        )
        text = path.read_text(encoding="utf-8")
        nodes = parse(text)
        admonitions = only(nodes, Admonition)
        assert len(admonitions) >= 1


# ── Inline parsing ────────────────────────────────────────────────────────────


from mkdocs_to_confluence.ir import (
    BlockQuote,
    BoldNode,
    BulletList,
    CodeInlineNode,
    HorizontalRule,
    ItalicNode,
    LinkNode,
    OrderedList,
    StrikethroughNode,
    Table,
)


class TestInlineParsing:
    def test_plain_text_becomes_text_node(self) -> None:
        para = first(parse("Hello world.\n"), Paragraph)
        assert isinstance(para, Paragraph)
        assert isinstance(para.children[0], TextNode)
        assert para.children[0].text == "Hello world."

    def test_bold_star(self) -> None:
        para = first(parse("Hello **world**.\n"), Paragraph)
        assert isinstance(para, Paragraph)
        bold = next(n for n in para.children if isinstance(n, BoldNode))
        assert isinstance(bold.children[0], TextNode)
        assert bold.children[0].text == "world"

    def test_italic_star(self) -> None:
        para = first(parse("Hello *world*.\n"), Paragraph)
        assert isinstance(para, Paragraph)
        italic = next(n for n in para.children if isinstance(n, ItalicNode))
        assert italic.children[0].text == "world"  # type: ignore[union-attr]

    def test_strikethrough(self) -> None:
        para = first(parse("Hello ~~old~~ text.\n"), Paragraph)
        assert isinstance(para, Paragraph)
        strike = next(n for n in para.children if isinstance(n, StrikethroughNode))
        assert strike.children[0].text == "old"  # type: ignore[union-attr]

    def test_inline_code(self) -> None:
        para = first(parse("Use `foo()` here.\n"), Paragraph)
        assert isinstance(para, Paragraph)
        code = next(n for n in para.children if isinstance(n, CodeInlineNode))
        assert code.code == "foo()"

    def test_link(self) -> None:
        para = first(parse("[Click here](https://example.com)\n"), Paragraph)
        assert isinstance(para, Paragraph)
        link = next(n for n in para.children if isinstance(n, LinkNode))
        assert link.href == "https://example.com"
        assert link.children[0].text == "Click here"  # type: ignore[union-attr]

    def test_heading_bold(self) -> None:
        nodes = parse("# **Bold** heading\n")
        section = nodes[0]
        assert isinstance(section, Section)
        assert any(isinstance(n, BoldNode) for n in section.title)


# ── List parsing ──────────────────────────────────────────────────────────────


class TestListParsing:
    def test_bullet_list_nodes(self) -> None:
        nodes = parse("- Alpha\n- Beta\n- Gamma\n")
        bl = first(nodes, BulletList)
        assert isinstance(bl, BulletList)
        assert len(bl.items) == 3

    def test_bullet_item_text(self) -> None:
        nodes = parse("- Hello world\n")
        bl = first(nodes, BulletList)
        assert isinstance(bl, BulletList)
        assert bl.items[0].children[0].text == "Hello world"  # type: ignore[union-attr]

    def test_bullet_item_with_link(self) -> None:
        nodes = parse("- [Docs](docs.md)\n")
        bl = first(nodes, BulletList)
        assert isinstance(bl, BulletList)
        link = next(
            n for n in bl.items[0].children if isinstance(n, LinkNode)
        )
        assert link.href == "docs.md"

    def test_task_list_checked(self) -> None:
        nodes = parse("- [x] Done item\n")
        bl = first(nodes, BulletList)
        assert isinstance(bl, BulletList)
        assert bl.items[0].task is True

    def test_task_list_unchecked(self) -> None:
        nodes = parse("- [ ] Todo item\n")
        bl = first(nodes, BulletList)
        assert isinstance(bl, BulletList)
        assert bl.items[0].task is False

    def test_ordered_list(self) -> None:
        nodes = parse("1. First\n2. Second\n3. Third\n")
        ol = first(nodes, OrderedList)
        assert isinstance(ol, OrderedList)
        assert len(ol.items) == 3
        assert ol.start == 1

    def test_ordered_list_custom_start(self) -> None:
        nodes = parse("5. Fifth\n6. Sixth\n")
        ol = first(nodes, OrderedList)
        assert isinstance(ol, OrderedList)
        assert ol.start == 5

    def test_loose_ordered_list_is_single_node(self) -> None:
        """Blank lines between items (loose list) must not split into multiple OLs."""
        nodes = parse("1. First\n\n1. Second\n\n1. Third\n")
        ols = only(nodes, OrderedList)
        assert len(ols) == 1, "loose ordered list must produce exactly one OrderedList"
        assert len(ols[0].items) == 3

    def test_loose_bullet_list_is_single_node(self) -> None:
        """Blank lines between items (loose list) must not split into multiple ULs."""
        nodes = parse("- Apple\n\n- Banana\n\n- Cherry\n")
        uls = only(nodes, BulletList)
        assert len(uls) == 1, "loose bullet list must produce exactly one BulletList"
        assert len(uls[0].items) == 3

    def test_loose_ordered_list_in_admonition(self) -> None:
        """Loose ordered list inside an admonition must stay as one OrderedList."""
        md = "!!! note\n    1. First\n\n    1. Second\n\n    1. Third\n"
        nodes = parse(md)
        adm = first(nodes, Admonition)
        assert adm is not None
        ols = only(adm.children, OrderedList)
        assert len(ols) == 1, "loose ordered list in admonition must be a single OrderedList"
        assert len(ols[0].items) == 3


# ── Table parsing ─────────────────────────────────────────────────────────────


class TestTableParsing:
    def test_basic_table(self) -> None:
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        tbl = first(parse(md), Table)
        assert isinstance(tbl, Table)

    def test_table_header_cells(self) -> None:
        md = "| Name | Value |\n|------|-------|\n| foo  | bar   |\n"
        tbl = first(parse(md), Table)
        assert isinstance(tbl, Table)
        assert tbl.header.cells[0].children[0].text == "Name"  # type: ignore[union-attr]
        assert tbl.header.cells[1].children[0].text == "Value"  # type: ignore[union-attr]

    def test_table_body_rows(self) -> None:
        md = "| A | B |\n|---|---|\n| x | y |\n| p | q |\n"
        tbl = first(parse(md), Table)
        assert isinstance(tbl, Table)
        assert len(tbl.rows) == 2

    def test_table_header_is_th(self) -> None:
        md = "| H1 | H2 |\n|----|----|\n| v1 | v2 |\n"
        tbl = first(parse(md), Table)
        assert isinstance(tbl, Table)
        assert all(c.is_header for c in tbl.header.cells)

    def test_table_right_align(self) -> None:
        md = "| Num |\n| ---: |\n| 42 |\n"
        tbl = first(parse(md), Table)
        assert isinstance(tbl, Table)
        assert tbl.rows[0].cells[0].align == "right"

    def test_table_center_align(self) -> None:
        md = "| X |\n| :---: |\n| v |\n"
        tbl = first(parse(md), Table)
        assert isinstance(tbl, Table)
        assert tbl.rows[0].cells[0].align == "center"


# ── Blockquote and HR parsing ─────────────────────────────────────────────────


class TestBlockquoteAndHR:
    def test_blockquote(self) -> None:
        nodes = parse("> Hello\n")
        bq = first(nodes, BlockQuote)
        assert isinstance(bq, BlockQuote)

    def test_blockquote_inline(self) -> None:
        nodes = parse("> **Bold** text\n")
        bq = first(nodes, BlockQuote)
        assert isinstance(bq, BlockQuote)
        para = first(bq.children, Paragraph)
        assert isinstance(para, Paragraph)
        assert any(isinstance(n, BoldNode) for n in para.children)

    def test_horizontal_rule_dashes(self) -> None:
        nodes = parse("---\n")
        assert any(isinstance(n, HorizontalRule) for n in nodes)

    def test_horizontal_rule_stars(self) -> None:
        nodes = parse("***\n")
        assert any(isinstance(n, HorizontalRule) for n in nodes)

    def test_hr_does_not_break_surrounding_paragraphs(self) -> None:
        nodes = parse("Before.\n\n---\n\nAfter.\n")
        paras = only(nodes, Paragraph)
        assert len(paras) == 2
