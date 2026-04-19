"""Icon shortcode preprocessing.

Replaces MkDocs Material / FontAwesome / Octicons / Simple icon shortcodes
(e.g. ``:material-check-circle:``) with the closest Unicode/emoji equivalent,
or strips them silently when no mapping is found.

Strategy: split the icon name on ``-`` and test each part against a small
keyword→emoji table.  The first matching keyword wins.  This keeps the
mapping set tiny and maintainable without requiring a full icon inventory.
"""

from __future__ import annotations

import re

# Matches :prefix-icon-name: for all common MkDocs icon families.
_ICON_RE = re.compile(
    r":(?:material|fontawesome|octicons|simple|twemoji)-[a-z0-9-]+:"
)

# Keyword → emoji.  Keys must be lowercase single words (icon name segments).
# Ordered so earlier, more-specific entries take priority where ambiguous.
_KEYWORD_MAP: dict[str, str | None] = {
    # Status / validation
    "check": "✅",
    "done": "✅",
    "complete": "✅",
    "success": "✅",
    "verified": "✅",
    "close": "❌",
    "cancel": "❌",
    "times": "❌",
    "alert": "⚠️",
    "warning": "⚠️",
    "warn": "⚠️",
    "caution": "⚠️",
    "information": "ℹ️",
    "info": "ℹ️",
    "question": "❓",
    "help": "❓",
    "exclamation": "❗",
    # Navigation / directional
    "arrow": None,          # resolved with next segment — see _resolve()
    "chevron": None,
    # Security
    "lock": "🔒",
    "security": "🔒",
    "shield": "🔒",
    "unlock": "🔓",
    "key": "🔑",
    # Actions
    "download": "⬇️",
    "upload": "⬆️",
    "refresh": "🔄",
    "sync": "🔄",
    "reload": "🔄",
    "search": "🔍",
    "magnify": "🔍",
    "edit": "✏️",
    "pencil": "✏️",
    "pen": "✏️",
    "copy": "📋",
    "clipboard": "📋",
    "trash": "🗑️",
    "delete": "🗑️",
    "add": "➕",
    "plus": "➕",
    "minus": "➖",
    "link": "🔗",
    "chain": "🔗",
    # Objects / content
    "star": "⭐",
    "favorite": "⭐",
    "bookmark": "🔖",
    "heart": "❤️",
    "fire": "🔥",
    "rocket": "🚀",
    "launch": "🚀",
    "home": "🏠",
    "settings": "⚙️",
    "cog": "⚙️",
    "gear": "⚙️",
    "wrench": "🔧",
    "email": "📧",
    "mail": "📧",
    "envelope": "📧",
    "phone": "📞",
    "clock": "🕐",
    "time": "🕐",
    "calendar": "📅",
    "date": "📅",
    "folder": "📁",
    "file": "📄",
    "document": "📄",
    "code": "💻",
    "terminal": "💻",
    "database": "🗄️",
    "cloud": "☁️",
    "globe": "🌍",
    "world": "🌍",
    "earth": "🌍",
    "chart": "📊",
    "graph": "📊",
    "book": "📖",
    "docs": "📖",
    "note": "📝",
    "tag": "🏷️",
    "label": "🏷️",
    "flag": "🚩",
    "eye": "👁️",
    "view": "👁️",
    "user": "👤",
    "account": "👤",
    "person": "👤",
    "group": "👥",
    "people": "👥",
    "team": "👥",
    "robot": "🤖",
    "bug": "🐛",
    "test": "🧪",
    "flask": "🧪",
    "lightbulb": "💡",
    "idea": "💡",
    "package": "📦",
    "server": "🖥️",
    "network": "🌐",
    "wifi": "📶",
    "battery": "🔋",
    "image": "🖼️",
    "video": "🎬",
    "music": "🎵",
    "printer": "🖨️",
    "keyboard": "⌨️",
    "mouse": "🖱️",
    "monitor": "🖥️",
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
