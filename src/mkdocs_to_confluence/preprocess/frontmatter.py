"""Extract and map YAML front matter from raw MkDocs markdown.

MkDocs pages optionally start with a YAML front matter block::

    ---
    title: "My Page"
    author: "Alice"
    tags: [arch, api]
    ---

    Page content starts here.

This module:

1. Detects and parses the front matter block.
2. Maps raw fields to a :class:`FrontMatter` IR node that the emitter can
   render as a Confluence **Page Properties** (``details``) macro.
3. Returns the remaining markdown text with the front matter block stripped.

Field mapping
-------------
=============  =============  ================================================
Front matter   Display name   Notes
=============  =============  ================================================
``title``      Title          Confluence page title on publish; shown in table
``subtitle``   —              Rendered as italic lead paragraph (not in table)
``documentId`` Document ID    —
``version``    Version        —
``lastUpdated``Last Updated   —
``author``     Author         —
``tags``       Tags           Also stored as Confluence labels
``ready``      Status         ``true`` → "✅ Ready", ``false`` → "📝 Draft"
``source``     —              **Stripped** (internal tooling field)
*other*        Title-cased    Stringified value
=============  =============  ================================================
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from mkdocs_to_confluence.ir.nodes import FrontMatter

# ── Constants ─────────────────────────────────────────────────────────────────

# Fields that carry no meaning in Confluence and should be discarded silently.
# ``status`` is consumed as a publishing directive (sets the Confluence page
# status via the API) and must not appear in the Page Properties table.
_STRIP_FIELDS: frozenset[str] = frozenset({"source", "status"})

# Fields whose value has special formatting logic (see _format_value).
_DISPLAY_NAMES: dict[str, str] = {
    "title": "Title",
    "documentId": "Document ID",
    "version": "Version",
    "lastUpdated": "Last Updated",
    "author": "Author",
    "tags": "Tags",
    "ready": "Status",
    "subtitle": "Subtitle",
}

# Preferred field order in the properties table.
_FIELD_ORDER: list[str] = [
    "title",
    "documentId",
    "version",
    "lastUpdated",
    "author",
    "tags",
    "ready",
]

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n?)---\s*\n?", re.DOTALL)


# ── Public API ────────────────────────────────────────────────────────────────


def extract_front_matter(text: str) -> tuple[FrontMatter | None, str]:
    """Parse YAML front matter from the top of *text*.

    Args:
        text: Raw markdown content.

    Returns:
        A ``(FrontMatter | None, remaining_text)`` tuple.  ``FrontMatter`` is
        ``None`` when no front matter block is present.  ``remaining_text`` is
        the markdown content after the ``---`` block.
    """
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return None, text

    remaining = text[m.end():]

    try:
        raw: object = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, text

    if not isinstance(raw, dict):
        return None, text

    return _build_node(raw), remaining


# ── Private helpers ───────────────────────────────────────────────────────────


def _build_node(raw: dict[str, Any]) -> FrontMatter:
    """Convert a raw front matter dict to a :class:`FrontMatter` IR node."""
    print(f"  [debug-fm] raw keys: {list(raw.keys())}")
    title: str | None = _stringify(raw.get("title")) if "title" in raw else None
    subtitle: str | None = _stringify(raw.get("subtitle")) if "subtitle" in raw else None

    # ``status:`` sets the Confluence page lifecycle status via the API.
    status_raw = raw.get("status")
    confluence_status: str | None = str(status_raw) if status_raw is not None else None

    # Labels come from the ``tags`` field.
    tags_raw = raw.get("tags", [])
    labels: tuple[str, ...] = tuple(str(t) for t in (tags_raw if isinstance(tags_raw, list) else [tags_raw]))

    # Build ordered properties table (skip subtitle and stripped fields).
    properties: list[tuple[str, str]] = []
    seen: set[str] = set()

    for key in _FIELD_ORDER:
        if key in raw and key not in _STRIP_FIELDS and key != "subtitle":
            display = _DISPLAY_NAMES.get(key, _humanize(key))
            properties.append((display, _format_value(key, raw[key])))
            seen.add(key)

    # Append any remaining unknown fields in document order.
    for key, value in raw.items():
        if key in seen or key in _STRIP_FIELDS or key == "subtitle":
            continue
        display = _DISPLAY_NAMES.get(key, _humanize(key))
        properties.append((display, _format_value(key, value)))

    return FrontMatter(
        title=title,
        subtitle=subtitle,
        properties=tuple(properties),
        labels=labels,
        confluence_status=confluence_status,
    )


def _format_value(key: str, value: Any) -> str:
    """Return a human-friendly string representation of a front matter value."""
    if key == "ready":
        return "✅ Ready" if value else "📝 Draft"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _humanize(key: str) -> str:
    """Convert camelCase or snake_case key to a Title Case display name."""
    # Insert a space before each uppercase letter sequence.
    spaced = re.sub(r"([A-Z]+)", r" \1", key).strip()
    # Replace underscores with spaces.
    spaced = spaced.replace("_", " ")
    return spaced.title()
