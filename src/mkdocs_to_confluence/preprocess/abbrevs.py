"""Extract and strip MkDocs abbreviation definitions from raw markdown.

MkDocs abbreviations use the syntax::

    *[ABBR]: Full definition text

These lines are processed by the ``pymdownx.snippets`` / ``abbr`` extension
during MkDocs builds.  Confluence has no native equivalent, so we:

1. Extract all definitions into a ``dict`` for downstream use.
2. Strip the definition lines from the markdown so the parser never sees them.

The downstream :mod:`mkdocs_to_confluence.transforms.abbrevs` module uses the
collected definitions to expand the first occurrence of each abbreviation in
safe body content and appends a Glossary section for any that only appeared in
headings or other non-expandable contexts.
"""

from __future__ import annotations

import re

# Matches: *[ABBR]: definition
# Groups: 1=abbreviation, 2=definition
_ABBR_DEF_RE = re.compile(r"^\*\[([^\]]+)\]:\s*(.+?)\s*$", re.MULTILINE)


def extract_abbreviations(text: str) -> dict[str, str]:
    """Return a ``{abbreviation: definition}`` mapping from *text*.

    Only collects ``*[ABBR]: definition`` lines; the rest of the text is
    ignored.  Later duplicates overwrite earlier ones (last definition wins).
    """
    return {m.group(1): m.group(2) for m in _ABBR_DEF_RE.finditer(text)}


def strip_abbreviation_defs(text: str) -> str:
    """Remove all ``*[ABBR]: definition`` lines from *text*.

    The lines are dropped entirely (including their trailing newline) so that
    the parser never sees dangling ``*[…]`` syntax.
    """
    return _ABBR_DEF_RE.sub("", text)
