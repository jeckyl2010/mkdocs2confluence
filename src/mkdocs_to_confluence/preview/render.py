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

import base64
import html as _html
import re
from pathlib import Path

# ── Regex patterns ────────────────────────────────────────────────────────────

# ac:layout tag patterns — converted to flex-box HTML divs.
_AC_LAYOUT_CELL_OPEN_RE = re.compile(r"<ac:layout-cell>")
_AC_LAYOUT_CELL_CLOSE_RE = re.compile(r"</ac:layout-cell>")
_AC_LAYOUT_SECTION_OPEN_RE = re.compile(r'<ac:layout-section\s+ac:type="([^"]+)">')
_AC_LAYOUT_SECTION_CLOSE_RE = re.compile(r"</ac:layout-section>")
_AC_LAYOUT_OPEN_RE = re.compile(r"<ac:layout>")
_AC_LAYOUT_CLOSE_RE = re.compile(r"</ac:layout>")

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

# Matches <ac:image ...>...</ac:image> blocks (single or multi-line).
_IMAGE_RE = re.compile(
    r'<ac:image(?P<attrs>[^>]*)>(?P<body>.*?)</ac:image>', re.DOTALL
)
_RI_URL_RE = re.compile(r'<ri:url\s+ri:value="(?P<src>[^"]+)"\s*/>')
_RI_ATTACH_RE = re.compile(r'<ri:attachment\s+ri:filename="(?P<name>[^"]+)"\s*/>')
_AC_ALT_RE = re.compile(r'ac:alt="(?P<alt>[^"]*)"')
_AC_TITLE_RE = re.compile(r'ac:title="(?P<title>[^"]*)"')
_DATA_LOCAL_PATH_RE = re.compile(r'data-local-path="(?P<path>[^"]*)"')

# Matches <ac:link ...>...</ac:link> blocks for cross-page link rewriting.
_AC_LINK_RE = re.compile(r'<ac:link(?P<link_attrs>[^>]*)>(?P<link_body>.*?)</ac:link>', re.DOTALL)
_RI_PAGE_TITLE_RE = re.compile(r'ri:content-title="(?P<title>[^"]*)"')
_AC_LINK_BODY_RE = re.compile(r'<ac:link-body>(.*?)</ac:link-body>', re.DOTALL)
_AC_ANCHOR_ATTR_RE = re.compile(r'ac:anchor="(?P<anchor>[^"]*)"')

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
    if name == "panel":
        # Custom-coloured panel (used for danger/error/bug kinds).
        border = params.get("borderColor", "#505f79")
        bg = params.get("bgColor", "#f4f5f7")
        title_bg = params.get("titleBGColor", border)
        title = params.get("title", "")
    else:
        default_title = name.capitalize()
        title = params.get("title", default_title)
        border, bg, title_bg = _PANEL_COLOURS.get(name, ("#505f79", "#f4f5f7", "#505f79"))
    content = render_html(_rich_body(body))
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


def _render_details(body: str) -> str:
    """Render the Confluence Page Properties (``details``) macro as a styled card."""
    content = render_html(_rich_body(body))
    return (
        '<div style="border:1px solid #dfe1e6;border-radius:4px;margin:1em 0;'
        'overflow:hidden;">'
        '<div style="background:#f4f5f7;padding:6px 12px;font-weight:600;'
        'font-size:0.85em;color:#505f79;border-bottom:1px solid #dfe1e6;">'
        "📋 Page Properties</div>"
        f'<div style="padding:0 12px;">{content}</div>'
        "</div>"
    )


def _render_macro(m: re.Match[str]) -> str:
    name = m.group("name")
    body = m.group("body")
    p = _params(body)

    if name == "code":
        return _render_code(p, body)
    if name in _PANEL_COLOURS or name == "panel":
        return _render_panel(name, p, body)
    if name == "expand":
        return _render_expand(p, body)
    if name == "details":
        return _render_details(body)

    return (
        f'<div style="border:1px dashed #aaa;padding:8px;margin:0.5em 0;'
        f'color:#888;font-style:italic;">[{_html.escape(name)} macro]</div>'
    )


