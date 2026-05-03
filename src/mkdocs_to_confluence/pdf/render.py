"""Build a combined HTML document suitable for WeasyPrint PDF rendering.

Structure
---------
1. Cover page  — section title, optional subtitle, date
2. TOC         — nav-order list of page titles (WeasyPrint resolves page numbers
                 via CSS ``target-counter``)
3. Chapters    — one ``<article>`` per page, ``page-break-before: always``
"""

from __future__ import annotations

import html as _html
from datetime import date

from mkdocs_to_confluence.preview.render import render_html

# ── PDF-specific CSS (extends / overrides preview CSS) ────────────────────────

_PDF_CSS = """
@page {
  size: A4 portrait;
  margin: 25mm 20mm 25mm 20mm;
  @bottom-center {
    content: counter(page);
    font-size: 9pt;
    color: #505f79;
  }
  @bottom-left {
    content: string(section-title);
    font-size: 9pt;
    color: #505f79;
  }
}

@page cover {
  margin: 40mm 25mm;
  @bottom-center { content: none; }
  @bottom-left   { content: none; }
}

@page toc {
  @bottom-center { content: none; }
  @bottom-left   { content: none; }
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 10pt;
  color: #172b4d;
  line-height: 1.6;
  margin: 0;
  padding: 0;
}

/* ── Cover ── */
.cover {
  page: cover;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 200mm;
}
.cover h1 {
  font-size: 28pt;
  color: #0052cc;
  margin: 0 0 8mm 0;
  border-bottom: 2px solid #0052cc;
  padding-bottom: 4mm;
}
.cover .subtitle {
  font-size: 14pt;
  color: #505f79;
  margin: 0 0 16mm 0;
}
.cover .meta {
  font-size: 9pt;
  color: #8993a4;
}

/* ── TOC ── */
.toc {
  page: toc;
  page-break-after: always;
}
.toc h2 {
  font-size: 14pt;
  color: #0052cc;
  border-bottom: 1px solid #dfe1e6;
  padding-bottom: 2mm;
  margin-bottom: 4mm;
}
.toc ol {
  list-style: none;
  padding: 0;
  margin: 0;
}
.toc ol li {
  display: flex;
  justify-content: space-between;
  padding: 1.5mm 0;
  border-bottom: 1px dotted #dfe1e6;
  font-size: 10pt;
}
.toc ol li a {
  color: #172b4d;
  text-decoration: none;
}
.toc ol li a::after {
  content: target-counter(attr(href), page);
  float: right;
  color: #505f79;
}

/* ── Chapters ── */
article {
  page-break-before: always;
  string-set: section-title attr(data-title);
}
article h1 { font-size: 18pt; color: #0052cc; margin-top: 0; }
article h2 { font-size: 13pt; color: #0052cc; }
article h3 { font-size: 11pt; color: #172b4d; }

a { color: #0052cc; }

table {
  border-collapse: collapse;
  width: 100%;
  margin: 4mm 0;
  font-size: 9pt;
  word-break: break-word;
}
th, td { border: 1px solid #dfe1e6; padding: 3mm 4mm; text-align: left; }
th { background: #f4f5f7; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }

code {
  background: #f4f5f7;
  padding: 1px 4px;
  border-radius: 2px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 0.85em;
}
.code-block {
  background: #1e1e1e;
  border-radius: 3px;
  margin: 3mm 0;
  overflow: hidden;
  page-break-inside: avoid;
}
.code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2mm 4mm;
  background: #2d2d2d;
}
.code-lang { color: #a0a0a0; font-size: 8pt; font-family: monospace; }
.code-title { color: #ccc; font-size: 8pt; }
.code-block pre {
  margin: 0;
  padding: 3mm 4mm;
  background: transparent;
  white-space: pre-wrap;
  word-break: break-all;
}
.code-block pre code {
  background: transparent;
  color: #d4d4d4;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8.5pt;
  padding: 0;
}

blockquote {
  border-left: 3px solid #0052cc;
  margin: 3mm 0;
  padding: 2mm 4mm;
  background: #deebff;
}

ul, ol { padding-left: 6mm; }
li { margin: 1mm 0; }

/* Grid cards: degrade to stacked blocks in PDF */
.ac-layout-section { display: block; }
.ac-layout-cell {
  display: block;
  border: 1px solid #dfe1e6;
  border-radius: 3px;
  padding: 3mm;
  margin: 2mm 0;
  background: #fafbfc;
  page-break-inside: avoid;
}

img { max-width: 100%; height: auto; }
"""


def build_pdf_html(
    section_title: str,
    chapters: list[tuple[str, str]],
    *,
    author: str = "",
    version: str = "",
) -> str:
    """Return a single HTML string ready for WeasyPrint.

    Parameters
    ----------
    section_title:
        Used on the cover page and in the running footer.
    chapters:
        List of ``(page_title, xhtml)`` pairs in nav order.
    author:
        Optional author name shown on the cover.
    version:
        Optional version string shown on the cover (e.g. ``"v1.2"``).
    """
    today = date.today().strftime("%B %d, %Y")

    # Cover
    subtitle_parts = [p for p in (version, author) if p]
    subtitle_html = (
        f'<p class="subtitle">{_html.escape(" · ".join(subtitle_parts))}</p>'
        if subtitle_parts
        else ""
    )
    cover = (
        '<section class="cover">'
        f"<h1>{_html.escape(section_title)}</h1>"
        f"{subtitle_html}"
        f'<p class="meta">{_html.escape(today)}</p>'
        "</section>\n"
    )

    # TOC
    toc_items = "".join(
        f'<li><a href="#{_anchor(title)}">{_html.escape(title)}</a></li>\n'
        for title, _ in chapters
    )
    toc = (
        '<nav class="toc">'
        "<h2>Table of Contents</h2>"
        f"<ol>{toc_items}</ol>"
        "</nav>\n"
    )

    # Chapters
    chapter_html = "".join(
        '<article id="{anchor}" data-title="{title}">\n{body}\n</article>\n'.format(
            anchor=_anchor(title),
            title=_html.escape(title),
            body=render_html(xhtml),
        )
        for title, xhtml in chapters
    )

    escaped_title = _html.escape(section_title)
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{escaped_title}</title>\n"
        f"<style>{_PDF_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{cover}"
        f"{toc}"
        f"{chapter_html}"
        "</body>\n</html>\n"
    )


def _anchor(title: str) -> str:
    """Slugify a page title for use as an HTML id / fragment."""
    return "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
