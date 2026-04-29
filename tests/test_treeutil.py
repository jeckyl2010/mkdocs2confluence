"""Tests for ir.treeutil.replace_nodes."""

from mkdocs_to_confluence.ir.nodes import (
    Paragraph,
    Section,
    TextNode,
    BoldNode,
)
from mkdocs_to_confluence.ir.treeutil import replace_nodes


def _text(t: str) -> TextNode:
    return TextNode(text=t)


def _para(*children):
    return Paragraph(children=tuple(children))


def _section(*children):
    return Section(level=1, anchor="s", title="T", children=tuple(children))


class TestReplaceNodes:
    def test_no_replacements_returns_same_tuple(self):
        nodes = (_para(_text("a")),)
        result = replace_nodes(nodes, {})
        assert result == nodes

    def test_top_level_node_replaced(self):
        original = _para(_text("old"))
        new = _para(_text("new"))
        result = replace_nodes((original,), {id(original): new})
        assert result == (new,)
        assert result[0] is new

    def test_nested_child_replaced(self):
        child = _text("old")
        parent = _para(child)
        new_child = _text("new")
        result = replace_nodes((parent,), {id(child): new_child})
        assert result[0].children == (new_child,)

    def test_unreferenced_nodes_unchanged(self):
        a = _para(_text("a"))
        b = _para(_text("b"))
        new_b = _para(_text("B"))
        result = replace_nodes((a, b), {id(b): new_b})
        assert result[0] == a
        assert result[1] is new_b

    def test_deeply_nested_replacement(self):
        leaf = _text("deep")
        inner = _para(leaf)
        outer = _section(inner)
        new_leaf = _text("replaced")
        result = replace_nodes((outer,), {id(leaf): new_leaf})
        assert result[0].children[0].children[0].text == "replaced"

    def test_multiple_replacements_in_one_pass(self):
        t1 = _text("one")
        t2 = _text("two")
        para = _para(t1, t2)
        r1 = _text("ONE")
        r2 = _text("TWO")
        result = replace_nodes((para,), {id(t1): r1, id(t2): r2})
        assert result[0].children == (r1, r2)

    def test_empty_nodes_tuple(self):
        assert replace_nodes((), {}) == ()

    def test_bold_child_replaced(self):
        child = BoldNode(children=(_text("bold"),))
        para = _para(child)
        new_child = BoldNode(children=(_text("BOLD"),))
        result = replace_nodes((para,), {id(child): new_child})
        assert result[0].children[0].children[0].text == "BOLD"
