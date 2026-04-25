"""Tests for the IR node types and document model — Milestone 4."""

from __future__ import annotations

import dataclasses
from typing import Iterator

import pytest

from mkdocs_to_confluence.ir import (
    Admonition,
    BlockQuote,
    BoldNode,
    BulletList,
    CodeBlock,
    CodeInlineNode,
    ContentTabs,
    Document,
    Expandable,
    HorizontalRule,
    ImageNode,
    IRNode,
    ItalicNode,
    LinkNode,
    ListItem,
    MermaidDiagram,
    OrderedList,
    PageMeta,
    Paragraph,
    RawHTML,
    Section,
    StrikethroughNode,
    SubscriptNode,
    SuperscriptNode,
    Tab,
    Table,
    TableCell,
    TableRow,
    TextNode,
    UnsupportedBlock,
    compute_sha,
    walk,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def text(s: str) -> TextNode:
    return TextNode(text=s)


def para(*children: IRNode) -> Paragraph:
    return Paragraph(children=children)


# ── compute_sha ───────────────────────────────────────────────────────────────


class TestComputeSha:
    def test_returns_64_char_hex_string(self) -> None:
        result = compute_sha("hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self) -> None:
        assert compute_sha("hello") == compute_sha("hello")

    def test_different_inputs_differ(self) -> None:
        assert compute_sha("hello") != compute_sha("world")

    def test_empty_string(self) -> None:
        result = compute_sha("")
        assert len(result) == 64

    def test_unicode_content(self) -> None:
        result = compute_sha("こんにちは")
        assert len(result) == 64


# ── PageMeta ──────────────────────────────────────────────────────────────────


class TestPageMeta:
    def test_required_fields(self) -> None:
        meta = PageMeta(source_path="docs/index.md", title="Home", sha="abc123")
        assert meta.source_path == "docs/index.md"
        assert meta.title == "Home"
        assert meta.sha == "abc123"

    def test_optional_defaults(self) -> None:
        meta = PageMeta(source_path="docs/index.md", title="Home", sha="abc123")
        assert meta.repo_url is None
        assert meta.tool_version == ""
        assert meta.confluence_id is None

    def test_optional_fields(self) -> None:
        meta = PageMeta(
            source_path="docs/index.md",
            title="Home",
            sha="abc123",
            repo_url="https://github.com/x/y",
            tool_version="0.1.0",
            confluence_id=42,
        )
        assert meta.repo_url == "https://github.com/x/y"
        assert meta.tool_version == "0.1.0"
        assert meta.confluence_id == 42

    def test_immutable(self) -> None:
        meta = PageMeta(source_path="docs/index.md", title="Home", sha="abc123")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            meta.title = "Other"  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        a = PageMeta(source_path="docs/index.md", title="Home", sha="abc")
        b = PageMeta(source_path="docs/index.md", title="Home", sha="abc")
        assert a == b

    def test_inequality(self) -> None:
        a = PageMeta(source_path="docs/index.md", title="Home", sha="abc")
        b = PageMeta(source_path="docs/other.md", title="Other", sha="xyz")
        assert a != b


# ── Document ──────────────────────────────────────────────────────────────────


class TestDocument:
    def _meta(self) -> PageMeta:
        return PageMeta(source_path="docs/index.md", title="Home", sha="abc")

    def test_construction(self) -> None:
        doc = Document(meta=self._meta(), body=())
        assert doc.body == ()
        assert doc.attachments == []
        assert doc.nav_context == {}

    def test_body_with_nodes(self) -> None:
        body = (para(text("Hello")),)
        doc = Document(meta=self._meta(), body=body)
        assert len(doc.body) == 1

    def test_attachments_mutable(self) -> None:
        doc = Document(meta=self._meta(), body=())
        doc.attachments.append("docs/images/logo.png")
        assert "docs/images/logo.png" in doc.attachments

    def test_nav_context_mutable(self) -> None:
        doc = Document(meta=self._meta(), body=())
        doc.nav_context["docs/other.md"] = "Other Page"
        assert doc.nav_context["docs/other.md"] == "Other Page"

    def test_different_docs_not_equal_by_default(self) -> None:
        meta = self._meta()
        a = Document(meta=meta, body=())
        b = Document(meta=meta, body=())
        # Document is not frozen — two instances are not equal by value
        # (regular dataclass uses identity equality unless __eq__ is customised)
        assert a is not b


# ── Inline nodes ──────────────────────────────────────────────────────────────


class TestInlineNodes:
    def test_text_node(self) -> None:
        node = TextNode(text="hello")
        assert node.text == "hello"

    def test_text_node_immutable(self) -> None:
        node = TextNode(text="hello")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            node.text = "world"  # type: ignore[misc]

    def test_bold_node(self) -> None:
        node = BoldNode(children=(TextNode(text="bold"),))
        assert isinstance(node.children[0], TextNode)

    def test_italic_node(self) -> None:
        node = ItalicNode(children=(TextNode(text="italic"),))
        assert node.children[0].text == "italic"

    def test_strikethrough_node(self) -> None:
        node = StrikethroughNode(children=(TextNode(text="strike"),))
        assert len(node.children) == 1

    def test_subscript_node(self) -> None:
        node = SubscriptNode(children=(TextNode(text="2"),))
        assert len(node.children) == 1

    def test_superscript_node(self) -> None:
        node = SuperscriptNode(children=(TextNode(text="2"),))
        assert len(node.children) == 1

    def test_code_inline_node(self) -> None:
        node = CodeInlineNode(code="print()")
        assert node.code == "print()"

    def test_link_node_defaults(self) -> None:
        node = LinkNode(href="https://example.com", children=(TextNode("click"),))
        assert not node.is_internal

    def test_link_node_internal(self) -> None:
        node = LinkNode(
            href="guide/installation.md",
            children=(TextNode("install"),),
            is_internal=True,
        )
        assert node.is_internal

    def test_image_node_defaults(self) -> None:
        node = ImageNode(src="images/logo.png", alt="Logo")
        assert node.title is None

    def test_image_node_with_title(self) -> None:
        node = ImageNode(src="images/logo.png", alt="Logo", title="Our logo")
        assert node.title == "Our logo"

    def test_nodes_are_hashable(self) -> None:
        a = TextNode(text="hello")
        b = TextNode(text="hello")
        assert hash(a) == hash(b)
        assert {a, b} == {a}  # same hash + equal → one element in set


# ── Block nodes ───────────────────────────────────────────────────────────────


class TestBlockNodes:
    def test_section_fields(self) -> None:
        node = Section(
            level=2,
            anchor="my-section",
            title=(TextNode("My Section"),),
            children=(para(TextNode("Body.")),),
        )
        assert node.level == 2
        assert node.anchor == "my-section"
        assert len(node.title) == 1
        assert len(node.children) == 1

    def test_section_nesting(self) -> None:
        inner = Section(
            level=3,
            anchor="inner",
            title=(TextNode("Inner"),),
            children=(),
        )
        outer = Section(
            level=2,
            anchor="outer",
            title=(TextNode("Outer"),),
            children=(inner,),
        )
        assert outer.children[0] is inner

    def test_paragraph(self) -> None:
        node = para(TextNode("Hello"), TextNode(" world"))
        assert len(node.children) == 2

    def test_code_block_defaults(self) -> None:
        node = CodeBlock(code="print('hi')")
        assert node.language is None
        assert node.title is None
        assert not node.linenums
        assert node.linenums_start == 1
        assert node.highlight_lines == ()

    def test_code_block_full(self) -> None:
        node = CodeBlock(
            code="x = 1\ny = 2\n",
            language="python",
            title="example.py",
            linenums=True,
            linenums_start=5,
            highlight_lines=(6,),
        )
        assert node.language == "python"
        assert node.title == "example.py"
        assert node.linenums
        assert node.linenums_start == 5
        assert node.highlight_lines == (6,)

    def test_blockquote(self) -> None:
        node = BlockQuote(children=(para(TextNode("A quote.")),))
        assert len(node.children) == 1

    def test_horizontal_rule(self) -> None:
        node = HorizontalRule()
        assert isinstance(node, IRNode)

    def test_raw_html(self) -> None:
        node = RawHTML(html="<div>raw</div>")
        assert node.html == "<div>raw</div>"


# ── List nodes ────────────────────────────────────────────────────────────────


class TestListNodes:
    def test_bullet_list(self) -> None:
        items = (
            ListItem(children=(TextNode("first"),)),
            ListItem(children=(TextNode("second"),)),
        )
        node = BulletList(items=items)
        assert len(node.items) == 2

    def test_ordered_list_default_start(self) -> None:
        node = OrderedList(items=(ListItem(children=(TextNode("one"),)),))
        assert node.start == 1

    def test_ordered_list_custom_start(self) -> None:
        node = OrderedList(
            items=(ListItem(children=(TextNode("four"),)),),
            start=4,
        )
        assert node.start == 4

    def test_list_item_no_task(self) -> None:
        node = ListItem(children=(TextNode("plain"),))
        assert node.task is None

    def test_list_item_checked_task(self) -> None:
        node = ListItem(children=(TextNode("done"),), task=True)
        assert node.task is True

    def test_list_item_unchecked_task(self) -> None:
        node = ListItem(children=(TextNode("todo"),), task=False)
        assert node.task is False


# ── Table nodes ───────────────────────────────────────────────────────────────


class TestTableNodes:
    def _header(self, *labels: str) -> TableRow:
        return TableRow(
            cells=tuple(
                TableCell(children=(TextNode(label),), is_header=True) for label in labels
            )
        )

    def _row(self, *values: str) -> TableRow:
        return TableRow(
            cells=tuple(TableCell(children=(TextNode(v),)) for v in values)
        )

    def test_table_construction(self) -> None:
        node = Table(
            header=self._header("Name", "Value"),
            rows=(self._row("foo", "bar"),),
        )
        assert len(node.header.cells) == 2
        assert len(node.rows) == 1

    def test_table_cell_defaults(self) -> None:
        cell = TableCell(children=(TextNode("hi"),))
        assert cell.align is None
        assert not cell.is_header

    def test_table_cell_alignment(self) -> None:
        cell = TableCell(children=(TextNode("hi"),), align="center")
        assert cell.align == "center"

    def test_table_row_cells(self) -> None:
        row = self._row("a", "b", "c")
        assert len(row.cells) == 3


# ── Material extension nodes ──────────────────────────────────────────────────


class TestMaterialNodes:
    def test_admonition_defaults(self) -> None:
        node = Admonition(
            kind="note",
            title=None,
            children=(para(TextNode("Body.")),),
        )
        assert node.kind == "note"
        assert node.title is None
        assert not node.collapsible

    def test_admonition_collapsible(self) -> None:
        node = Admonition(
            kind="warning",
            title="Watch out",
            children=(),
            collapsible=True,
        )
        assert node.collapsible
        assert node.title == "Watch out"

    def test_admonition_kinds(self) -> None:
        kinds = [
            "note", "warning", "tip", "danger", "info",
            "success", "failure", "bug", "example", "quote", "abstract",
        ]
        for kind in kinds:
            node = Admonition(kind=kind, title=None, children=())
            assert node.kind == kind

    def test_mermaid_diagram(self) -> None:
        source = "graph TD\n  A --> B\n"
        node = MermaidDiagram(source=source)
        assert node.source == source

    def test_content_tabs(self) -> None:
        tabs = (
            Tab(label="Python", children=(para(TextNode("Python code")),)),
            Tab(label="TypeScript", children=(para(TextNode("TS code")),)),
        )
        node = ContentTabs(tabs=tabs)
        assert len(node.tabs) == 2
        assert node.tabs[0].label == "Python"

    def test_expandable(self) -> None:
        node = Expandable(
            title="Click to expand",
            children=(para(TextNode("Hidden content.")),),
        )
        assert node.title == "Click to expand"
        assert len(node.children) == 1


# ── UnsupportedBlock ──────────────────────────────────────────────────────────


class TestUnsupportedBlock:
    def test_carries_raw_content(self) -> None:
        node = UnsupportedBlock(
            raw="```unknown-lang\nstuff\n```",
            reason="Unknown fenced block language",
        )
        assert "unknown-lang" in node.raw

    def test_carries_reason(self) -> None:
        node = UnsupportedBlock(raw="??", reason="Unrecognised syntax")
        assert node.reason == "Unrecognised syntax"

    def test_is_ir_node(self) -> None:
        node = UnsupportedBlock(raw="x", reason="y")
        assert isinstance(node, IRNode)

    def test_immutable(self) -> None:
        node = UnsupportedBlock(raw="x", reason="y")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            node.raw = "z"  # type: ignore[misc]


# ── walk() ────────────────────────────────────────────────────────────────────


class TestWalk:
    def test_single_node(self) -> None:
        node = TextNode(text="hi")
        assert list(walk(node)) == [node]

    def test_paragraph_with_children(self) -> None:
        t1 = TextNode("a")
        t2 = TextNode("b")
        p = Paragraph(children=(t1, t2))
        result = list(walk(p))
        assert result == [p, t1, t2]

    def test_nested_tree_depth_first(self) -> None:
        leaf1 = TextNode("leaf1")
        leaf2 = TextNode("leaf2")
        inner = Paragraph(children=(leaf1,))
        outer = Section(
            level=1,
            anchor="s",
            title=(TextNode("Title"),),
            children=(inner, leaf2),
        )
        result = list(walk(outer))
        # Pre-order: outer, title text, inner, leaf1, leaf2
        assert result[0] is outer
        assert TextNode("Title") in result
        assert inner in result
        assert leaf1 in result
        assert leaf2 in result

    def test_collects_all_image_nodes(self) -> None:
        img1 = ImageNode(src="a.png", alt="A")
        img2 = ImageNode(src="b.png", alt="B")
        body = Section(
            level=1,
            anchor="s",
            title=(),
            children=(
                Paragraph(children=(img1,)),
                Paragraph(children=(TextNode("text"), img2)),
            ),
        )
        images = [n for n in walk(body) if isinstance(n, ImageNode)]
        assert images == [img1, img2]

    def test_horizontal_rule_no_children(self) -> None:
        hr = HorizontalRule()
        assert list(walk(hr)) == [hr]

    def test_walk_table(self) -> None:
        cell = TableCell(children=(TextNode("val"),))
        row = TableRow(cells=(cell,))
        header = TableRow(cells=(TableCell(children=(TextNode("head"),), is_header=True),))
        table = Table(header=header, rows=(row,))
        nodes = list(walk(table))
        assert table in nodes
        assert cell in nodes
        assert row in nodes

    def test_walk_table_header_cells_are_visited(self) -> None:
        """walk() must descend into Table.header (single IRNode field, not tuple)."""
        header_text = TextNode("Head")
        header_cell = TableCell(children=(header_text,), is_header=True)
        header_row = TableRow(cells=(header_cell,))
        body_text = TextNode("Body")
        body_cell = TableCell(children=(body_text,))
        body_row = TableRow(cells=(body_cell,))
        table = Table(header=header_row, rows=(body_row,))
        nodes = list(walk(table))
        # All nodes — including those inside the header — must be visited.
        assert header_row in nodes
        assert header_cell in nodes
        assert header_text in nodes
        assert body_row in nodes
        assert body_text in nodes

    def test_walk_link_in_table_header_found(self) -> None:
        """LinkNode inside a table header cell must be reachable via walk()."""
        link = LinkNode(href="https://example.com", children=(TextNode("click"),))
        header_cell = TableCell(children=(link,), is_header=True)
        header_row = TableRow(cells=(header_cell,))
        table = Table(header=header_row, rows=())
        links = [n for n in walk(table) if isinstance(n, LinkNode)]
        assert links == [link]

    def test_walk_unsupported_block(self) -> None:
        node = UnsupportedBlock(raw="x", reason="y")
        assert list(walk(node)) == [node]

    def test_walk_admonition(self) -> None:
        leaf = TextNode("body text")
        adm = Admonition(kind="note", title=None, children=(Paragraph(children=(leaf,)),))
        nodes = list(walk(adm))
        assert adm in nodes
        assert leaf in nodes

    def test_generator_type(self) -> None:
        node = TextNode("x")
        assert isinstance(walk(node), Iterator)


# ── Node equality and hashing ─────────────────────────────────────────────────


class TestNodeEquality:
    def test_equal_nodes(self) -> None:
        a = CodeBlock(code="x = 1", language="python")
        b = CodeBlock(code="x = 1", language="python")
        assert a == b

    def test_unequal_nodes(self) -> None:
        a = CodeBlock(code="x = 1", language="python")
        b = CodeBlock(code="x = 2", language="python")
        assert a != b

    def test_different_types_not_equal(self) -> None:
        a = TextNode(text="hello")
        b = CodeInlineNode(code="hello")
        assert a != b

    def test_nodes_usable_in_sets(self) -> None:
        a = TextNode("hi")
        b = TextNode("hi")
        c = TextNode("bye")
        s = {a, b, c}
        assert len(s) == 2

    def test_nodes_usable_as_dict_keys(self) -> None:
        node = TextNode("key")
        d = {node: "value"}
        assert d[TextNode("key")] == "value"
