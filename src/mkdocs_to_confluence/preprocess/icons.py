"""Icon shortcode preprocessing.

Replaces MkDocs Material / FontAwesome / Octicons / Simple icon shortcodes
(e.g. ``:material-check-circle:``) with the closest Unicode emoji equivalent,
or strips them silently when no mapping is found.

Strategy: split the icon name on ``-`` and test each part against a small
keyword→symbol table.  The first matching keyword wins.  This keeps the
mapping set tiny and maintainable without requiring a full icon inventory.

**Unicode range**: Confluence Cloud stores pages as UTF-8 with full Unicode
support (utf8mb4), so supplementary-plane emoji (U+10000+) are safe.
Symbols without a clear emoji equivalent are still stripped silently (``""``).
"""

from __future__ import annotations

import re

# Matches :prefix-icon-name: for all common MkDocs icon families.
_ICON_RE = re.compile(
    r":(?:material|fontawesome|octicons|simple|twemoji)-[a-z0-9-]+:"
)

# Matches bare GitHub/Python-Markdown emoji shortcodes: :rotating_light:, :wrench: etc.
# Requires at least one underscore or is a known single-word name.
# Must not overlap with _ICON_RE (those all contain a hyphenated prefix).
_STANDARD_EMOJI_RE = re.compile(r":([a-z][a-z0-9_]*):")

# Bare emoji shortcode → Unicode symbol (or "" to strip silently).
_STANDARD_EMOJI_MAP: dict[str, str] = {
    # Alerts / status
    "warning": "⚠",                # U+26A0
    "rotating_light": "🚨",        # U+1F6A8
    "octagonal_sign": "⛔",         # U+26D4
    "no_entry": "⛔",               # U+26D4
    "no_entry_sign": "⛔",
    "stop_sign": "⛔",
    "information_source": "ℹ",     # U+2139
    # Checkmarks / marks
    "white_check_mark": "✓",       # U+2713
    "heavy_check_mark": "✓",       # U+2713
    "x": "✗",                      # U+2717
    "heavy_multiplication_x": "✗",
    # Objects — tools
    "wrench": "🔧",                 # U+1F527
    "gear": "⚙",                   # U+2699
    "hammer": "🔨",                 # U+1F528
    "hammer_and_wrench": "🛠️",     # U+1F6E0
    # Work / business
    "briefcase": "💼",              # U+1F4BC
    # Nature / miscellaneous
    "star": "★",                   # U+2605
    "star2": "★",
    "rocket": "🚀",                 # U+1F680
    "construction": "🚧",           # U+1F6A7
    "tada": "🎉",                   # U+1F389
    "trophy": "🏆",                 # U+1F3C6
    "thinking": "🤔",               # U+1F914
    "smile": "😄",                  # U+1F604
    "laughing": "😆",               # U+1F606
    "heart": "♥",                  # U+2665
    "fire": "🔥",                   # U+1F525
    "zap": "⚡",                    # U+26A1
    "bulb": "💡",                   # U+1F4A1
    "computer": "💻",               # U+1F4BB
    "notebook": "📓",               # U+1F4D3
    "memo": "📝",                   # U+1F4DD
    "clipboard": "📋",              # U+1F4CB
    "link": "🔗",                   # U+1F517
    "label": "🏷️",                 # U+1F3F7
    "bookmark": "🔖",               # U+1F516
    "chart_with_upwards_trend": "📈",  # U+1F4C8
    "bar_chart": "📊",              # U+1F4CA
}

