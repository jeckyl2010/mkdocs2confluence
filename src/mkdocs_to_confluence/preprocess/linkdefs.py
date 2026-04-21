"""Reference-style link preprocessing.

Markdown supports two forms of reference-style links that our inline parser
does not handle:

    Full:       [link text][label]      with  [label]: url
    Collapsed:  [link text][]           with  [link text]: url

This module expands those patterns into equivalent inline links
``[link text](url)`` *before* the parser sees the text, so the rest of the
pipeline handles them transparently.

Approach
--------
1. :func:`collect_link_defs` — scan the whole document for definition lines
   (``[label]: url …``).
2. :func:`expand_link_refs` — replace ``[text][label]`` / ``[text][]`` with
   ``[text](url)`` wherever a matching definition exists; leaves unresolved
   references unchanged.
3. :func:`strip_link_defs` — remove definition lines so they don't end up as
   stray text in the output.

Code-span safety
----------------
Substitutions are intentionally skipped inside inline code spans (`` `…` ``)
to avoid mangling code examples that happen to use bracket notation.
"""

from __future__ import annotations

import re

# Definition line: [label]: url  or  [label]: url "title"
# Allows up to three leading spaces (standard CommonMark rule).
_DEF_LINE_RE = re.compile(
    r"^[ ]{0,3}\[(?P<label>[^\]]+)\]:\s+(?P<url>\S+)"
    r'(?:\s+"[^"]*"|\s+\'[^\']*\'|\s+\([^)]*\))?[ \t]*$',
    re.MULTILINE,
)

# Full reference: [text][label]  — label may be empty (collapsed reference)
_REF_LINK_RE = re.compile(r"\[(?P<text>[^\]]+)\]\[(?P<label>[^\]]*)\]")

# Inline code span (to skip substitution inside them)
_CODE_SPAN_RE = re.compile(r"`+[^`]*`+")


def collect_link_defs(text: str) -> dict[str, str]:
    """Return a ``{lowercase_label: url}`` mapping of all definition lines.

    Labels are case-insensitive per the CommonMark spec.
    """
    return {
        m.group("label").lower().strip(): m.group("url")
        for m in _DEF_LINE_RE.finditer(text)
    }


def expand_link_refs(text: str, defs: dict[str, str]) -> str:
    """Replace ``[text][label]`` and ``[text][]`` with ``[text](url)``.

    Substitution is skipped inside inline code spans.  Unresolved references
    are left unchanged so they can be handled gracefully downstream.
    """
    if not defs:
        return text

    def _expand(m: re.Match[str]) -> str:
        raw_label = m.group("label")
        label_key = (raw_label if raw_label else m.group("text")).lower().strip()
        url = defs.get(label_key)
        if url is None:
            return m.group(0)  # leave unresolved reference as-is
        text_part = m.group("text")
        return f"[{text_part}]({url})"

    # Process the document piece by piece, skipping code spans.
    parts: list[str] = []
    last = 0
    for code_m in _CODE_SPAN_RE.finditer(text):
        # Expand in the non-code segment before this code span
        segment = text[last : code_m.start()]
        parts.append(_REF_LINK_RE.sub(_expand, segment))
        # Emit the code span verbatim
        parts.append(code_m.group(0))
        last = code_m.end()
    # Expand in the remainder
    parts.append(_REF_LINK_RE.sub(_expand, text[last:]))
    return "".join(parts)


def strip_link_defs(text: str) -> str:
    """Remove definition lines from *text*.

    The lines are deleted entirely so they don't appear as stray paragraphs in
    the rendered output.
    """
    return _DEF_LINE_RE.sub("", text)
