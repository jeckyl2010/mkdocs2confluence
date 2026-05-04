"""Abbreviation expansion: IR tree transform.

Collects ``*[ABBR]: definition`` pairs (extracted by
:mod:`mkdocs_to_confluence.preprocess.abbrevs`) and walks the IR tree to:

1. **Annotate** the first occurrence of each abbreviation in *safe* body nodes —
   paragraphs, list items, table body cells, blockquotes — by inserting an
   inline Confluence ``footnote`` macro immediately after the term.  Confluence
   renders this as a superscript number and collects all definitions at the
   bottom of the page.

2. **Skip** structural/title nodes where expansion would look odd:
   section headings, table header cells, admonition/panel titles, code spans,
   and link text.

3. **Append a Glossary section** at the end of the page for any abbreviation
   that was detected in the page text but could not be footnoted because it
   only appeared in skipped contexts (headings, table headers, etc.).

Entry point
-----------
:func:`apply_abbreviations` — call after :func:`parse` and before
:func:`emit`.
"""

from __future__ import annotations

import re
from dataclasses import replace

from mkdocs_to_confluence.ir.nodes import (
    AbbrevFootnoteNode,
    Admonition,
    BlockQuote,
    BoldNode,
    BulletList,
    ContentTabs,
    Expandable,
    HorizontalRule,
    IRNode,
    ItalicNode,
    LinkNode,
    ListItem,
    OrderedList,
    Paragraph,
    Section,
    StrikethroughNode,
    Tab,
    Table,
    TableCell,
    TableRow,
    TextNode,
)

# ── Internal state ────────────────────────────────────────────────────────────


class _State:
    """Mutable transform state threaded through the recursive walk."""

    def __init__(self, abbrevs: dict[str, str]) -> None:
        self.abbrevs = abbrevs
        self.expanded: set[str] = set()
        # Pre-compile word-boundary patterns once.
        self._patterns: dict[str, re.Pattern[str]] = {
            abbr: re.compile(r"\b" + re.escape(abbr) + r"\b")
            for abbr in abbrevs
        }

    def expand_to_nodes(self, text: str) -> tuple[IRNode, ...]:
        """Split *text* around the first unexpanded abbreviation.

        Returns a mix of :class:`TextNode` and :class:`AbbrevFootnoteNode`.
        Each abbreviation is footnoted at most once per page.
        """
        best: tuple[int, int, str] | None = None
        for abbr in self.abbrevs:
            if abbr in self.expanded:
                continue
            m = self._patterns[abbr].search(text)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), m.end(), abbr)

        if best is None:
            return (TextNode(text),) if text else ()

        start, end, abbr = best
        self.expanded.add(abbr)
        nodes: list[IRNode] = []
        if text[:start]:
            nodes.append(TextNode(text[:start]))
        nodes.append(AbbrevFootnoteNode(abbr=abbr, definition=self.abbrevs[abbr]))
        nodes.extend(self.expand_to_nodes(text[end:]))
        return tuple(nodes)


# ── Block-level transform ─────────────────────────────────────────────────────


def _transform_block(node: IRNode, state: _State) -> IRNode:
    """Return *node* with abbreviations expanded in safe descendant text."""
    if isinstance(node, Paragraph):
        return replace(node, children=_inline(node.children, state, safe=True))

    if isinstance(node, Section):
        # Heading text is unsafe; body children recurse as blocks.
        new_title = _inline(node.title, state, safe=False)
        new_children = tuple(_transform_block(c, state) for c in node.children)
        return replace(node, title=new_title, children=new_children)

    if isinstance(node, BulletList):
        return replace(node, items=tuple(_transform_list_item(i, state) for i in node.items))

    if isinstance(node, OrderedList):
        return replace(node, items=tuple(_transform_list_item(i, state) for i in node.items))

    if isinstance(node, BlockQuote):
        return replace(node, children=tuple(_transform_block(c, state) for c in node.children))

    if isinstance(node, Table):
        new_header = _transform_table_row(node.header, state)
        new_rows = tuple(_transform_table_row(r, state) for r in node.rows)
        return replace(node, header=new_header, rows=new_rows)

    if isinstance(node, Admonition):
        # ``title`` is a plain ``str`` — skip it (unsafe context).
        new_children = tuple(_transform_block(c, state) for c in node.children)
        return replace(node, children=new_children)

    if isinstance(node, ContentTabs):
        return replace(node, tabs=tuple(_transform_tab(t, state) for t in node.tabs))

    if isinstance(node, Expandable):
        # ``title`` is a plain ``str`` — skip it.
        new_children = tuple(_transform_block(c, state) for c in node.children)
        return replace(node, children=new_children)

    # Leaf blocks (CodeBlock, MermaidDiagram, HorizontalRule, RawHTML,
    # UnsupportedBlock, ImageNode) — never expand inside these.
    return node


