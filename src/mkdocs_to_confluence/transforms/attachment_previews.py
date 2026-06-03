"""Attachment inline preview transform.

When enabled, replaces ``LinkNode``s that point at an uploaded PDF or Office
attachment (``attachment_name`` set by ``resolve_local_assets``) with an
:class:`AttachmentPreview` node, which the emitter renders as a Confluence
``view-file`` macro. Links to non-previewable file types, external URLs, and
internal pages are left unchanged.
"""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import AttachmentPreview, IRNode, LinkNode, walk
from mkdocs_to_confluence.ir.treeutil import replace_nodes

PREVIEWABLE_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
)


def resolve_attachment_previews(
    nodes: tuple[IRNode, ...], *, enabled: bool
) -> tuple[IRNode, ...]:
    """Swap eligible attachment links for ``AttachmentPreview`` nodes."""
    if not enabled:
        return nodes
    replacements: dict[int, IRNode] = {}
    for top_node in nodes:
        for node in walk(top_node):
            if not isinstance(node, LinkNode) or node.attachment_name is None:
                continue
            ext = _extension(node.attachment_name)
            if ext not in PREVIEWABLE_EXTENSIONS:
                continue
            replacements[id(node)] = AttachmentPreview(filename=node.attachment_name)
    if not replacements:
        return nodes
    return replace_nodes(nodes, replacements)


def _extension(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot != -1 else ""
