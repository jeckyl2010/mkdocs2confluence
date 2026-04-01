"""Minimal markdown-to-IR parser.

Supported in this milestone
---------------------------
* ATX headings (``# H1`` … ``###### H6``) → :class:`~ir.Section`
* Fenced code blocks (`` ``` `` or ``~~~``) → :class:`~ir.CodeBlock`
  with full Material attribute parsing (language, title, linenums, hl_lines)
* Paragraphs (consecutive non-blank lines) → :class:`~ir.Paragraph`

Not yet supported (later milestones)
--------------------------------------
* Inline formatting (bold, italic, links, images)
* Admonitions, content tabs, mermaid diagrams
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
    CodeBlock,
    IRNode,
    Paragraph,
    Section,
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


_Token = Union[_HeadingToken, _CodeToken, _ParagraphToken]


# ── Tokenizer ─────────────────────────────────────────────────────────────────

# Matches ATX headings: optional leading whitespace, 1–6 '#', space, text.
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)(?:\s+#+\s*)?$")

# Matches the opening line of a fenced code block.
_FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


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

        # ── Paragraph accumulation ───────────────────────────────────────────
        para_lines: list[str] = []
        while i < len(lines):
            current = lines[i]
            # Stop on blank line, heading, or fence opening
            if not current.strip():
                break
            if _HEADING_RE.match(current):
                break
            if _FENCE_OPEN_RE.match(current):
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


# ── Tree builder ──────────────────────────────────────────────────────────────


@dataclass
class _OpenSection:
    """Mutable accumulator for a heading that has not yet been closed."""

    level: int
    title_text: str
    children: list[IRNode] = field(default_factory=list)


def _build_tree(tokens: list[_Token]) -> tuple[IRNode, ...]:
    """Convert a flat token list into a nested IR node tree.

    Headings open :class:`_OpenSection` entries on the stack.  A heading of
    level N closes all open sections with level >= N (building nested
    :class:`~ir.Section` nodes), then opens a new section at level N.
    Block content (paragraphs, code blocks) goes into the innermost open
    section, or directly onto the root list if no section is open.
    """
    root: list[IRNode] = []
    stack: list[_OpenSection] = []

    for token in tokens:
        if isinstance(token, _HeadingToken):
            _close_from_level(token.level, stack, root)
            stack.append(_OpenSection(level=token.level, title_text=token.text))

        elif isinstance(token, _ParagraphToken):
            node = _paragraph_node(token)
            _append_content(node, stack, root)

        elif isinstance(token, _CodeToken):
            node = CodeBlock(
                code=token.code,
                language=token.language,
                title=token.title,
                linenums=token.linenums,
                linenums_start=token.linenums_start,
                highlight_lines=token.highlight_lines,
            )
            _append_content(node, stack, root)

    # Close all remaining open sections.
    _close_from_level(0, stack, root)
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
            title=(TextNode(text=closed.title_text),),
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


def _paragraph_node(token: _ParagraphToken) -> Paragraph:
    """Convert a paragraph token into a :class:`~ir.Paragraph` node.

    Inline parsing is not yet implemented; the whole paragraph text is wrapped
    in a single :class:`~ir.TextNode`.
    """
    text = " ".join(line.strip() for line in token.lines)
    return Paragraph(children=(TextNode(text=text),))


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
