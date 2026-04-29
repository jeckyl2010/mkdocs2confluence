"""Tests for the Confluence XHTML emitter."""

from __future__ import annotations

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import (
    Admonition,
    BoldNode,
    BulletList,
    CodeBlock,
    CodeInlineNode,
    ContentTabs,
    Expandable,
    HorizontalRule,
    ItalicNode,
    LinkNode,
    ListItem,
    OrderedList,
    Paragraph,
    Section,
    Tab,
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

    def test_collapsible_maps_to_expand(self) -> None:
        out = emit((
            Admonition(kind="note", title="Hidden", children=(Paragraph((TextNode("secret"),)),), collapsible=True),
        ))
        assert 'ac:name="expand"' in out
        assert 'ac:name="info"' not in out
        assert "Hidden" in out
        assert "secret" in out

    def test_collapsible_danger_still_expand(self) -> None:
        # Even danger kinds should use expand when collapsible
        out = emit((Admonition(kind="danger", title="Careful", children=(), collapsible=True),))
        assert 'ac:name="expand"' in out
        assert 'ac:name="panel"' not in out


class TestContentTabsEmitter:
    def test_tabs_render_as_expand_macros(self) -> None:
        tabs = (
            Tab(label="Python", children=(Paragraph((TextNode("py code"),)),)),
            Tab(label="Bash", children=(Paragraph((TextNode("sh code"),)),)),
        )
        out = emit((ContentTabs(tabs=tabs),))
        assert out.count('ac:name="expand"') == 2
        assert "Python" in out
        assert "Bash" in out
        assert "py code" in out

    def test_single_tab(self) -> None:
        tabs = (Tab(label="Only", children=(Paragraph((TextNode("content"),)),)),)
        out = emit((ContentTabs(tabs=tabs),))
        assert 'ac:name="expand"' in out
        assert "Only" in out


class TestExpandableEmitter:
    def test_expand_macro(self) -> None:
        out = emit((Expandable(title="Details", children=(Paragraph((TextNode("body"),)),)),))
        assert 'ac:name="expand"' in out
        assert "Details" in out
        assert "body" in out


class TestListEmitters:
    def test_bullet_list(self) -> None:
        items = (ListItem((TextNode("one"),)), ListItem((TextNode("two"),)))
        out = emit((BulletList(items=items),))
        assert "<ul>" in out
        assert "<li><p>one</p></li>" in out
        assert "<li><p>two</p></li>" in out

    def test_ordered_list(self) -> None:
        items = (ListItem((TextNode("first"),)),)
        out = emit((OrderedList(items=items),))
        assert "<ol>" in out
        assert "<li><p>first</p></li>" in out

    def test_ordered_list_custom_start(self) -> None:
        items = (ListItem((TextNode("x"),)),)
        out = emit((OrderedList(items=items, start=5),))
        assert 'start="5"' in out

    def test_list_item_with_external_link(self) -> None:
        # Inline links in list items must be wrapped in <p> so Confluence
        # renders them — without <p>, structured elements are stripped.
        link = LinkNode("https://example.com", (TextNode("Example"),))
        items = (ListItem((link,)),)
        out = emit((BulletList(items=items),))
        assert "<li><p>" in out
        assert '<a href="https://example.com">Example</a>' in out

    def test_task_list_unchecked(self) -> None:
        items = (ListItem((TextNode("do this"),), task=False),)
        out = emit((BulletList(items=items),))
        assert "<ac:task-list>" in out
        assert "<ac:task-status>incomplete</ac:task-status>" in out
        assert "<ac:task-body>do this</ac:task-body>" in out
        assert "<ul>" not in out

    def test_task_list_checked(self) -> None:
        items = (ListItem((TextNode("done"),), task=True),)
        out = emit((BulletList(items=items),))
        assert "<ac:task-list>" in out
        assert "<ac:task-status>complete</ac:task-status>" in out
        assert "<ac:task-body>done</ac:task-body>" in out

    def test_task_list_mixed_checked_unchecked(self) -> None:
        items = (
            ListItem((TextNode("done"),), task=True),
            ListItem((TextNode("pending"),), task=False),
        )
        out = emit((BulletList(items=items),))
        assert out.count("<ac:task>") == 2
        assert "<ac:task-status>complete</ac:task-status>" in out
        assert "<ac:task-status>incomplete</ac:task-status>" in out

    def test_regular_list_not_wrapped_in_task_list(self) -> None:
        items = (ListItem((TextNode("normal"),), task=None),)
        out = emit((BulletList(items=items),))
        assert "<ul>" in out
        assert "<ac:task-list>" not in out


class TestHorizontalRule:
    def test_hr(self) -> None:
        out = emit((HorizontalRule(),))
        assert "<hr/>" in out


class TestUnsupportedBlock:
    def test_renders_warning_macro(self) -> None:
        out = emit((UnsupportedBlock(raw="some raw content", reason="not supported"),))
        assert 'ac:name="warning"' in out
        assert "some raw content" in out


# ── Missing node coverage ─────────────────────────────────────────────────────

from mkdocs_to_confluence.ir.nodes import (  # noqa: E402
    BlockQuote,
    DefinitionItem,
    DefinitionList,
    ImageNode,
    StrikethroughNode,
    SubscriptNode,
    SuperscriptNode,
    Table,
    TableCell,
    TableRow,
)


class TestStrikethroughEmitter:
    def test_strikethrough_node(self) -> None:
        out = emit((Paragraph((StrikethroughNode((TextNode("old"),)),)),))
        assert "<s>old</s>" in out


class TestSubscriptSuperscriptEmitter:
    def test_subscript(self) -> None:
        out = emit((Paragraph((SubscriptNode((TextNode("2"),)),)),))
        assert "<sub>2</sub>" in out

    def test_superscript(self) -> None:
        out = emit((Paragraph((SuperscriptNode((TextNode("2"),)),)),))
        assert "<sup>2</sup>" in out


class TestDefinitionListEmitter:
    def test_basic_dl(self) -> None:
        item = DefinitionItem(
            term=(TextNode("Apple"),),
            definitions=((TextNode("A fruit"),),),
        )
        out = emit((DefinitionList(items=(item,)),))
        assert "<dl>" in out
        assert "<dt>Apple</dt>" in out
        assert "<dd>A fruit</dd>" in out

    def test_multiple_definitions(self) -> None:
        item = DefinitionItem(
            term=(TextNode("Color"),),
            definitions=((TextNode("Red"),), (TextNode("Blue"),)),
        )
        out = emit((DefinitionList(items=(item,)),))
        assert out.count("<dd>") == 2


class TestBlockQuoteEmitter:
    def test_blockquote_wraps_children(self) -> None:
        out = emit((BlockQuote(children=(Paragraph((TextNode("quote"),)),)),))
        assert "<blockquote>" in out
        assert "<p>quote</p>" in out
        assert "</blockquote>" in out


class TestImageEmitter:
    def test_image_url(self) -> None:
        out = emit((Paragraph((ImageNode(src="https://example.com/img.png", alt="logo"),),),))
        assert '<ri:url ri:value="https://example.com/img.png"/>' in out
        assert "<ac:image" in out

    def test_image_alt(self) -> None:
        out = emit((Paragraph((ImageNode(src="img.png", alt="desc"),),),))
        assert 'ac:alt="desc"' in out

    def test_image_title(self) -> None:
        out = emit((Paragraph((ImageNode(src="img.png", alt="", title="My title"),),),))
        assert 'ac:title="My title"' in out

    def test_image_width(self) -> None:
        out = emit((Paragraph((ImageNode(src="img.png", alt="", width=400),),),))
        assert 'ac:width="400"' in out

    def test_image_height(self) -> None:
        out = emit((Paragraph((ImageNode(src="img.png", alt="", height=200),),),))
        assert 'ac:height="200"' in out

    def test_image_align(self) -> None:
        out = emit((Paragraph((ImageNode(src="img.png", alt="", align="center"),),),))
        assert 'ac:align="center"' in out

    def test_image_no_sizing_attrs_absent(self) -> None:
        out = emit((Paragraph((ImageNode(src="img.png", alt=""),),),))
        assert "ac:width" not in out
        assert "ac:height" not in out
        assert "ac:align" not in out


class TestTableEmitter:
    def _simple_table(self) -> Table:
        header = TableRow(cells=(
            TableCell(children=(TextNode("Name"),), is_header=True),
            TableCell(children=(TextNode("Value"),), is_header=True),
        ))
        row = TableRow(cells=(
            TableCell(children=(TextNode("foo"),)),
            TableCell(children=(TextNode("bar"),)),
        ))
        return Table(header=header, rows=(row,))

    def test_table_has_table_tag(self) -> None:
        out = emit((self._simple_table(),))
        assert "<table>" in out

    def test_table_header_uses_th(self) -> None:
        out = emit((self._simple_table(),))
        assert "<th>Name</th>" in out

    def test_table_body_uses_td(self) -> None:
        out = emit((self._simple_table(),))
        assert "<td>foo</td>" in out

    def test_table_alignment(self) -> None:
        header = TableRow(cells=(TableCell(children=(TextNode("N"),), is_header=True),))
        row = TableRow(cells=(TableCell(children=(TextNode("1"),), align="right"),))
        out = emit((Table(header=header, rows=(row,)),))
        assert 'text-align: right' in out


class TestFootnoteEmitter:
    def test_footnote_ref_emits_superscript_link(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import emit
        from mkdocs_to_confluence.ir import FootnoteRef, Paragraph, Section
        ref = FootnoteRef(label="1", number=1)
        para = Paragraph(children=[ref])
        section = Section(title="S", level=1, anchor="s", children=[para])
        html_out = emit([section])
        assert '<sup>' in html_out
        assert 'ac:anchor="fn-1"' in html_out
        assert '<![CDATA[1]]>' in html_out

    def test_footnote_block_emits_anchored_list(self) -> None:
        from mkdocs_to_confluence.emitter.xhtml import emit
        from mkdocs_to_confluence.ir import FootnoteBlock, FootnoteDef, Section, TextNode
        fn = FootnoteDef(label="1", number=1, children=[TextNode(text="My note.")])
        block = FootnoteBlock(items=[fn])
        section = Section(title="S", level=1, anchor="s", children=[block])
        html_out = emit([section])
        assert '<h2>Footnotes</h2>' in html_out
        assert '<ol>' in html_out
        assert 'ac:name="anchor"' in html_out
        assert 'fn-1' in html_out
        assert 'My note.' in html_out


# ── Inline HTML emitters ──────────────────────────────────────────────────────


class TestInlineHtmlEmitters:
    def test_line_break(self) -> None:
        from mkdocs_to_confluence.ir import LineBreakNode
        out = emit((Paragraph((TextNode("a"), LineBreakNode(), TextNode("b"))),))
        assert "<br />" in out

    def test_mark_emits_yellow_span(self) -> None:
        from mkdocs_to_confluence.ir import InlineHtmlNode
        out = emit((Paragraph((InlineHtmlNode(tag="mark", children=(TextNode("hi"),)),)),))
        assert '<span style="background-color: yellow;">hi</span>' in out

    def test_kbd_emits_code(self) -> None:
        from mkdocs_to_confluence.ir import InlineHtmlNode
        out = emit((Paragraph((InlineHtmlNode(tag="kbd", children=(TextNode("Ctrl+C"),)),)),))
        assert "<code>Ctrl+C</code>" in out

    def test_sub_passthrough(self) -> None:
        from mkdocs_to_confluence.ir import InlineHtmlNode
        out = emit((Paragraph((InlineHtmlNode(tag="sub", children=(TextNode("2"),)),)),))
        assert "<sub>2</sub>" in out

    def test_sup_passthrough(self) -> None:
        from mkdocs_to_confluence.ir import InlineHtmlNode
        out = emit((Paragraph((InlineHtmlNode(tag="sup", children=(TextNode("2"),)),)),))
        assert "<sup>2</sup>" in out

    def test_u_passthrough(self) -> None:
        from mkdocs_to_confluence.ir import InlineHtmlNode
        out = emit((Paragraph((InlineHtmlNode(tag="u", children=(TextNode("text"),)),)),))
        assert "<u>text</u>" in out

    def test_small_passthrough(self) -> None:
        from mkdocs_to_confluence.ir import InlineHtmlNode
        out = emit((Paragraph((InlineHtmlNode(tag="small", children=(TextNode("note"),)),)),))
        assert "<small>note</small>" in out

    def test_s_emits_strikethrough_span(self) -> None:
        from mkdocs_to_confluence.ir import InlineHtmlNode
        out = emit((Paragraph((InlineHtmlNode(tag="s", children=(TextNode("old"),)),)),))
        assert '<span style="text-decoration: line-through;">old</span>' in out

    def test_nested_inline_in_mark(self) -> None:
        from mkdocs_to_confluence.ir import BoldNode, InlineHtmlNode
        inner = BoldNode(children=(TextNode("bold"),))
        out = emit((Paragraph((InlineHtmlNode(tag="mark", children=(inner,)),)),))
        assert '<span style="background-color: yellow;"><strong>bold</strong></span>' in out

    def test_parse_and_emit_roundtrip(self) -> None:
        """End-to-end: parse inline HTML then emit to Confluence XHTML."""
        from mkdocs_to_confluence.parser import parse as md_parse
        nodes = md_parse("Use <kbd>Enter</kbd> and H<sub>2</sub>O and <mark>yellow</mark>.\n")
        out = emit(nodes)
        assert "<code>Enter</code>" in out
        assert "<sub>2</sub>" in out
        assert '<span style="background-color: yellow;">yellow</span>' in out


class TestMermaidEmitter:
    def test_attachment_centered(self) -> None:
        from mkdocs_to_confluence.ir.nodes import MermaidDiagram
        node = MermaidDiagram(source="graph TD; A-->B", attachment_name="diag.png")
        out = emit((node,))
        assert 'ac:align="center"' in out
        assert 'ri:filename="diag.png"' in out