def _render_layout(html: str) -> str:
    """Convert ``ac:layout`` / ``ac:layout-section`` / ``ac:layout-cell`` to flex HTML."""
    html = _AC_LAYOUT_CELL_OPEN_RE.sub('<div class="ac-layout-cell">', html)
    html = _AC_LAYOUT_CELL_CLOSE_RE.sub("</div>", html)
    html = _AC_LAYOUT_SECTION_OPEN_RE.sub(
        lambda m: f'<div class="ac-layout-section ac-{m.group(1).replace("_", "-")}">',
        html,
    )
    html = _AC_LAYOUT_SECTION_CLOSE_RE.sub("</div>", html)
    html = _AC_LAYOUT_OPEN_RE.sub('<div class="ac-layout">', html)
    html = _AC_LAYOUT_CLOSE_RE.sub("</div>", html)
    return html


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
dl { margin: 1em 0; }
dt { font-weight: 600; margin-top: 0.5em; }
dd { margin-left: 2em; margin-top: 2px; }
.ac-layout { margin: 1em 0; }
.ac-layout-section { display: flex; gap: 16px; flex-wrap: wrap; }
.ac-layout-cell {
  flex: 1; min-width: 180px; padding: 12px;
  background: #fafbfc; border: 1px solid #dfe1e6; border-radius: 4px;
}
"""


def _render_image(m: re.Match[str]) -> str:
    """Convert ``<ac:image>`` to an ``<img>`` tag for browser preview."""
    attrs = m.group("attrs")
    body = m.group("body")

    alt_m = _AC_ALT_RE.search(attrs)
    title_m = _AC_TITLE_RE.search(attrs)
    local_m = _DATA_LOCAL_PATH_RE.search(attrs)
    alt = _html.escape(alt_m.group("alt")) if alt_m else ""
    title = _html.escape(title_m.group("title")) if title_m else ""

    style = "max-width:100%;height:auto;margin:0.5em 0;"
    title_attr = f' title="{title}"' if title else ""

    url_m = _RI_URL_RE.search(body)
    attach_m = _RI_ATTACH_RE.search(body)

    if url_m:
        src = url_m.group("src")
        if not src.startswith(("http://", "https://", "data:")):
            data = _load_image_data(Path(src))
            if data:
                return f'<img src="{data}" alt="{alt}"{title_attr} style="{style}">'
        return f'<img src="{_html.escape(src)}" alt="{alt}"{title_attr} style="{style}">'

    if attach_m:
        # Use data-local-path if present (set by emitter for local files)
        if local_m:
            data = _load_image_data(Path(local_m.group("path")))
            if data:
                return f'<img src="{data}" alt="{alt}"{title_attr} style="{style}">'
        name = attach_m.group("name")
        return (
            f'<div style="border:1px dashed #aaa;padding:0.5em;color:#666;'
            f'font-style:italic;">📎 Attachment: {_html.escape(name)}</div>'
        )

    return m.group(0)


def _load_image_data(path: Path) -> str:
    """Return a base64 data URI for a local image file, or empty string."""
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def render_html(xhtml: str, page_link_map: dict[str, str] | None = None) -> str:
    """Translate Confluence XHTML macros into browser-renderable HTML.

    Iterates until no more macros remain (handles nested macros such as a
    code block inside a warning panel).

    Parameters
    ----------
    page_link_map:
        Optional ``{page_title: html_filename}`` map.  When provided,
        ``<ac:link>`` cross-page references are rewritten to relative
        ``<a href="...">`` links so previewed pages are navigable.
    """
    prev: str | None = None
    result = xhtml
    while result != prev:
        prev = result
        result = _MACRO_RE.sub(_render_macro, result)
    result = _render_layout(result)
    result = _IMAGE_RE.sub(_render_image, result)
    if page_link_map:
        result = _rewrite_page_links(result, page_link_map)
    return result


def _rewrite_page_links(html: str, page_link_map: dict[str, str]) -> str:
    """Replace ``<ac:link>`` elements with HTML ``<a>`` tags."""
    def _replace(m: re.Match[str]) -> str:
        link_attrs = m.group("link_attrs")
        link_body = m.group("link_body")

        title_m = _RI_PAGE_TITLE_RE.search(link_body)
        body_m = _AC_LINK_BODY_RE.search(link_body)
        anchor_m = _AC_ANCHOR_ATTR_RE.search(link_attrs)

        label = body_m.group(1).strip() if body_m else ""
        anchor = f"#{_html.escape(anchor_m.group('anchor'))}" if anchor_m else ""

        if title_m:
            title = title_m.group("title")
            fname = page_link_map.get(title)
            if fname:
                return f'<a href="{_html.escape(fname)}{anchor}">{label}</a>'
            return (
                f'<a href="#" style="color:#c00;text-decoration:line-through;" '
                f'title="Page not in section: {_html.escape(title)}">{label}</a>'
            )

        # Anchor-only link (same-page heading reference)
        if anchor_m:
            return f'<a href="{anchor}">{label}</a>'

        return str(m.group(0))

    return _AC_LINK_RE.sub(_replace, html)


_LIVERELOAD_SCRIPT = (
    "<script>"
    "(function(){"
    "var v=null;"
    "function poll(){"
    "fetch('/__livereload')"
    ".then(function(r){return r.text();})"
    ".then(function(n){"
    "if(v===null){v=n;}else if(n!==v){location.reload();}else{setTimeout(poll,800);}"
    "}).catch(function(){setTimeout(poll,2000);})"
    "}"
    "setTimeout(poll,800);"
    "})();"
    "</script>"
)


def inject_livereload(html: str) -> str:
    """Inject a polling livereload script before ``</body>``."""
    return html.replace("</body>", _LIVERELOAD_SCRIPT + "\n</body>", 1)


def render_page(xhtml: str, page: str = "", page_link_map: dict[str, str] | None = None) -> str:
    """Wrap rendered HTML in a full browser page with Confluence-like styles."""
    body = render_html(xhtml, page_link_map=page_link_map)
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


def render_index(section_title: str, pages: list[tuple[str, str]]) -> str:
    """Generate a simple HTML index page linking to all section pages.

    Parameters
    ----------
    section_title:
        Human-readable name of the section (used as the page ``<h1>``).
    pages:
        List of ``(page_title, html_filename)`` pairs in nav order.
    """
    items = "\n".join(
        f'  <li><a href="{_html.escape(fname)}">{_html.escape(title)}</a></li>'
        for title, fname in pages
    )
    escaped_title = _html.escape(section_title)
    return (
        f'<!DOCTYPE html>\n<html>\n<head>\n'
        f'<meta charset="utf-8">\n'
        f'<title>mk2conf preview — {escaped_title}</title>\n'
        f"<style>{_CSS}</style>\n"
        f"</head>\n<body>\n"
        f"<h1>{escaped_title}</h1>\n"
        f"<ul>\n{items}\n</ul>\n"
        f"</body>\n</html>\n"
    )
