"""Emit IR nodes as Confluence storage XHTML.

Confluence storage format is an XML dialect accepted by the Confluence REST
API and renderable inside the editor.  Key constructs:

* ``<ac:structured-macro>`` — wraps built-in macros (code, info, warning …)
* ``<ac:rich-text-body>`` — macro body rendered as wiki content
* ``<ac:plain-text-body>`` — macro body treated as literal text (code)
* ``<ac:parameter>`` — a named macro parameter
* ``<ri:url>`` / ``<ri:attachment>`` — resource identifiers

References
----------
https://developer.atlassian.com/server/confluence/confluence-storage-format/
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Sequence

from mkdocs_to_confluence.ir.nodes import (
    Admonition,
    BlockQuote,
    BoldNode,
    BulletList,
    CodeBlock,
    CodeInlineNode,
    ContentTabs,
    Expandable,
    FrontMatter,
    HorizontalRule,
    ImageNode,
    IRNode,
    ItalicNode,
    LinkNode,
    ListItem,
    MermaidDiagram,
    OrderedList,
    Paragraph,
    RawHTML,
    Section,
    StrikethroughNode,
    Table,
    TableCell,
    TableRow,
    TextNode,
    UnsupportedBlock,
)

# ── Admonition kind → Confluence macro name ───────────────────────────────────

# Types that map to Confluence's four native panel macros (include built-in icons).
_ADMONITION_MACRO: dict[str, str] = {
    "note": "info",
    "abstract": "info",
    "summary": "info",
    "tldr": "info",
    "info": "info",
    "todo": "info",
    "tip": "tip",
    "hint": "tip",
    "important": "tip",
    "success": "tip",
    "check": "tip",
    "done": "tip",
    "warning": "warning",
    "caution": "warning",
    "attention": "warning",
    "example": "note",
    "quote": "note",
    "cite": "note",
}

# Types that need a custom-coloured panel macro (red — no native equivalent).
# Title is prefixed with an emoji since the panel macro has no built-in icon.
_ADMONITION_DANGER_KINDS: frozenset[str] = frozenset(
    {"danger", "error", "bug", "failure", "fail", "missing"}
)
_DANGER_EMOJI = "🚨"
_DANGER_COLOURS = {
    "borderColor": "#DE350B",
    "titleBGColor": "#DE350B",
    "bgColor": "#FFEBE6",
}

_DEFAULT_ADMONITION_TITLES: dict[str, str] = {
    "note": "Note",
    "abstract": "Abstract",
    "summary": "Summary",
    "tldr": "TL;DR",
    "info": "Info",
    "todo": "Todo",
    "tip": "Tip",
    "hint": "Hint",
    "important": "Important",
    "success": "Success",
    "check": "Check",
    "done": "Done",
    "warning": "Warning",
    "caution": "Caution",
    "attention": "Attention",
    "failure": "Failure",
    "fail": "Fail",
    "missing": "Missing",
    "danger": "Danger",
    "error": "Error",
    "bug": "Bug",
    "example": "Example",
    "quote": "Quote",
    "cite": "Cite",
}


# ── Public API ─────────────────────────────────────────────────────────────────


def emit(nodes: Sequence[IRNode]) -> str:
    """Convert a sequence of top-level IR nodes to Confluence storage XHTML.

    Args:
        nodes: Top-level IR nodes as returned by the parser.

    Returns:
        A UTF-8 string of valid Confluence storage format XML, without an XML
        declaration (Confluence expects the body fragment only).
    """
    parts: list[str] = []
    for node in nodes:
        parts.append(_emit_node(node))
    return "".join(parts)


# ── Node dispatch ─────────────────────────────────────────────────────────────


def _emit_node(node: IRNode) -> str:
    if isinstance(node, Section):
        return _emit_section(node)
    if isinstance(node, Paragraph):
        return _emit_paragraph(node)
    if isinstance(node, CodeBlock):
        return _emit_code_block(node)
    if isinstance(node, Admonition):
        return _emit_admonition(node)
    if isinstance(node, BulletList):
        return _emit_bullet_list(node)
    if isinstance(node, OrderedList):
        return _emit_ordered_list(node)
    if isinstance(node, Table):
        return _emit_table(node)
    if isinstance(node, BlockQuote):
        return _emit_blockquote(node)
    if isinstance(node, HorizontalRule):
        return "<hr/>\n"
    if isinstance(node, RawHTML):
        return _emit_raw_html(node)
    if isinstance(node, MermaidDiagram):
        return _emit_mermaid(node)
    if isinstance(node, ContentTabs):
        return _emit_content_tabs(node)
    if isinstance(node, Expandable):
        return _emit_expandable(node)
    if isinstance(node, FrontMatter):
        return _emit_front_matter(node)
    if isinstance(node, UnsupportedBlock):
        return _emit_unsupported(node)
    # Inline nodes at block level (shouldn't normally appear, but be safe)
    return _emit_inline(node)


# ── Block emitters ────────────────────────────────────────────────────────────


def _emit_section(node: Section) -> str:
    tag = f"h{node.level}"
    title_html = _emit_inlines(node.title)
    heading = f"<{tag}>{title_html}</{tag}>\n"
    body = emit(node.children)
    return heading + body


def _source_link_label(url: str) -> str:
    """Return a platform-aware label for the source edit link.

    Detects GitHub, GitLab and Bitbucket from the URL hostname and returns
    "Edit in <Platform> ↗".  Falls back to "Edit source ↗" for anything else.
    Only the proven-safe ↗ arrow is used — no emoji that may render as ??? on
    Confluence Cloud.
    """
    lurl = url.lower()
    if "github.com" in lurl:
        platform = "GitHub"
    elif "gitlab.com" in lurl or "gitlab." in lurl:
        platform = "GitLab"
    elif "bitbucket.org" in lurl:
        platform = "Bitbucket"
    else:
        return "Edit source \u2197"
    return f"Edit in {platform} \u2197"


def _emit_front_matter(node: FrontMatter) -> str:
    """Emit front matter as an optional subtitle paragraph + Page Properties macro."""
    parts: list[str] = []

    if node.subtitle:
        parts.append(f"<p><em>{html.escape(node.subtitle)}</em></p>\n")

    has_table = node.properties or node.source_url
    if has_table:
        rows = "".join(
            f"    <tr><th>{html.escape(display)}</th>"
            f"<td>{html.escape(value)}</td></tr>\n"
            for display, value in node.properties
        )
        if node.source_url:
            label = html.escape(_source_link_label(node.source_url))
            href = html.escape(node.source_url)
            rows += (
                f'    <tr><th>Source</th>'
                f'<td><a href="{href}">{label}</a></td></tr>\n'
            )
        parts.append(
            '<ac:structured-macro ac:name="details">\n'
            "  <ac:rich-text-body>\n"
            "    <table><tbody>\n"
            f"{rows}"
            "    </tbody></table>\n"
            "  </ac:rich-text-body>\n"
            "</ac:structured-macro>\n"
        )

    return "".join(parts)


def _emit_paragraph(node: Paragraph) -> str:
    return f"<p>{_emit_inlines(node.children)}</p>\n"


def _emit_code_block(node: CodeBlock) -> str:
    parts = ['<ac:structured-macro ac:name="code">\n']
    if node.language:
        parts.append(
            f'  <ac:parameter ac:name="language">{html.escape(node.language)}</ac:parameter>\n'
        )
    if node.title:
        parts.append(
            f'  <ac:parameter ac:name="title">{html.escape(node.title)}</ac:parameter>\n'
        )
    if node.linenums:
        parts.append('  <ac:parameter ac:name="linenumbers">true</ac:parameter>\n')
        if node.linenums_start != 1:
            parts.append(
                f'  <ac:parameter ac:name="firstline">{node.linenums_start}</ac:parameter>\n'
            )
    # Escape ]]> sequences inside CDATA to avoid breaking the block
    safe_code = node.code.replace("]]>", "]]]]><![CDATA[>")
    parts.append(f"  <ac:plain-text-body><![CDATA[{safe_code}]]></ac:plain-text-body>\n")
    parts.append("</ac:structured-macro>\n")
    return "".join(parts)


def _emit_admonition(node: Admonition) -> str:
    title = node.title or _DEFAULT_ADMONITION_TITLES.get(node.kind, node.kind.capitalize())
    body = emit(node.children)

    if node.kind in _ADMONITION_DANGER_KINDS:
        colours = "".join(
            f'  <ac:parameter ac:name="{k}">{v}</ac:parameter>\n'
            for k, v in _DANGER_COLOURS.items()
        )
        prefixed_title = html.escape(f"{_DANGER_EMOJI} {title}")
        return (
            '<ac:structured-macro ac:name="panel">\n'
            f'  <ac:parameter ac:name="title">{prefixed_title}</ac:parameter>\n'
            f"{colours}"
            f"  <ac:rich-text-body>\n{body}  </ac:rich-text-body>\n"
            "</ac:structured-macro>\n"
        )

    macro_name = _ADMONITION_MACRO.get(node.kind, "info")
    return (
        f'<ac:structured-macro ac:name="{macro_name}">\n'
        f'  <ac:parameter ac:name="title">{html.escape(title)}</ac:parameter>\n'
        f"  <ac:rich-text-body>\n{body}  </ac:rich-text-body>\n"
        f"</ac:structured-macro>\n"
    )


def _emit_bullet_list(node: BulletList) -> str:
    items = "".join(_emit_list_item(i) for i in node.items)
    return f"<ul>\n{items}</ul>\n"


def _emit_ordered_list(node: OrderedList) -> str:
    items = "".join(_emit_list_item(i) for i in node.items)
    start_attr = f' start="{node.start}"' if node.start != 1 else ""
    return f"<ol{start_attr}>\n{items}</ol>\n"


def _emit_list_item(item: ListItem) -> str:
    inner = emit(item.children)
    return f"  <li>{inner.strip()}</li>\n"


def _emit_table(node: Table) -> str:
    parts = ["<table>\n  <tbody>\n"]
    parts.append(_emit_table_row(node.header, is_header=True))
    for row in node.rows:
        parts.append(_emit_table_row(row, is_header=False))
    parts.append("  </tbody>\n</table>\n")
    return "".join(parts)


def _emit_table_row(row: TableRow, *, is_header: bool) -> str:
    cells = "".join(_emit_table_cell(c, force_header=is_header) for c in row.cells)
    return f"    <tr>\n{cells}    </tr>\n"


def _emit_table_cell(cell: TableCell, *, force_header: bool) -> str:
    tag = "th" if (cell.is_header or force_header) else "td"
    align_attr = f' style="text-align: {cell.align};"' if cell.align else ""
    content = _emit_inlines(cell.children)
    return f"      <{tag}{align_attr}>{content}</{tag}>\n"


def _emit_blockquote(node: BlockQuote) -> str:
    body = emit(node.children)
    return f"<blockquote>\n{body}</blockquote>\n"


def _emit_raw_html(node: RawHTML) -> str:
    safe = node.html.replace("]]>", "]]]]><![CDATA[>")
    return (
        '<ac:structured-macro ac:name="html">\n'
        f"  <ac:plain-text-body><![CDATA[{safe}]]></ac:plain-text-body>\n"
        "</ac:structured-macro>\n"
    )


def _emit_mermaid(node: MermaidDiagram) -> str:
    # Degrade gracefully: wrap source in a code block labelled "mermaid"
    safe = node.source.replace("]]>", "]]]]><![CDATA[>")
    return (
        '<ac:structured-macro ac:name="code">\n'
        '  <ac:parameter ac:name="language">mermaid</ac:parameter>\n'
        f"  <ac:plain-text-body><![CDATA[{safe}]]></ac:plain-text-body>\n"
        "</ac:structured-macro>\n"
    )


def _emit_content_tabs(node: ContentTabs) -> str:
    # Degrade to a series of expand macros (one per tab)
    parts: list[str] = []
    for tab in node.tabs:
        body = emit(tab.children)
        parts.append(
            '<ac:structured-macro ac:name="expand">\n'
            f'  <ac:parameter ac:name="title">{html.escape(tab.label)}</ac:parameter>\n'
            f"  <ac:rich-text-body>\n{body}  </ac:rich-text-body>\n"
            "</ac:structured-macro>\n"
        )
    return "".join(parts)


def _emit_expandable(node: Expandable) -> str:
    body = emit(node.children)
    return (
        '<ac:structured-macro ac:name="expand">\n'
        f'  <ac:parameter ac:name="title">{html.escape(node.title)}</ac:parameter>\n'
        f"  <ac:rich-text-body>\n{body}  </ac:rich-text-body>\n"
        "</ac:structured-macro>\n"
    )


def _emit_unsupported(node: UnsupportedBlock) -> str:
    safe = html.escape(node.raw)
    return (
        '<ac:structured-macro ac:name="warning">\n'
        '  <ac:parameter ac:name="title">Unsupported block</ac:parameter>\n'
        f"  <ac:rich-text-body><pre>{safe}</pre></ac:rich-text-body>\n"
        "</ac:structured-macro>\n"
    )


# ── Inline emitters ───────────────────────────────────────────────────────────


def _emit_inlines(nodes: Sequence[IRNode]) -> str:
    return "".join(_emit_inline(n) for n in nodes)


def _emit_inline(node: IRNode) -> str:
    if isinstance(node, TextNode):
        return html.escape(node.text)
    if isinstance(node, BoldNode):
        return f"<strong>{_emit_inlines(node.children)}</strong>"
    if isinstance(node, ItalicNode):
        return f"<em>{_emit_inlines(node.children)}</em>"
    if isinstance(node, StrikethroughNode):
        return f"<s>{_emit_inlines(node.children)}</s>"
    if isinstance(node, CodeInlineNode):
        return f"<code>{html.escape(node.code)}</code>"
    if isinstance(node, LinkNode):
        return _emit_link(node)
    if isinstance(node, ImageNode):
        return _emit_image(node)
    # Fallback: emit unknown inline nodes as escaped repr
    return html.escape(repr(node))


def _emit_link(node: LinkNode) -> str:
    # Internal page link: resolved by the internallinks transform
    if node.is_internal:
        label = _emit_inlines(node.children)
        page_title = html.escape(node.href)
        anchor_attr = f' ac:anchor="{html.escape(node.anchor)}"' if node.anchor else ""
        return (
            f"<ac:link{anchor_attr}>"
            f'<ri:page ac:title="{page_title}"/>'
            f"<ac:plain-text-link-body>{label}</ac:plain-text-link-body>"
            "</ac:link>"
        )
    # Attachment link: local non-Markdown file with a resolved attachment name
    if node.attachment_name is not None:
        label = _emit_inlines(node.children)
        filename = html.escape(node.attachment_name)
        return (
            "<ac:link>"
            f'<ri:attachment ri:filename="{filename}"/>'
            f"<ac:plain-text-link-body>{label}</ac:plain-text-link-body>"
            "</ac:link>"
        )
    # Unresolved .md link: Confluence strips <a href="...md"> entirely because
    # relative markdown paths are not valid Storage Format URLs.  Degrade to
    # the label text so content is never silently lost.
    if node.href.lower().endswith(".md") or ".md#" in node.href.lower():
        return _emit_inlines(node.children)
    label = _emit_inlines(node.children)
    escaped_href = html.escape(node.href)
    return f'<a href="{escaped_href}">{label}</a>'


def _emit_image(node: ImageNode) -> str:
    alt_attr = f' ac:alt="{html.escape(node.alt)}"' if node.alt else ""
    title_attr = f' ac:title="{html.escape(node.title)}"' if node.title else ""
    # Local file → attachment reference; URL → external ri:url
    src = node.src
    if src.startswith(("http://", "https://", "//", "data:")):
        ref = f'<ri:url ri:value="{html.escape(src)}"/>'
        return f"<ac:image{alt_attr}{title_attr}>{ref}</ac:image>"
    else:
        filename = html.escape(node.attachment_name or Path(src).name)
        # data-local-path is used by the preview renderer only (not valid XHTML)
        local_attr = f' data-local-path="{html.escape(src)}"'
        ref = f'<ri:attachment ri:filename="{filename}"/>'
        return f"<ac:image{alt_attr}{title_attr}{local_attr}>{ref}</ac:image>"
