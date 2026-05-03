"""IR node definitions: the internal representation of a compiled MkDocs page.

All node types are frozen dataclasses — immutable, hashable, and structurally
equal.  Import everything you need directly from this package:

    from mkdocs_to_confluence.ir import (
        Document, PageMeta,
        Section, Paragraph, Text, CodeBlock, ...
    )
"""

from mkdocs_to_confluence.ir.document import Document, PageMeta, compute_sha
from mkdocs_to_confluence.ir.nodes import (
    # Material extension nodes
    Admonition,
    BlockQuote,
    BoldNode,
    # List nodes
    BulletList,
    CodeBlock,
    CodeInlineNode,
    ContentTabs,
    # Definition list
    DefinitionItem,
    DefinitionList,
    Expandable,
    # Footnote nodes
    FootnoteBlock,
    FootnoteDef,
    FootnoteRef,
    HorizontalRule,
    ImageNode,
    # Inline HTML nodes
    InlineHtmlNode,
    InsertNode,
    # Traversal utility
    IRNode,
    ItalicNode,
    LineBreakNode,
    LinkNode,
    ListItem,
    MermaidDiagram,
    OrderedList,
    Paragraph,
    RawHTML,
    # Block nodes
    Section,
    StrikethroughNode,
    SubscriptNode,
    SuperscriptNode,
    Tab,
    # Table nodes
    Table,
    TableCell,
    TableRow,
    # Inline nodes
    TextNode,
    # Graceful degradation
    UnsupportedBlock,
    walk,
)

__all__ = [
    # Document envelope
    "Document",
    "PageMeta",
    "compute_sha",
    # Base
    "IRNode",
    "walk",
    # Inline
    "TextNode",
    "BoldNode",
    "ItalicNode",
    "StrikethroughNode",
    "SuperscriptNode",
    "SubscriptNode",
    "CodeInlineNode",
    "LinkNode",
    "ImageNode",
    "LineBreakNode",
    "InlineHtmlNode",
    "InsertNode",
    # Block
    "Section",
    "Paragraph",
    "CodeBlock",
    "BlockQuote",
    "HorizontalRule",
    "RawHTML",
    # Lists
    "BulletList",
    "OrderedList",
    "ListItem",
    # Definition list
    "DefinitionList",
    "DefinitionItem",
    # Tables
    "Table",
    "TableRow",
    "TableCell",
    # Material
    "Admonition",
    "MermaidDiagram",
    "ContentTabs",
    "Tab",
    "Expandable",
    # Degradation
    "UnsupportedBlock",
    # Footnotes
    "FootnoteRef",
    "FootnoteDef",
    "FootnoteBlock",
]