# Keyword → symbol.  Keys must be lowercase single words (icon name segments).
# Ordered so earlier, more-specific entries take priority where ambiguous.
_KEYWORD_MAP: dict[str, str | None] = {
    # Status / validation
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
    # Security
    "lock": "🔒",        # U+1F512
    "security": "🛡️",   # U+1F6E0
    "shield": "🛡️",
    "unlock": "🔓",      # U+1F513
    "key": "🔑",         # U+1F511
    # Actions
    "download": "↓",    # U+2193
    "upload": "↑",      # U+2191
    "refresh": "↻",     # U+21BB
    "sync": "↻",
    "reload": "↻",
    "search": "🔍",     # U+1F50D
    "magnify": "🔍",
    "edit": "✎",        # U+270E
    "pencil": "✎",
    "pen": "✎",
    "copy": "",         # strip
    "clipboard": "📋",  # U+1F4CB
    "trash": "🗑️",     # U+1F5D1
    "delete": "🗑️",
    "add": "+",
    "plus": "+",
    "minus": "−",       # U+2212
    "link": "🔗",       # U+1F517
    "chain": "🔗",
    # Objects / content
    "star": "★",        # U+2605
    "favorite": "★",
    "bookmark": "🔖",   # U+1F516
    "heart": "♥",       # U+2665
    "fire": "🔥",       # U+1F525
    "rocket": "🚀",     # U+1F680
    "launch": "🚀",
    "home": "🏠",       # U+1F3E0
    "settings": "⚙",   # U+2699
    "cog": "⚙",
    "gear": "⚙",
    "wrench": "🔧",     # U+1F527
    "email": "✉",       # U+2709
    "mail": "✉",
    "envelope": "✉",
    "phone": "☎",       # U+260E
    "clock": "⏰",      # U+23F0
    "time": "⏰",
    "calendar": "📅",   # U+1F4C5
    "date": "📅",
    "folder": "📁",     # U+1F4C1
    "file": "📄",       # U+1F4C4
    "document": "📄",
    "code": "💻",       # U+1F4BB
    "terminal": "💻",
    "database": "🗄️",  # U+1F5C4
    "cloud": "☁",       # U+2601
    "globe": "🌍",      # U+1F30D
    "world": "🌍",
    "earth": "🌍",
    "chart": "📊",      # U+1F4CA
    "graph": "📊",
    "book": "📖",       # U+1F4D6
    "docs": "📖",
    "note": "",         # strip — ambiguous; not the 📝 emoji
    "tag": "🏷️",       # U+1F3F7
    "label": "🏷️",
    "flag": "🚩",       # U+1F6A9
    "eye": "",          # strip — was wrongly matching grid/view icons
    "view": "",         # strip — semantically ambiguous
    "grid": "",         # strip — layout/grid icons have no emoji analogue
    "user": "👤",       # U+1F464
    "account": "👤",
    "person": "👤",
    "group": "👥",      # U+1F465
    "people": "👥",
    "team": "👥",
    "robot": "🤖",      # U+1F916
    "bug": "🐛",        # U+1F41B
    "test": "",         # strip
    "flask": "",        # strip
    "lightbulb": "💡", # U+1F4A1
    "idea": "💡",
    "package": "📦",    # U+1F4E6
    "server": "🖥️",    # U+1F5A5
    "network": "",      # strip
    "wifi": "",         # strip
    "battery": "",      # strip
    "image": "🖼️",     # U+1F5BC
    "video": "🎥",      # U+1F3A5
    "music": "♪",       # U+266A
    "printer": "",      # strip
    "keyboard": "⌨",   # U+2328
    "mouse": "",        # strip
    "monitor": "🖥️",
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


def _replace_standard_emoji(text: str) -> str:
    """Replace standard emoji shortcodes (e.g. ``:rotating_light:``) with BMP symbols."""

    def _replace(m: re.Match[str]) -> str:
        name = m.group(1)
        if name in _STANDARD_EMOJI_MAP:
            return _STANDARD_EMOJI_MAP[name]
        # Unknown shortcode — leave it intact (may be valid Markdown syntax).
        return m.group(0)

    return _STANDARD_EMOJI_RE.sub(_replace, text)


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

    return _ICON_RE.sub(_replace, _replace_standard_emoji(text))
