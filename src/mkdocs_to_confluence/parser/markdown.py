"""Minimal markdown-to-IR parser.

Supported in this milestone
---------------------------
* ATX headings (``# H1`` … ``###### H6``) → :class:`~ir.Section`
* Fenced code blocks (`` ``` `` or ``~~~``) → :class:`~ir.CodeBlock`
  with full Material attribute parsing (language, title, linenums, hl_lines)
* Paragraphs (consecutive non-blank lines) → :class:`~ir.Paragraph`
* Admonitions (``!!!``/``???``/``???+``) → :class:`~ir.Admonition`
  Body is recursively tokenized, so nested code blocks and paragraphs work.

Not yet supported (later milestones)
--------------------------------------
* Inline formatting (bold, italic, links, images)
* Content tabs, mermaid diagrams
* Setext headings (underline style)
* Block quotes, lists, tables, horizontal rules

Inline content of headings and paragraphs is represented as a single
:class:`~ir.TextNode` carrying the raw text; once the inline parser is
implemented that node will be replaced by structured inline nodes.

Architecture notes
------------------
The parser is a two-phase pipeline:

1. :func:`_tokenize` — single left-to-right pass over lines; yields typed
   ``_Token`` objects with no IR dependency.
2. :func:`_build_tree` — consumes the token stream, maintains a heading
   stack to build the nested :class:`~ir.Section` tree, and returns the
   top-level ``tuple[IRNode, ...]``.

This separation makes each phase independently testable and lets us swap in
a proper library (e.g. ``markdown-it-py``) later without touching the IR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Union

from mkdocs_to_confluence.ir.nodes import (
    Admonition,
    BlockQuote,
    BoldNode,
    BulletList,
    CodeBlock,
    CodeInlineNode,
    ContentTabs,
    DefinitionItem,
    DefinitionList,
    FootnoteBlock,
    FootnoteDef,
    FootnoteRef,
    HorizontalRule,
    ImageNode,
    InlineHtmlNode,
    IRNode,
    ItalicNode,
    LineBreakNode,
    LinkNode,
    ListItem,
    MermaidDiagram,
    OrderedList,
    Paragraph,
    Section,
    StrikethroughNode,
    SubscriptNode,
    SuperscriptNode,
    Tab,
    Table,
    TableCell,
    TableRow,
    TextNode,
)

# ── Public API ────────────────────────────────────────────────────────────────


def parse(text: str) -> tuple[IRNode, ...]:
    """Parse *text* (preprocessed markdown) into a tuple of top-level IR nodes.

    Args:
        text: Preprocessed markdown content (includes already resolved).

    Returns:
        A tuple of top-level :class:`~ir.IRNode` instances.  Headings create
        nested :class:`~ir.Section` trees; everything else becomes a direct
        child of its enclosing section or of the document root.
    """
    tokens = _tokenize(text)
    return _build_tree(tokens)


# ── Internal token types ──────────────────────────────────────────────────────


@dataclass
class _HeadingToken:
    level: int
    text: str  # raw heading text, stripped of leading # characters


@dataclass
class _CodeToken:
    code: str
    language: str | None
    title: str | None
    linenums: bool
    linenums_start: int
    highlight_lines: tuple[int, ...]


@dataclass
class _ParagraphToken:
    lines: list[str]  # non-blank lines forming one paragraph


@dataclass
class _AdmonitionToken:
    kind: str
    title: str | None       # None → use the kind's default Confluence title
    collapsible: bool       # True for ??? and ???+
    body_tokens: list[_Token]


@dataclass
class _HRToken:
    """A horizontal rule (``---``, ``***``, ``___``)."""


@dataclass
class _BlockQuoteToken:
    body_tokens: list["_Token"]


@dataclass
class _ListItemData:
    text: str
    task: bool | None = None  # None=regular, True=checked, False=unchecked


@dataclass
class _BulletListToken:
    items: list[_ListItemData]


@dataclass
class _OrderedListToken:
    start: int
    items: list[_ListItemData]


@dataclass
class _TabData:
    label: str
    body_tokens: list["_Token"]


@dataclass
class _ContentTabsToken:
    tabs: list[_TabData]


@dataclass
class _TableToken:
    header_cells: list[str]
    aligns: list[str | None]
    rows: list[list[str]]


@dataclass
class _FootnoteDefToken:
    label: str
    content: str  # raw inline content of the definition


@dataclass
class _DefListItemData:
    term: str
    definitions: list[str]


@dataclass
class _DefListToken:
    items: list[_DefListItemData]


_Token = Union[
    _HeadingToken,
    _CodeToken,
    _ParagraphToken,
    _AdmonitionToken,
    _HRToken,
    _BlockQuoteToken,
    _BulletListToken,
    _OrderedListToken,
    _ContentTabsToken,
    _TableToken,
    _FootnoteDefToken,
    _DefListToken,
]


# ── Tokenizer ─────────────────────────────────────────────────────────────────

# Matches ATX headings: optional leading whitespace, 1–6 '#', space, text.
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)(?:\s+#+\s*)?$")

# Matches the opening line of a fenced code block.
_FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

# Matches an admonition opener:  !!! kind  /  !!! kind "title"  /  ??? kind  /  ???+ kind
_ADMONITION_RE = re.compile(
    r'^(?P<marker>!{3}|\?{3}\+?)\s+(?P<kind>\w+)(?:\s+["\'](?P<title>[^"\']*)["\'])?$'
)

# Matches a Material for MkDocs content tab opener:  === "Label"
_TAB_RE = re.compile(r'^===\s+["\'](?P<label>[^"\']*)["\']$')

# Matches a horizontal rule (3+ dashes, stars, or underscores alone on a line).
_HR_RE = re.compile(r'^(?:-{3,}|\*{3,}|_{3,})\s*$')

# Matches a bullet list item: optional leading spaces, then - / * / +, then space.
_BULLET_RE = re.compile(r'^(?P<indent>\s*)(?P<marker>[-*+])\s+(?P<text>.+)$')

# Matches an ordered list item: digits, dot, space.
_ORDERED_RE = re.compile(r'^(?P<indent>\s*)(?P<num>\d+)\.\s+(?P<text>.+)$')

# Matches a task checkbox at the start of a list item body.
_TASK_RE = re.compile(r'^\[(?P<state>[xX ])\]\s+(?P<rest>.+)$')


# Matches a footnote definition: [^label]: content (at line start)
_FOOTNOTE_DEF_RE = re.compile(r'^\[\^(?P<label>[^\]]+)\]:\s+(?P<content>.+)$')

# Matches an inline footnote reference: [^label]
_FOOTNOTE_REF_RE = re.compile(r'^\[\^(?P<label>[^\]]+)\]')

# Matches a definition list definition line:  :   text
_DEFLIST_DEF_RE = re.compile(r'^:\s+(?P<text>.+)$')


def _tokenize(text: str) -> list[_Token]:
    """Convert *text* into a flat list of tokens.

    The tokenizer has two states: NORMAL and IN_FENCE.
    """
    lines = text.splitlines()
    tokens: list[_Token] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ────────────────────────────────────────────────
        fence_m = _FENCE_OPEN_RE.match(line)
        if fence_m:
            fence_char = fence_m.group("fence")[0]
            fence_min = len(fence_m.group("fence"))
            info = fence_m.group("info").strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines):
                close_m = re.match(
                    rf"^(?P<close>[{re.escape(fence_char)}]{{{fence_min},}})\s*$",
                    lines[i],
                )
                if close_m:
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            # Strip a single leading/trailing blank line from the code body
            # (common formatting convention).
            code = "\n".join(code_lines)
            lang, title, linenums, ln_start, hl = _parse_info_string(info)
            tokens.append(
                _CodeToken(
                    code=code,
                    language=lang,
                    title=title,
                    linenums=linenums,
                    linenums_start=ln_start,
                    highlight_lines=hl,
                )
            )
            continue

        # ── ATX heading ──────────────────────────────────────────────────────
        heading_m = _HEADING_RE.match(line)
        if heading_m:
            level = len(heading_m.group("hashes"))
            heading_text = heading_m.group("text").strip()
            tokens.append(_HeadingToken(level=level, text=heading_text))
            i += 1
            continue

        # ── Blank line ───────────────────────────────────────────────────────
        if not line.strip():
            i += 1
            continue

        # ── Admonition ───────────────────────────────────────────────────────
        adm_m = _ADMONITION_RE.match(line)
        if adm_m:
            marker = adm_m.group("marker")
            kind = adm_m.group("kind")
            title = adm_m.group("title")    # None if no quoted title given
            collapsible = marker.startswith("?")
            i += 1
            # Collect body: blank lines or lines indented by ≥4 spaces / 1 tab.
            body_raw: list[str] = []
            while i < len(lines):
                bl = lines[i]
                if not bl.strip():
                    body_raw.append("")
                    i += 1
                elif bl.startswith("    ") or bl.startswith("\t"):
                    body_raw.append(bl[4:] if bl.startswith("    ") else bl[1:])
                    i += 1
                else:
                    break
            # Drop trailing blank lines so the recursive tokenizer stays clean.
            while body_raw and not body_raw[-1].strip():
                body_raw.pop()
            body_tokens = _tokenize("\n".join(body_raw))
            tokens.append(
                _AdmonitionToken(
                    kind=kind,
                    title=title,
                    collapsible=collapsible,
                    body_tokens=body_tokens,
                )
            )
            continue

        # ── Content tabs (=== "Label") ────────────────────────────────────────
        tab_m = _TAB_RE.match(line)
        if tab_m:
            tabs: list[_TabData] = []
            while i < len(lines):
                tm = _TAB_RE.match(lines[i])
                if not tm:
                    break
                label = tm.group("label")
                i += 1
                body_raw_tab: list[str] = []
                while i < len(lines):
                    bl = lines[i]
                    if not bl.strip():
                        body_raw_tab.append("")
                        i += 1
                    elif bl.startswith("    ") or bl.startswith("\t"):
                        body_raw_tab.append(bl[4:] if bl.startswith("    ") else bl[1:])
                        i += 1
                    else:
                        break
                while body_raw_tab and not body_raw_tab[-1].strip():
                    body_raw_tab.pop()
                tabs.append(_TabData(label=label, body_tokens=_tokenize("\n".join(body_raw_tab))))
            if tabs:
                tokens.append(_ContentTabsToken(tabs=tabs))
            continue

        # ── Horizontal rule ───────────────────────────────────────────────────
        if _HR_RE.match(line):
            tokens.append(_HRToken())
            i += 1
            continue

        # ── Blockquote ────────────────────────────────────────────────────────
        if line.startswith("> ") or line == ">":
            bq_lines: list[str] = []
            while i < len(lines) and (lines[i].startswith("> ") or lines[i] == ">"):
                stripped = lines[i][2:] if lines[i].startswith("> ") else ""
                bq_lines.append(stripped)
                i += 1
            body_tokens_bq = _tokenize("\n".join(bq_lines))
            tokens.append(_BlockQuoteToken(body_tokens=body_tokens_bq))
            continue

        # ── Bullet list ───────────────────────────────────────────────────────
        bullet_m = _BULLET_RE.match(line)
        if bullet_m and not bullet_m.group("indent"):
            list_items: list[_ListItemData] = []
            while i < len(lines):
                bm = _BULLET_RE.match(lines[i])
                if not bm or bm.group("indent"):
                    # Loose list: blank line(s) followed by another bullet item.
                    if not lines[i].strip():
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines):
                            peek = _BULLET_RE.match(lines[j])
                            if peek and not peek.group("indent"):
                                i = j  # skip blanks, resume at next item
                                continue
                    break
                item_text = bm.group("text")
                task: bool | None = None
                task_m = _TASK_RE.match(item_text)
                if task_m:
                    task = task_m.group("state").lower() == "x"
                    item_text = task_m.group("rest")
                i += 1
                # Collect continuation lines (non-blank, non-list) into this item.
                while i < len(lines) and lines[i].strip():
                    cont = lines[i]
                    if (_BULLET_RE.match(cont) and not _BULLET_RE.match(cont).group("indent")) or (
                        _ORDERED_RE.match(cont) and not _ORDERED_RE.match(cont).group("indent")
                    ):
                        break
                    item_text = item_text.rstrip() + " " + cont.strip()
                    i += 1
                list_items.append(_ListItemData(text=item_text, task=task))
            tokens.append(_BulletListToken(items=list_items))
            continue

        # ── Ordered list ──────────────────────────────────────────────────────
        ordered_m = _ORDERED_RE.match(line)
        if ordered_m and not ordered_m.group("indent"):
            start = int(ordered_m.group("num"))
            ord_items: list[_ListItemData] = []
            while i < len(lines):
                om = _ORDERED_RE.match(lines[i])
                if not om or om.group("indent"):
                    # Loose list: blank line(s) followed by another ordered item.
                    if not lines[i].strip():
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines):
                            peek = _ORDERED_RE.match(lines[j])
                            if peek and not peek.group("indent"):
                                i = j  # skip blanks, resume at next item
                                continue
                    break
                item_text = om.group("text")
                i += 1
                # Collect continuation lines (non-blank, non-list) into this item.
                while i < len(lines) and lines[i].strip():
                    cont = lines[i]
                    if (_ORDERED_RE.match(cont) and not _ORDERED_RE.match(cont).group("indent")) or (
                        _BULLET_RE.match(cont) and not _BULLET_RE.match(cont).group("indent")
                    ):
                        break
                    item_text = item_text.rstrip() + " " + cont.strip()
                    i += 1
                ord_items.append(_ListItemData(text=item_text))
            tokens.append(_OrderedListToken(start=start, items=ord_items))
            continue

        # ── Table ─────────────────────────────────────────────────────────────
        if line.strip().startswith("|") and i + 1 < len(lines):
            sep = lines[i + 1]
            if re.match(r"^[\|\s\-:]+$", sep) and "|" in sep and "-" in sep:
                header_cells = _split_table_row(line)
                aligns = _parse_table_aligns(sep)
                table_rows: list[list[str]] = []
                i += 2  # skip header and separator
                while i < len(lines) and "|" in lines[i]:
                    table_rows.append(_split_table_row(lines[i]))
                    i += 1
                tokens.append(
                    _TableToken(
                        header_cells=header_cells,
                        aligns=aligns,
                        rows=table_rows,
                    )
                )
                continue

        # ── Footnote definition ───────────────────────────────────────────────
        fn_def_m = _FOOTNOTE_DEF_RE.match(line)
        if fn_def_m:
            tokens.append(_FootnoteDefToken(
                label=fn_def_m.group("label"),
                content=fn_def_m.group("content"),
            ))
            i += 1
            continue

        # ── Definition list ──────────────────────────────────────────────────
        # A definition list starts when a non-blank, non-special line is
        # immediately followed by a `:   definition` line.
        if (
            line.strip()
            and not _HEADING_RE.match(line)
            and not _FENCE_OPEN_RE.match(line)
            and not _ADMONITION_RE.match(line)
            and not _HR_RE.match(line)
            and not (line.startswith("> ") or line == ">")
            and not (_BULLET_RE.match(line) and not _BULLET_RE.match(line).group("indent"))  # type: ignore[union-attr]
            and not (_ORDERED_RE.match(line) and not _ORDERED_RE.match(line).group("indent"))  # type: ignore[union-attr]
            and not line.strip().startswith("|")
            and not _TAB_RE.match(line)
            and i + 1 < len(lines)
            and _DEFLIST_DEF_RE.match(lines[i + 1])
        ):
            dl_items: list[_DefListItemData] = []
            while i < len(lines) and lines[i].strip():
                term_line = lines[i]
                # term must not itself be a definition line
                if _DEFLIST_DEF_RE.match(term_line):
                    break
                defs: list[str] = []
                i += 1
                while i < len(lines):
                    def_m = _DEFLIST_DEF_RE.match(lines[i])
                    if def_m:
                        defs.append(def_m.group("text"))
                        i += 1
                    else:
                        break
                if defs:
                    dl_items.append(_DefListItemData(term=term_line.strip(), definitions=defs))
                else:
                    # Not actually a def-list item; rewind and fall through to paragraph
                    break
            if dl_items:
                tokens.append(_DefListToken(items=dl_items))
                continue

        # ── Paragraph accumulation ───────────────────────────────────────────
        para_lines: list[str] = []
        while i < len(lines):
            current = lines[i]
            if not current.strip():
                break
            if _HEADING_RE.match(current):
                break
            if _FENCE_OPEN_RE.match(current):
                break
            if _ADMONITION_RE.match(current):
                break
            if _HR_RE.match(current):
                break
            if current.startswith("> ") or current == ">":
                break
            if _BULLET_RE.match(current) and not _BULLET_RE.match(current).group("indent"):  # type: ignore[union-attr]
                break
            if _ORDERED_RE.match(current) and not _ORDERED_RE.match(current).group("indent"):  # type: ignore[union-attr]
                break
            if current.strip().startswith("|"):
                break
            if _TAB_RE.match(current):
                break
            para_lines.append(current)
            i += 1
        if para_lines:
            tokens.append(_ParagraphToken(lines=para_lines))

    return tokens


# ── Info-string parser ────────────────────────────────────────────────────────

# Matches key="value" or key='value' attribute pairs.
_ATTR_RE = re.compile(r'(\w+)=["\']([^"\']*)["\']')


def _parse_info_string(
    info: str,
) -> tuple[str | None, str | None, bool, int, tuple[int, ...]]:
    """Parse the info string that follows a code fence opening.

    Handles::

        python
        python title="example.py"
        python linenums="1"
        python title="main.py" linenums="5" hl_lines="2 3"

    Returns:
        ``(language, title, linenums, linenums_start, highlight_lines)``
    """
    info = info.strip()
    if not info:
        return None, None, False, 1, ()

    attrs: dict[str, str] = {}
    for m in _ATTR_RE.finditer(info):
        attrs[m.group(1)] = m.group(2)

    # Language is the first whitespace-delimited token *before* any key= pair.
    first_attr = _ATTR_RE.search(info)
    lang_part = info[: first_attr.start()].strip() if first_attr else info
    language: str | None = lang_part if lang_part else None

    title: str | None = attrs.get("title")

    linenums_val = attrs.get("linenums")
    if linenums_val is not None:
        linenums = True
        try:
            linenums_start = max(1, int(linenums_val))
        except ValueError:
            linenums_start = 1
    else:
        linenums = False
        linenums_start = 1

    hl_raw = attrs.get("hl_lines", "")
    highlight_lines = tuple(int(n) for n in hl_raw.split() if n.isdigit())

    return language, title, linenums, linenums_start, highlight_lines


# ── Table helpers ─────────────────────────────────────────────────────────────


def _split_table_row(line: str) -> list[str]:
    """Split a GFM table row into trimmed cell strings."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_table_aligns(sep_line: str) -> list[str | None]:
    """Extract per-column alignment from a GFM separator row."""
    aligns: list[str | None] = []
    for cell in _split_table_row(sep_line):
        c = cell.strip()
        if c.startswith(":") and c.endswith(":"):
            aligns.append("center")
        elif c.endswith(":"):
            aligns.append("right")
        elif c.startswith(":"):
            aligns.append("left")
        else:
            aligns.append(None)
    return aligns


