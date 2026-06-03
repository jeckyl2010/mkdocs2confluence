"""Figure/figcaption preprocess rewrite.

Material for MkDocs authors captions with the ``md_in_html`` figure form::

    <figure markdown="span">
      ![alt](img.png)
      <figcaption>The caption</figcaption>
    </figure>

Confluence storage format has no ``<figure>`` element, so this pass rewrites
such a block into a single titled Markdown image::

    ![alt](img.png "The caption")

The image then flows through the normal parser and the ``resolve_captions``
transform promotes the title to an ``ac:caption``. The figcaption text always
wins over any pre-existing image title (it is substituted into the title slot).
"""

from __future__ import annotations

import re

_FIGURE_RE = re.compile(
    r"<figure\b[^>]*>\s*"
    r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^\s)]+)(?:\s+\"[^\"]*\")?\)\s*"
    r"<figcaption>(?P<cap>.*?)</figcaption>\s*"
    r"</figure>",
    re.IGNORECASE | re.DOTALL,
)


def rewrite_figure_captions(text: str) -> str:
    """Rewrite ``<figure>…<figcaption>…</figure>`` blocks to titled images."""

    def _sub(m: re.Match[str]) -> str:
        alt = m.group("alt")
        src = m.group("src")
        cap = m.group("cap").strip().replace('"', "'")
        return f'![{alt}]({src} "{cap}")'

    return _FIGURE_RE.sub(_sub, text)
