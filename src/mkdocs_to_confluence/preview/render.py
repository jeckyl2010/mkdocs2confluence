"""Convert Confluence storage XHTML to browser-renderable HTML for local preview.

Confluence uses proprietary XML elements (``<ac:structured-macro>``,
``<ac:plain-text-body>``, ``<ac:rich-text-body>``, etc.) that browsers cannot
render.  This module translates the most common ones into styled HTML so
authors can visually check a page without a running Confluence instance.

Supported macros
----------------
* ``code``    → ``<pre><code>`` with optional title header
* ``info``    → blue info panel
* ``tip``     → green tip panel
* ``warning`` → orange warning panel
* ``note``    → grey note panel
* ``expand``  → ``<details>/<summary>``
* everything else → visible "unsupported macro" placeholder
"""

from __future__ import annotations

import html as _html
import re

# ── Regex patterns ────────────────────────────────────────────────────────────

# Matches the innermost macro only (body contains no nested <ac:structured-macro).
# The negative lookahead (?!<ac:structured-macro) prevents consuming into a
# nested macro, so inner macros are always replaced before outer ones.
_MACRO_RE = re.compile(
    r'<ac:structured-macro\s+ac:name="(?P<name>[^"]+)"[^>]*>'
    r"(?P<body>(?:(?!<ac:structured-macro)[\s\S])*?)"
    r"</ac:structured-macro>",
)

_PARAM_RE = re.compile(
    r'<ac:parameter\s+ac:name="([^"]+)">([^<]*)</ac:parameter>'
)

_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)

_RICH_BODY_RE = re.compile(
    r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", re.DOTALL
)

# ── Internal helpers ──────────────────────────────────────────────────────────


def _params(macro_body: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _PARAM_RE.finditer(macro_body)}


def _cdata(macro_body: str) -> str:
    m = _CDATA_RE.search(macro_body)
    return m.group(1) if m else ""


def _rich_body(macro_body: str) -> str:
    m = _RICH_BODY_RE.search(macro_body)
    return m.group(1).strip() if m else ""


# ── Macro renderers ───────────────────────────────────────────────────────────

_PANEL_COLOURS: dict[str, tuple[str, str, str]] = {
    #          border       background   title-bg
    "info":    ("#0052cc",  "#deebff",   "#0052cc"),
    "tip":     ("#006644",  "#e3fcef",   "#006644"),
    "warning": ("#ff8b00",  "#fffae6",   "#ff8b00"),
    "note":    ("#505f79",  "#f4f5f7",   "#505f79"),
}


def _render_code(params: dict[str, str], body: str) -> str:
    lang = params.get("language", "")
    title = params.get("title", "")
    code = _cdata(body)
    title_html = (
        f'<div class="code-title">{_html.escape(title)}</div>' if title else ""
    )
    lang_class = f' class="language-{_html.escape(lang)}"' if lang else ""
    lang_label = (
        f'<span class="code-lang">{_html.escape(lang)}</span>' if lang else ""
    )
    return (
        f'<div class="code-block">'
        f'<div class="code-header">{lang_label}{title_html}</div>'
        f"<pre><code{lang_class}>{_html.escape(code)}</code></pre>"
        f"</div>"
    )


def _render_panel(name: str, params: dict[str, str], body: str) -> str:
    default_title = name.capitalize()
    title = params.get("title", default_title)
    content = render_html(_rich_body(body))
    border, bg, title_bg = _PANEL_COLOURS.get(name, ("#505f79", "#f4f5f7", "#505f79"))
    return (
        f'<div class="panel" style="border-left:4px solid {border};background:{bg};'
        f'margin:1em 0;border-radius:0 4px 4px 0;">'
        f'<div class="panel-title" style="background:{title_bg};color:#fff;'
        f'padding:4px 12px;font-weight:600;font-size:0.85em;border-radius:0 4px 0 0;">'
        f"{_html.escape(title)}</div>"
        f'<div class="panel-body" style="padding:8px 12px;">{content}</div>'
        f"</div>"
    )


def _render_expand(params: dict[str, str], body: str) -> str:
    title = params.get("title", "Details")
    content = render_html(_rich_body(body))
    return (
        f'<details style="border:1px solid #dfe1e6;border-radius:4px;'
        f'margin:0.5em 0;padding:4px 12px;">'
        f"<summary style=\"cursor:pointer;font-weight:600;padding:4px 0;\">"
        f"{_html.escape(title)}</summary>"
        f"<div style=\"padding-top:8px;\">{content}</div>"
        f"</details>"
    )


def _render_macro(m: re.Match[str]) -> str:
    name = m.group("name")
    body = m.group("body")
    p = _params(body)

    if name == "code":
        return _render_code(p, body)
    if name in _PANEL_COLOURS:
        return _render_panel(name, p, body)
    if name == "expand":
        return _render_expand(p, body)

    return (
        f'<div style="border:1px dashed #aaa;padding:8px;margin:0.5em 0;'
        f'color:#888;font-style:italic;">[{_html.escape(name)} macro]</div>'
    )


# ── Public API ────────────────────────────────────────────────────────────────

_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 860px; margin: 48px auto; padding: 0 24px;
  color: #172b4d; line-height: 1.6;
}
h1,h2,h3,h4,h5,h6 { color: #0052cc; margin-top: 1.5em; }
h1 { font-size: 1.9em; } h2 { font-size: 1.4em; } h3 { font-size: 1.1em; }
a { color: #0052cc; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #dfe1e6; padding: 8px 12px; text-align: left; }
th { background: #f4f5f7; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
blockquote {
  border-left: 4px solid #0052cc; margin: 1em 0;
  padding: 8px 16px; background: #deebff; border-radius: 0 4px 4px 0;
}
code {
  background: #f4f5f7; padding: 2px 5px;
  border-radius: 3px; font-family: monospace; font-size: 0.88em;
}
.code-block { background: #1e1e1e; border-radius: 4px; margin: 1em 0; overflow: hidden; }
.code-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 12px; background: #2d2d2d;
}
.code-lang { color: #a0a0a0; font-size: 0.78em; font-family: monospace; }
.code-title { color: #ccc; font-size: 0.82em; }
.code-block pre {
  margin: 0; padding: 12px 16px; overflow-x: auto;
  background: transparent;
}
.code-block pre code {
  background: transparent; color: #d4d4d4;
  font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.88em;
  padding: 0;
}
ul, ol { padding-left: 1.5em; }
li { margin: 4px 0; }
hr { border: none; border-top: 1px solid #dfe1e6; margin: 1.5em 0; }
"""


def render_html(xhtml: str) -> str:
    """Translate Confluence XHTML macros into browser-renderable HTML.

    Iterates until no more macros remain (handles nested macros such as a
    code block inside a warning panel).
    """
    prev: str | None = None
    result = xhtml
    while result != prev:
        prev = result
        result = _MACRO_RE.sub(_render_macro, result)
    return result


def render_page(xhtml: str, page: str = "") -> str:
    """Wrap rendered HTML in a full browser page with Confluence-like styles."""
    body = render_html(xhtml)
    escaped_page = _html.escape(page)
    return (
        f'<!DOCTYPE html>\n<html>\n<head>\n'
        f'<meta charset="utf-8">\n'
        f'<title>mk2conf preview{f" — {escaped_page}" if page else ""}</title>\n'
        f"<style>{_CSS}</style>\n"
        f"</head>\n<body>\n"
        f"{body}\n"
        f"</body>\n</html>\n"
    )