# ── Inline parser ─────────────────────────────────────────────────────────────


def _parse_inline(text: str, fn_map: dict[str, int] | None = None) -> tuple[IRNode, ...]:
    """Parse inline markdown into a tuple of IR inline nodes.

    Handles: backtick code spans, images, links, bold (``**``/``__``),
    strikethrough (``~~``), italic (``*``/``_``), footnote refs, and plain text.
    """
    return tuple(_scan_inline(text, fn_map or {}))


def _scan_inline(text: str, fn_map: dict[str, int] | None = None) -> list[IRNode]:
    _fn = fn_map or {}
    nodes: list[IRNode] = []
    buf = ""
    i = 0
    n = len(text)

    def flush() -> None:
        nonlocal buf
        if buf:
            nodes.append(TextNode(text=buf))
            buf = ""

    while i < n:
        # Inline code: backtick span (supports multi-backtick like `` ` ``)
        if text[i] == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            tick = text[i:j]
            close_idx = text.find(tick, j)
            if close_idx != -1:
                flush()
                nodes.append(CodeInlineNode(code=text[j:close_idx].strip()))
                i = close_idx + len(tick)
            else:
                buf += tick
                i = j
            continue

        # Image: ![alt](src) or ![alt](src "title")
        if text[i : i + 2] == "![":
            m = re.match(
                r'!\[([^\]]*)\]\(([^\s)]+)(?:\s+"([^"]*)")?\s*\)', text[i:]
            )
            if m:
                flush()
                nodes.append(
                    ImageNode(src=m.group(2), alt=m.group(1), title=m.group(3))
                )
                i += len(m.group(0))
                continue

        # Footnote reference: [^label] — must be checked before generic link
        if text[i] == "[" and i + 1 < n and text[i + 1] == "^":
            fn_m = _FOOTNOTE_REF_RE.match(text[i:])
            if fn_m:
                label = fn_m.group("label")
                flush()
                nodes.append(FootnoteRef(label=label, number=_fn.get(label, 0)))
                i += len(fn_m.group(0))
                continue

        # Link: [text](href)
        if text[i] == "[":
            m = re.match(r"\[([^\]]*)\]\(([^)]*)\)", text[i:])
            if m:
                flush()
                inner = _scan_inline(m.group(1), _fn)
                nodes.append(LinkNode(href=m.group(2), children=tuple(inner)))
                i += len(m.group(0))
                continue

        # Bold: **text** or __text__
        if text[i : i + 2] in ("**", "__"):
            delim = text[i : i + 2]
            close_idx = text.find(delim, i + 2)
            if close_idx != -1:
                flush()
                inner = _scan_inline(text[i + 2 : close_idx], _fn)
                nodes.append(BoldNode(children=tuple(inner)))
                i = close_idx + 2
                continue

        # Strikethrough: ~~text~~
        if text[i : i + 2] == "~~":
            close_idx = text.find("~~", i + 2)
            if close_idx != -1:
                flush()
                inner = _scan_inline(text[i + 2 : close_idx], _fn)
                nodes.append(StrikethroughNode(children=tuple(inner)))
                i = close_idx + 2
                continue

        # Subscript: ~text~ (single tilde, checked after ~~ strikethrough)
        if text[i] == "~" and (i + 1 >= len(text) or text[i + 1] != "~"):
            close_idx = text.find("~", i + 1)
            if close_idx != -1 and close_idx > i + 1:
                flush()
                inner = _scan_inline(text[i + 1 : close_idx], _fn)
                nodes.append(SubscriptNode(children=tuple(inner)))
                i = close_idx + 1
                continue

        # Superscript: ^text^
        if text[i] == "^":
            close_idx = text.find("^", i + 1)
            if close_idx != -1 and close_idx > i + 1:
                flush()
                inner = _scan_inline(text[i + 1 : close_idx], _fn)
                nodes.append(SuperscriptNode(children=tuple(inner)))
                i = close_idx + 1
                continue

        # Italic: *text* — only for *, not _ (avoids false positives in code)
        if text[i] == "*":
            close_idx = text.find("*", i + 1)
            if close_idx != -1 and close_idx > i + 1:
                flush()
                inner = _scan_inline(text[i + 1 : close_idx], _fn)
                nodes.append(ItalicNode(children=tuple(inner)))
                i = close_idx + 1
                continue

        # Inline HTML: <br>, <br/>, <br /> and paired tags
        if text[i] == "<":
            # Hard line break
            br_m = re.match(r"<br\s*/?\s*>", text[i:], re.IGNORECASE)
            if br_m:
                flush()
                nodes.append(LineBreakNode())
                i += len(br_m.group(0))
                continue
            # Paired inline tags
            tag_m = re.match(
                r"<(mark|kbd|sub|sup|u|s|del|small)>", text[i:], re.IGNORECASE
            )
            if tag_m:
                raw_tag = tag_m.group(1).lower()
                tag = "s" if raw_tag == "del" else raw_tag
                close = f"</{raw_tag}>"
                close_idx = text.lower().find(close, i + len(tag_m.group(0)))
                if close_idx != -1:
                    flush()
                    inner = _scan_inline(text[i + len(tag_m.group(0)) : close_idx], _fn)
                    nodes.append(InlineHtmlNode(tag=tag, children=tuple(inner)))
                    i = close_idx + len(close)
                    continue

        buf += text[i]
        i += 1

    flush()
    return nodes


