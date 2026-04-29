"""Shared IR tree-manipulation utilities.

Used by transform passes that need to substitute nodes without mutating the
frozen dataclass tree.  Every transform works the same way:

1. Walk the tree and collect ``{id(node): replacement}`` pairs.
2. Call :func:`replace_nodes` to rebuild the tree with substitutions applied.

Both functions are pure and return new objects — the original tree is never
modified.
"""

from __future__ import annotations

import dataclasses

from mkdocs_to_confluence.ir.nodes import IRNode


def replace_nodes(
    nodes: tuple[IRNode, ...],
    replacements: dict[int, IRNode],
) -> tuple[IRNode, ...]:
    """Recursively rebuild *nodes*, substituting entries from *replacements*."""
    result: list[IRNode] = []
    for node in nodes:
        if id(node) in replacements:
            result.append(replacements[id(node)])
            continue
        result.append(_rebuild(node, replacements))
    return tuple(result)


def _rebuild(node: IRNode, replacements: dict[int, IRNode]) -> IRNode:
    """Return *node* with any matching descendants replaced."""
    changes: dict[str, object] = {}
    for field in dataclasses.fields(node):
        value = getattr(node, field.name)
        if isinstance(value, IRNode):
            replaced = replacements.get(id(value), _rebuild(value, replacements))
            if replaced is not value:
                changes[field.name] = replaced
        elif isinstance(value, tuple) and value and isinstance(value[0], IRNode):
            rebuilt = replace_nodes(value, replacements)
            if rebuilt is not value:
                changes[field.name] = rebuilt
    if changes:
        return dataclasses.replace(node, **changes)
    return node
