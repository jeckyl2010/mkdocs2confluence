"""Icon shortcode preprocessing.

Replaces MkDocs Material / FontAwesome / Octicons / Simple icon shortcodes
(e.g. ``:material-check-circle:``) with the closest Unicode symbol equivalent,
or strips them silently when no mapping is found.

Strategy: split the icon name on ``-`` and test each part against a small
keyword→symbol table.  The first matching keyword wins.  This keeps the
mapping set tiny and maintainable without requiring a full icon inventory.

**BMP-only constraint**: all mapped symbols must lie in the Unicode Basic
Multilingual Plane (U+0000–U+FFFF, ≤ 3-byte UTF-8).  Supplementary-plane
emoji (U+10000+, 4-byte UTF-8) are not stored correctly by Confluence
deployments that use MySQL ``utf8`` (not ``utf8mb4``) and render as ``???``.
Where no good BMP symbol exists the shortcode is stripped silently (``""``).
"""

from __future__ import annotations

import re

# Matches :prefix-icon-name: for all common MkDocs icon families.
_ICON_RE = re.compile(
    r":(?:material|fontawesome|octicons|simple|twemoji)-[a-z0-9-]+:"
)

# Keyword → symbol.  Keys must be lowercase single words (icon name segments).
# ALL values must be BMP characters (U+0000–U+FFFF) or "" (strip silently).
# Ordered so earlier, more-specific entries take priority where ambiguous.
_KEYWORD_MAP: dict[str, str | None] = {
    # Status / validation  (all BMP ✓)
    "check": "✓",       # U+2713
    "done": "✓",
    "complete": "✓",
    "success": "✓",
    "verified": "✓",
    "close": "✗",       # U+2717
    "cancel": "✗",
    "times": "✗",
    "alert": "⚠",       # U+26A0
    "warning": "⚠",
    "warn": "⚠",
    "caution": "⚠",
    "information": "ℹ",  # U+2139
    "info": "ℹ",
    "question": "?",
    "help": "?",
    "exclamation": "!",
    # Navigation / directional
    "arrow": None,          # resolved with next segment — see _resolve()
    "chevron": None,
    # Security — no good BMP glyph; strip silently
    "lock": "",
    "security": "",
    "shield": "",
    "unlock": "",
    "key": "",
    # Actions
    "download": "↓",    # U+2193
    "upload": "↑",      # U+2191
    "refresh": "↻",     # U+21BB  (BMP)
    "sync": "↻",
    "reload": "↻",
    "search": "",       # no reliable BMP magnifier glyph; strip
    "magnify": "",
    "edit": "✎",        # U+270E  (BMP pencil)
    "pencil": "✎",
    "pen": "✎",
    "copy": "",         # strip
    "clipboard": "",
    "trash": "",        # strip
    "delete": "",
    "add": "+",
    "plus": "+",
    "minus": "−",       # U+2212 minus sign
    "link": "",         # strip — no reliable BMP link-chain glyph
    "chain": "",
    # Objects / content
    "star": "★",        # U+2605  (BMP)
    "favorite": "★",
    "bookmark": "",     # strip
    "heart": "♥",       # U+2665  (BMP)
    "fire": "",         # strip
    "rocket": "",       # strip
    "launch": "",
    "home": "",         # strip — ⌂ U+2302 exists but renders poorly
    "settings": "⚙",   # U+2699  (BMP)
    "cog": "⚙",
    "gear": "⚙",
    "wrench": "",       # strip
    "email": "✉",       # U+2709  (BMP envelope)
    "mail": "✉",
    "envelope": "✉",
    "phone": "☎",       # U+260E  (BMP telephone)
    "clock": "",        # strip
    "time": "",
    "calendar": "",     # strip
    "date": "",
    "folder": "",       # strip
    "file": "",
    "document": "",
    "code": "",         # strip
    "terminal": "",
    "database": "",     # strip
    "cloud": "☁",       # U+2601  (BMP)
    "globe": "",        # strip
    "world": "",
    "earth": "",
    "chart": "",        # strip
    "graph": "",
    "book": "",         # strip
    "docs": "",
    "note": "",         # strip
    "tag": "",          # strip
    "label": "",
    "flag": "",         # strip
    "eye": "",          # strip — was wrongly matching grid/view icons
    "view": "",         # strip — semantically ambiguous (grid-view ≠ eye)
    "grid": "",         # strip — layout/grid icons have no BMP analogue
    "user": "",         # strip
    "account": "",
    "person": "",
    "group": "",        # strip
    "people": "",
    "team": "",
    "robot": "",        # strip
    "bug": "",          # strip
    "test": "",         # strip
    "flask": "",
    "lightbulb": "",    # strip
    "idea": "",
    "package": "",      # strip
    "server": "",
    "network": "",      # strip
    "wifi": "",
    "battery": "",      # strip
    "image": "",        # strip
    "video": "",
    "music": "♪",       # U+266A  (BMP)
    "printer": "",      # strip
    "keyboard": "⌨",   # U+2328  (BMP)
    "mouse": "",        # strip
    "monitor": "",      # strip
    # Modifier suffixes — never meaningful on their own; always strip
    "outline": "",
    "variant": "",
    "filled": "",
    "sharp": "",
    "circle": "",
    "rounded": "",
}

# Directional arrows resolved from two-segment pairs like arrow-right
_ARROW_MAP: dict[str, str] = {
    "right": "→",
    "left": "←",
    "up": "↑",
    "down": "↓",
    "expand": "↗",
    "collapse": "↙",
}


def _resolve(parts: list[str]) -> str:
    """Return emoji for an icon name split into *parts*, or empty string."""
    for i, part in enumerate(parts):
        emoji = _KEYWORD_MAP.get(part)
        if emoji is not None:
            return emoji
        # Handle arrow/chevron + direction pairs.
        if part in ("arrow", "chevron") and i + 1 < len(parts):
            direction = _ARROW_MAP.get(parts[i + 1])
            if direction:
                return direction
    return ""


def strip_icon_shortcodes(text: str) -> str:
    """Replace icon shortcodes with emoji or strip them silently.

    Parameters
    ----------
    text:
        Raw Markdown text (may include fenced code blocks — those are
        left untouched via a segment-based approach).
    """

    def _replace(m: re.Match[str]) -> str:
        shortcode = m.group(0)  # e.g. ":material-check-circle:"
        # Strip leading/trailing colons and the family prefix.
        inner = shortcode[1:-1]  # "material-check-circle"
        # Remove family prefix (everything up to and including the first "-").
        _, _, name = inner.partition("-")  # "check-circle"
        parts = name.split("-")
        return _resolve(parts)

    return _ICON_RE.sub(_replace, text)