@dataclass
class _OpenSection:
    """Mutable accumulator for a heading that has not yet been closed."""

    level: int
    title_text: str
    children: list[IRNode] = field(default_factory=list)


def _build_tree(
    tokens: list[_Token],
    fn_map: dict[str, int] | None = None,
) -> tuple[IRNode, ...]:
    """Convert a flat token list into a nested IR node tree.

    Headings open :class:`_OpenSection` entries on the stack.  A heading of
    level N closes all open sections with level >= N (building nested
    :class:`~ir.Section` nodes), then opens a new section at level N.
    Block content (paragraphs, code blocks) goes into the innermost open
    section, or directly onto the root list if no section is open.
    """
    # Top-level call: extract footnote definitions and assign numbers.
    fn_defs: list[_FootnoteDefToken] = []
    if fn_map is None:
        fn_defs = [t for t in tokens if isinstance(t, _FootnoteDefToken)]
        fn_map = {t.label: i + 1 for i, t in enumerate(fn_defs)}
        tokens = [t for t in tokens if not isinstance(t, _FootnoteDefToken)]
    _fn = fn_map
    root: list[IRNode] = []
    stack: list[_OpenSection] = []

    for token in tokens:
        if isinstance(token, _HeadingToken):
            _close_from_level(token.level, stack, root)
            stack.append(_OpenSection(level=token.level, title_text=token.text))

        elif isinstance(token, _ParagraphToken):
            node = _paragraph_node(token, fn_map=_fn)
            _append_content(node, stack, root)

        elif isinstance(token, _CodeToken):
            if token.language and token.language.lower() == "mermaid":
                _append_content(MermaidDiagram(source=token.code), stack, root)
            else:
                _append_content(
                    CodeBlock(
                        code=token.code,
                        language=token.language,
                        title=token.title,
                        linenums=token.linenums,
                        linenums_start=token.linenums_start,
                        highlight_lines=token.highlight_lines,
                    ),
                    stack,
                    root,
                )

        elif isinstance(token, _AdmonitionToken):
            body_nodes = _build_tree(token.body_tokens, fn_map=_fn)
            _append_content(
                Admonition(
                    kind=token.kind,
                    title=token.title,
                    collapsible=token.collapsible,
                    children=body_nodes,
                ),
                stack,
                root,
            )

        elif isinstance(token, _HRToken):
            _append_content(HorizontalRule(), stack, root)

        elif isinstance(token, _BlockQuoteToken):
            body_nodes_bq = _build_tree(token.body_tokens, fn_map=_fn)
            _append_content(BlockQuote(children=body_nodes_bq), stack, root)

        elif isinstance(token, _BulletListToken):
            items = tuple(
                ListItem(children=_parse_inline(item.text, fn_map=_fn), task=item.task)
                for item in token.items
            )
            _append_content(BulletList(items=items), stack, root)

        elif isinstance(token, _OrderedListToken):
            items = tuple(
                ListItem(children=_parse_inline(item.text, fn_map=_fn))
                for item in token.items
            )
            _append_content(OrderedList(items=items, start=token.start), stack, root)

        elif isinstance(token, _TableToken):
            aligns = token.aligns

            def _make_cell(
                text: str, col: int, is_header: bool = False
            ) -> TableCell:
                align = aligns[col] if col < len(aligns) else None
                return TableCell(
                    children=_parse_inline(text, fn_map=_fn),
                    align=align,
                    is_header=is_header,
                )

            header = TableRow(
                cells=tuple(
                    _make_cell(c, j, is_header=True)
                    for j, c in enumerate(token.header_cells)
                )
            )
            body_rows = tuple(
                TableRow(
                    cells=tuple(_make_cell(c, j) for j, c in enumerate(row))
                )
                for row in token.rows
            )
            _append_content(Table(header=header, rows=body_rows), stack, root)

        elif isinstance(token, _ContentTabsToken):
            tab_nodes = tuple(
                Tab(label=t.label, children=_build_tree(t.body_tokens, fn_map=_fn))
                for t in token.tabs
            )
            _append_content(ContentTabs(tabs=tab_nodes), stack, root)

        elif isinstance(token, _DefListToken):
            dl_items = tuple(
                DefinitionItem(
                    term=_parse_inline(item.term, fn_map=_fn),
                    definitions=tuple(
                        _parse_inline(d, fn_map=_fn) for d in item.definitions
                    ),
                )
                for item in token.items
            )
            _append_content(DefinitionList(items=dl_items), stack, root)

    # Close all remaining open sections.
    _close_from_level(0, stack, root)

    # Append footnote block at the document root (top-level call only).
    if fn_defs:
        footnote_items = tuple(
            FootnoteDef(
                label=t.label,
                number=_fn[t.label],
                children=_parse_inline(t.content, fn_map=_fn),
            )
            for t in fn_defs
        )
        root.append(FootnoteBlock(items=footnote_items))

    return tuple(root)


