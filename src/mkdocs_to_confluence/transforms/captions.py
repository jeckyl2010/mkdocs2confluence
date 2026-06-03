"""Caption resolution transform.

Fills :attr:`ImageNode.caption` from the image ``title`` attribute when no
caption is already present, and clears ``title`` so the same text is not also
emitted as a hover tooltip. Images whose caption is already set (e.g. from a
``<figcaption>`` rewrite) are left untouched, so figcaptions take precedence.
"""

from __future__ import annotations

import dataclasses

from mkdocs_to_confluence.ir.nodes import ImageNode, IRNode, walk
from mkdocs_to_confluence.ir.treeutil import replace_nodes


def resolve_captions(nodes: tuple[IRNode, ...]) -> tuple[IRNode, ...]:
    """Promote image ``title`` to ``caption`` where no caption exists yet."""
    replacements: dict[int, IRNode] = {}
    for top_node in nodes:
        for node in walk(top_node):
            if not isinstance(node, ImageNode):
                continue
            if node.caption is not None or node.title is None:
                continue
            replacements[id(node)] = dataclasses.replace(
                node, caption=node.title, title=None
            )
    if not replacements:
        return nodes
    return replace_nodes(nodes, replacements)
