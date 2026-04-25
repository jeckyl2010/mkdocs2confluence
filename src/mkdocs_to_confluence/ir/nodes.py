"""All IR node types for the mkdocs-to-confluence compiler.

Design rules
------------
* Every node is a **frozen dataclass** — immutable, hashable, equality by value.
* Children sequences use ``tuple[IRNode, ...]``, never ``list``, to preserve
  immutability at the node level.
* Optional attributes have sensible defaults so callers only supply what they know.
* :class:`UnsupportedBlock` is the single catch-all for features the parser or
  emitter does not yet handle — it carries the original markdown so no content
  is ever silently lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generator

# ── Base ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IRNode:
    """Abstract base class for all IR nodes.

    Not meant to be instantiated directly — use a concrete subclass.
    """


# ── Inline nodes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextNode(IRNode):
    """A plain-text leaf; the most common building block of inline content."""

    text: str


@dataclass(frozen=True)
class BoldNode(IRNode):
    """Strongly-emphasised (bold) inline content."""

    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class ItalicNode(IRNode):
    """Emphasised (italic) inline content."""

    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class StrikethroughNode(IRNode):
    """Struck-through inline content (``~~text~~``)."""

    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class CodeInlineNode(IRNode):
    """An inline code span (`` `code` ``)."""

    code: str


@dataclass(frozen=True)
class LinkNode(IRNode):
    """A hyperlink, internal or external.

    ``is_internal`` is set by the link-resolution transform when the href
    references another page in the same MkDocs site.  The transform also
    rewrites ``href`` from a relative ``.md`` path to the Confluence page title.

    ``attachment_name`` is set by the assets transform when the href points to a
    local non-Markdown file.  It holds the collision-safe filename used in
    Confluence (e.g. ``assets_files_spec.pdf``).
    """

    href: str
    children: tuple[IRNode, ...]
    is_internal: bool = False
    attachment_name: str | None = None
    anchor: str | None = None  # fragment identifier for internal page links


@dataclass(frozen=True)
class LineBreakNode(IRNode):
    """A hard line break (``<br>``, ``<br/>``, or ``<br />``)."""


@dataclass(frozen=True)
class InlineHtmlNode(IRNode):
    """An inline HTML element mapped to a Confluence-safe equivalent.

    Supported tags: ``mark``, ``kbd``, ``sub``, ``sup``, ``u``, ``s``,
    ``del``, ``small``.  The emitter maps each to the appropriate
    Confluence storage-format construct.
    """

    tag: str
    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class ImageNode(IRNode):
    """An image reference.

    The images transform collects all ``ImageNode`` instances and registers
    their ``src`` on ``Document.attachments`` so the publisher can upload them.

    ``attachment_name`` is the collision-safe filename used in Confluence
    (e.g. ``assets_images_logo.png``).  Set by the assets transform.
    """

    src: str
    alt: str
    title: str | None = None
    attachment_name: str | None = None


# ── Block nodes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Section(IRNode):
    """A document section: a heading and all block content that follows it.

    Sections nest naturally — an H2 ``Section`` is a child of the H1 ``Section``
    that precedes it.  This tree shape maps cleanly onto Confluence's
    parent-child page hierarchy for deep nesting, and onto heading macros for
    shallow nesting within a single page.

    Attributes:
        level:    Heading level 1–6.
        anchor:   The auto-generated fragment identifier (e.g. ``"my-section"``).
        title:    Inline nodes that form the heading text.
        children: Block nodes that are the body of this section.
    """

    level: int
    anchor: str
    title: tuple[IRNode, ...]
    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class Paragraph(IRNode):
    """A block of inline content separated by blank lines."""

    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class CodeBlock(IRNode):
    """A fenced code block.

    Attributes:
        code:            The literal code text.
        language:        Syntax identifier (e.g. ``"python"``), or ``None``.
        title:           Optional filename/title shown above the block.
        linenums:        Whether line numbers are enabled.
        linenums_start:  First line number (default 1); only meaningful when
                         ``linenums`` is ``True``.
        highlight_lines: 1-based line numbers that should be highlighted.
    """

    code: str
    language: str | None = None
    title: str | None = None
    linenums: bool = False
    linenums_start: int = 1
    highlight_lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class BlockQuote(IRNode):
    """A block quotation (``> ...``)."""

    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class HorizontalRule(IRNode):
    """A thematic break (``---``)."""


@dataclass(frozen=True)
class RawHTML(IRNode):
    """Verbatim HTML that the parser chose not to interpret.

    The emitter wraps this in a Confluence HTML macro or a ``<![CDATA[...]]>``
    block.  Use sparingly — prefer semantic nodes where possible.
    """

    html: str


# ── List nodes ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ListItem(IRNode):
    """A single item in a ``BulletList`` or ``OrderedList``.

    ``task`` is ``None`` for ordinary items, ``True`` for a checked task, and
    ``False`` for an unchecked task (``- [x]`` / ``- [ ]``).
    """

    children: tuple[IRNode, ...]
    task: bool | None = None


@dataclass(frozen=True)
class BulletList(IRNode):
    """An unordered list."""

    items: tuple[ListItem, ...]


@dataclass(frozen=True)
class OrderedList(IRNode):
    """An ordered (numbered) list.

    ``start`` is the value of the first list item (usually 1).
    """

    items: tuple[ListItem, ...]
    start: int = 1


# ── Table nodes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TableCell(IRNode):
    """A single table cell.

    Attributes:
        children:  Inline content of the cell.
        align:     ``"left"``, ``"center"``, ``"right"``, or ``None``.
        is_header: ``True`` for cells in the header row (``<th>``).
    """

    children: tuple[IRNode, ...]
    align: str | None = None
    is_header: bool = False


@dataclass(frozen=True)
class TableRow(IRNode):
    """A row of :class:`TableCell` nodes."""

    cells: tuple[TableCell, ...]


@dataclass(frozen=True)
class Table(IRNode):
    """A Markdown table.

    ``header`` is always the first row.  ``rows`` contains the body rows.
    """

    header: TableRow
    rows: tuple[TableRow, ...]


# ── Material extension nodes ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Admonition(IRNode):
    """A Material for MkDocs admonition block (``!!! type "Title"``).

    Attributes:
        kind:        One of the MkDocs admonition types: ``"note"``,
                     ``"warning"``, ``"tip"``, ``"danger"``, ``"info"``,
                     ``"success"``, ``"failure"``, ``"bug"``, ``"example"``,
                     ``"quote"``, ``"abstract"``.
        title:       Custom title override, or ``None`` to use the default
                     title for ``kind``.
        children:    Block nodes that form the admonition body.
        collapsible: ``True`` when opened with ``???`` (collapsed by default)
                     or ``???+`` (expanded by default).
    """

    kind: str
    title: str | None
    children: tuple[IRNode, ...]
    collapsible: bool = False


@dataclass(frozen=True)
class MermaidDiagram(IRNode):
    """A Mermaid diagram (`` ```mermaid `` fenced block).

    ``source`` is the raw Mermaid DSL.  When ``attachment_name`` is set the
    emitter renders an ``<ac:image>`` referencing the uploaded PNG; otherwise
    it falls back to a code block showing the raw source.
    """

    source: str
    attachment_name: str | None = None
    local_path: Path | None = None  # set by mermaid transform; used by preview renderer


@dataclass(frozen=True)
class Tab(IRNode):
    """A single tab inside a :class:`ContentTabs` group."""

    label: str
    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class ContentTabs(IRNode):
    """Material for MkDocs content tabs (``=== "Label"`` syntax).

    The emitter maps these to a Confluence Tabs macro (if the marketplace
    plugin is installed) or falls back to a series of :class:`Expandable`
    blocks.
    """

    tabs: tuple[Tab, ...]


@dataclass(frozen=True)
class Expandable(IRNode):
    """A collapsible ``<details>``/``<summary>`` block.

    Maps to the native Confluence ``expand`` macro.
    """

    title: str
    children: tuple[IRNode, ...]


# ── Document metadata ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrontMatter(IRNode):
    """YAML front matter extracted from the top of a markdown file.

    The emitter renders this as a Confluence **Page Properties** (``details``)
    macro so the metadata is queryable via the Page Properties Report macro.

    Attributes:
        title:      The page title (``title:`` field).  Used as the Confluence
                    page title on publish; also shown as a row in the table.
        subtitle:   Optional subtitle rendered as an italic lead paragraph
                    *before* the properties table.
        properties: Ordered ``(display_name, value)`` pairs for the table.
                    Field-order and display names are normalised by the
                    front matter extractor.
        labels:     Confluence page labels derived from the ``tags:`` field.
                    Applied via the REST API at publish time (not in XHTML).
        source_url: Optional URL to the source file in the version-control
                    repository.  Rendered as a clickable link row ("Source")
                    at the bottom of the Page Properties table.
        site_url:   Optional URL to the rendered page on the published MkDocs
                    site.  Rendered as a "Published Page" row in the table.
    """

    title: str | None
    subtitle: str | None
    properties: tuple[tuple[str, str], ...]
    labels: tuple[str, ...]
    source_url: str | None = None
    site_url: str | None = None


# ── Footnotes ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FootnoteRef(IRNode):
    """An inline footnote reference, e.g. ``[^1]``.

    Rendered as a superscript anchor-link pointing to the footnote definition.
    """

    label: str   # raw label as written, e.g. "1" or "note"
    number: int  # 1-based display number


@dataclass(frozen=True)
class FootnoteDef(IRNode):
    """A single footnote definition."""

    label: str
    number: int
    children: tuple[IRNode, ...]


@dataclass(frozen=True)
class FootnoteBlock(IRNode):
    """The collected footnote definitions appended at the end of a page."""

    items: tuple[FootnoteDef, ...]


# ── Graceful degradation ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnsupportedBlock(IRNode):
    """A block the parser or emitter does not yet know how to handle.

    The emitter renders this as a clearly-visible warning panel (e.g. a
    Confluence ``warning`` macro wrapping a code block) so that authors
    can see what was not converted rather than silently losing content.

    Attributes:
        raw:    The original markdown source of the block.
        reason: Human-readable explanation of why it is unsupported.
    """

    raw: str
    reason: str


# ── Traversal utility ─────────────────────────────────────────────────────────


def walk(node: IRNode) -> Generator[IRNode, None, None]:
    """Yield *node* and every descendant in depth-first pre-order.

    Works with any :class:`IRNode` subclass regardless of how its children are
    stored.  Children are discovered by inspecting all ``tuple[IRNode, ...]``
    fields via the dataclass field metadata.

    Example::

        images = [n for n in walk(document.body) if isinstance(n, ImageNode)]
    """
    import dataclasses

    yield node
    for f in dataclasses.fields(node):
        value = getattr(node, f.name)
        if isinstance(value, IRNode):
            yield from walk(value)
        elif isinstance(value, tuple):
            for item in value:
                if isinstance(item, IRNode):
                    yield from walk(item)