def _close_from_level(
    level: int, stack: list[_OpenSection], root: list[IRNode]
) -> None:
    """Close (and emit) every open section with ``section.level >= level``."""
    while stack and stack[-1].level >= level:
        closed = stack.pop()
        section = Section(
            level=closed.level,
            anchor=_make_anchor(closed.title_text),
            title=_parse_inline(closed.title_text),
            children=tuple(closed.children),
        )
        _append_content(section, stack, root)


def _append_content(
    node: IRNode, stack: list[_OpenSection], root: list[IRNode]
) -> None:
    """Add *node* to the innermost open section's children, or to *root*."""
    if stack:
        stack[-1].children.append(node)
    else:
        root.append(node)


def _paragraph_node(token: _ParagraphToken, fn_map: dict[str, int] | None = None) -> Paragraph:
    """Convert a paragraph token into a :class:`~ir.Paragraph` node."""
    text = " ".join(line.strip() for line in token.lines)
    return Paragraph(children=_parse_inline(text, fn_map=fn_map))


# ── Anchor generation ─────────────────────────────────────────────────────────

_NON_WORD_RE = re.compile(r"[^\w\s-]")
_WHITESPACE_RE = re.compile(r"\s+")


def _make_anchor(text: str) -> str:
    """Convert heading text to a URL-safe fragment identifier.

    Follows MkDocs' default anchor-generation rules:
    - Lowercase
    - Strip non-word characters (keep ``-`` and word chars)
    - Replace whitespace runs with a single ``-``
    - Strip leading/trailing ``-``
    """
    anchor = text.lower()
    anchor = _NON_WORD_RE.sub("", anchor)
    anchor = _WHITESPACE_RE.sub("-", anchor.strip())
    return anchor.strip("-")