def _transform_list_item(item: ListItem, state: _State) -> ListItem:
    new_children = tuple(_transform_block(c, state) for c in item.children)
    return replace(item, children=new_children)


def _transform_tab(tab: Tab, state: _State) -> Tab:
    new_children = tuple(_transform_block(c, state) for c in tab.children)
    return replace(tab, children=new_children)


def _transform_table_row(row: TableRow, state: _State) -> TableRow:
    new_cells = tuple(_transform_table_cell(c, state) for c in row.cells)
    return replace(row, cells=new_cells)


def _transform_table_cell(cell: TableCell, state: _State) -> TableCell:
    safe = not cell.is_header
    return replace(cell, children=_inline(cell.children, state, safe=safe))


# ── Inline-level transform ────────────────────────────────────────────────────


def _inline(nodes: tuple[IRNode, ...], state: _State, safe: bool) -> tuple[IRNode, ...]:
    result: list[IRNode] = []
    for n in nodes:
        result.extend(_transform_inline(n, state, safe))
    return tuple(result)


def _transform_inline(node: IRNode, state: _State, safe: bool) -> tuple[IRNode, ...]:
    if isinstance(node, TextNode):
        return state.expand_to_nodes(node.text) if safe else (node,)

    if isinstance(node, (BoldNode, ItalicNode, StrikethroughNode)):
        return (replace(node, children=_inline(node.children, state, safe)),)

    if isinstance(node, LinkNode):
        # Expanding inside link text could break the anchor label — skip.
        return (replace(node, children=_inline(node.children, state, safe=False)),)

    # CodeInlineNode, ImageNode — never expand.
    return (node,)


# ── Glossary builder ──────────────────────────────────────────────────────────


def _find_mentioned(text: str, abbrevs: dict[str, str]) -> set[str]:
    """Return abbreviations that appear as whole words anywhere in *text*."""
    return {
        abbr
        for abbr in abbrevs
        if re.search(r"\b" + re.escape(abbr) + r"\b", text)
    }


def _build_glossary_section(terms: dict[str, str]) -> tuple[IRNode, ...]:
    """Return an HR + h6 ``Section`` listing abbreviations that could not be footnoted."""
    items = tuple(
        ListItem(children=(Paragraph(children=(TextNode(f"{abbr} — {defn}"),)),))
        for abbr, defn in sorted(terms.items())
    )
    section = Section(
        level=6,
        anchor="glossary",
        title=(TextNode("Glossary"),),
        children=(BulletList(items=items),),
    )
    return (HorizontalRule(), section)


# ── Public API ────────────────────────────────────────────────────────────────


def apply_abbreviations(
    nodes: tuple[IRNode, ...],
    abbrevs: dict[str, str],
    *,
    page_text: str = "",
) -> tuple[IRNode, ...]:
    """Expand abbreviations in IR *nodes* and return the modified tree.

    Args:
        nodes:      Top-level IR nodes returned by :func:`parse`.
        abbrevs:    ``{abbreviation: definition}`` mapping, typically from
                    :func:`~mkdocs_to_confluence.preprocess.abbrevs.extract_abbreviations`.
        page_text:  The preprocessed page text (after stripping abbreviation
                    definition lines) used to detect which abbreviations are
                    actually present on the page.  Used to determine which
                    abbreviations need a glossary entry.

    Returns:
        Modified node tuple.  Abbreviations in body text are replaced with an
        :class:`~mkdocs_to_confluence.ir.nodes.AbbrevFootnoteNode` on first
        occurrence.  A ``Glossary`` section is appended only for abbreviations
        that were detected in *page_text* but never footnoted (e.g. they only
        appeared in headings or table headers).
    """
    if not abbrevs:
        return nodes

    state = _State(abbrevs)
    transformed = tuple(_transform_block(n, state) for n in nodes)

    mentioned = _find_mentioned(page_text, abbrevs)
    # Only add a glossary entry for abbreviations that were never footnoted.
    glossary_needed = {
        abbr: abbrevs[abbr]
        for abbr in mentioned
        if abbr not in state.expanded
    }

    if glossary_needed:
        transformed = transformed + _build_glossary_section(glossary_needed)

    return transformed

