"""Degrade Markdown links inside admonition titles.

A Confluence macro title is an ``<ac:parameter>`` and holds plain text only —
it cannot contain ``<ac:link>`` or any markup. A Markdown link written in an
admonition title therefore cannot render. This transform replaces each inline
link ``[text](target)`` in an ``Admonition`` title with its ``text`` and warns
to stderr so the author can adjust the source.

Images (``![alt](src)``) are deliberately left untouched (negative lookbehind on
``!``). Reference-style links and autolinks are out of scope.
"""

from __future__ import annotations

import dataclasses
import re

from mkdocs_to_confluence.ir.nodes import Admonition, IRNode, walk
from mkdocs_to_confluence.ir.treeutil import replace_nodes
from mkdocs_to_confluence.transforms._kroki import warn as _warn

# Inline Markdown link [text](target), but not an image (no leading '!').
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


def strip_links_in_admonition_titles(
    nodes: tuple[IRNode, ...], page_path: str
) -> tuple[IRNode, ...]:
    """Replace inline links in admonition titles with their link text.

    Emits a transpiler warning to stderr for each affected title. Returns the
    original *nodes* unchanged when no title contained a link.
    """
    replacements: dict[int, IRNode] = {}

    for top in nodes:
        for node in walk(top):
            if not isinstance(node, Admonition) or node.title is None:
                continue
            new_title = _LINK_RE.sub(r"\1", node.title)
            if new_title == node.title:
                continue
            _warn(
                "link in admonition title not supported by Confluence "
                f'(using link text): "{node.title}" in {page_path}'
            )
            replacements[id(node)] = dataclasses.replace(node, title=new_title)

    if not replacements:
        return nodes
    return replace_nodes(nodes, replacements)

