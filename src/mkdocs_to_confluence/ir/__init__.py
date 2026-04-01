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
    # Inline nodes
    TextNode,
    BoldNode,
    ItalicNode,
    StrikethroughNode,
    CodeInlineNode,
    LinkNode,
    ImageNode,
    # Block nodes
    Section,
    Paragraph,
    CodeBlock,
    BlockQuote,
    HorizontalRule,
    RawHTML,
    # List nodes
    BulletList,
    OrderedList,
    ListItem,
    # Table nodes
    Table,
    TableRow,
    TableCell,
    # Material extension nodes
    Admonition,
    MermaidDiagram,
    ContentTabs,
    Tab,
    Expandable,
    # Graceful degradation
    UnsupportedBlock,
    # Traversal utility
    IRNode,
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
    "CodeInlineNode",
    "LinkNode",
    "ImageNode",
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
]
