"""Tests for the Confluence XHTML emitter."""

from __future__ import annotations

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import (
    Admonition,
    BoldNode,
    BulletList,
    CodeBlock,
    CodeInlineNode,
    HorizontalRule,
    ItalicNode,
    LinkNode,
    ListItem,
    OrderedList,
    Paragraph,
    Section,
    TextNode,
    UnsupportedBlock,
)


# ── Inline nodes ──────────────────────────────────────────────────────────────


class TestInlineEmitters:
    def test_text_node_escaped(self) -> None:
        out = emit((Paragraph((TextNode("<b>hello</b>"),)),))
        assert "&lt;b&gt;hello&lt;/b&gt;" in out

    def test_bold_node(self) -> None:
        out = emit((Paragraph((BoldNode((TextNode("bold"),)),)),))
        assert "<strong>bold</strong>" in out

    def test_italic_node(self) -> None:
        out = emit((Paragraph((ItalicNode((TextNode("italic"),)),)),))
        assert "<em>italic</em>" in out

    def test_code_inline_node(self) -> None:
        out = emit((Paragraph((CodeInlineNode("x = 1"),)),))
        assert "<code>x = 1</code>" in out

    def test_link_node(self) -> None:
        out = emit((Paragraph((LinkNode("https://example.com", (TextNode("click"),)),)),))
        assert '<a href="https://example.com">click</a>' in out


# ── Block nodes ───────────────────────────────────────────────────────────────


class TestSectionEmitter:
    def test_heading_level(self) -> None:
        node = Section(level=2, anchor="my-section", title=(TextNode("My Section"),), children=())
        out = emit((node,))
        assert "<h2>My Section</h2>" in out

    def test_section_with_paragraph_child(self) -> None:
        child = Paragraph((TextNode("body text"),))
        node = Section(level=1, anchor="intro", title=(TextNode("Intro"),), children=(child,))
        out = emit((node,))
        assert "<h1>Intro</h1>" in out
        assert "<p>body text</p>" in out


class TestParagraphEmitter:
    def test_simple_paragraph(self) -> None:
        out = emit((Paragraph((TextNode("hello world"),)),))
        assert "<p>hello world</p>" in out


class TestCodeBlockEmitter:
    def test_language_parameter(self) -> None:
        out = emit((CodeBlock(code="x = 1", language="python"),))
        assert 'ac:name="code"' in out
        assert 'ac:name="language"' in out
        assert "python" in out
        assert "x = 1" in out

    def test_no_language(self) -> None:
        out = emit((CodeBlock(code="hello"),))
        assert 'ac:name="language"' not in out
        assert "hello" in out

    def test_title_parameter(self) -> None:
        out = emit((CodeBlock(code="pass", language="python", title="example.py"),))
        assert "example.py" in out

    def test_linenums(self) -> None:
        out = emit((CodeBlock(code="pass", linenums=True),))
        assert "linenumbers" in out

    def test_cdata_escaping(self) -> None:
        out = emit((CodeBlock(code="a]]>b"),))
        # The escape sequence splits ]]> across two CDATA sections
        assert "]]]]><![CDATA[>" in out


class TestAdmonitionEmitter:
    def test_note_maps_to_info(self) -> None:
        out = emit((Admonition(kind="note", title=None, children=(Paragraph((TextNode("body"),)),)),))
        assert 'ac:name="info"' in out
        assert "body" in out

    def test_warning_maps_to_warning(self) -> None:
        out = emit((Admonition(kind="warning", title=None, children=()),))
        assert 'ac:name="warning"' in out

    def test_tip_maps_to_tip(self) -> None:
        out = emit((Admonition(kind="tip", title=None, children=()),))
        assert 'ac:name="tip"' in out

    def test_custom_title(self) -> None:
        out = emit((Admonition(kind="note", title="My Custom Title", children=()),))
        assert "My Custom Title" in out

    def test_default_title_used(self) -> None:
        out = emit((Admonition(kind="tip", title=None, children=()),))
        assert "Tip" in out


class TestListEmitters:
    def test_bullet_list(self) -> None:
        items = (ListItem((TextNode("one"),)), ListItem((TextNode("two"),)))
        out = emit((BulletList(items=items),))
        assert "<ul>" in out
        assert "<li>one</li>" in out
        assert "<li>two</li>" in out

    def test_ordered_list(self) -> None:
        items = (ListItem((TextNode("first"),)),)
        out = emit((OrderedList(items=items),))
        assert "<ol>" in out
        assert "<li>first</li>" in out

    def test_ordered_list_custom_start(self) -> None:
        items = (ListItem((TextNode("x"),)),)
        out = emit((OrderedList(items=items, start=5),))
        assert 'start="5"' in out


class TestHorizontalRule:
    def test_hr(self) -> None:
        out = emit((HorizontalRule(),))
        assert "<hr/>" in out


class TestUnsupportedBlock:
    def test_renders_warning_macro(self) -> None:
        out = emit((UnsupportedBlock(raw="some raw content", reason="not supported"),))
        assert 'ac:name="warning"' in out
        assert "some raw content" in out
