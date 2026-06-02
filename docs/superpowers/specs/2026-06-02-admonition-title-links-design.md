# Design: warn + degrade links in admonition titles

**Date:** 2026-06-02
**Status:** Approved

## Problem

A Confluence macro title is an `<ac:parameter>`, which holds **plain text only** —
it cannot contain `<ac:link>` or any markup. So a Markdown link written in an
admonition title (`!!! warning "Conflict - see [Hello](foobar.md#hello)"`) cannot
render as a link. Today the transpiler emits the raw Markdown verbatim, so the
published title reads `Conflict - see [Hello](foobar.md#hello)` — broken syntax
leaking into Confluence, which contradicts the project principle that no broken
output should reach the page.

## Goal

When an admonition title contains a Markdown inline link, publish a clean title
(link text only) and emit a transpiler warning so the author can adjust the
source.

## Behavior

- Match **inline links only**: `[text](target)`.
- Replace each with its `text`, e.g. `Conflict - see [Hello](foobar.md#hello)`
  becomes `Conflict - see Hello`.
- Emit one warning per affected title to **stderr**, in the existing transpiler
  warning format (see `transforms/mermaid.py:_warn`):
  `  warning    link in admonition title not supported by Confluence (using link text): "<original title>" in <page_path>`
- Applies to all admonition forms — `!!!`, `???`, `???+`, and danger panels —
  because they all read `Admonition.title`.

### Decisions

- **Images** (`![alt](src)`) are left untouched, not mangled — a negative
  lookbehind on `!` prevents the link regex from matching the `[alt](src)` part.
  Out of scope.
- **Other macro titles** (content-tab labels `=== "..."`, code-block titles) are
  out of scope. Links there are vanishingly rare. Noted as a known similar case.
- Reference-style links and autolinks in titles are out of scope (inline
  `[text](url)` only).

## Architecture

A new transform `src/mkdocs_to_confluence/transforms/admonition_titles.py`,
matching the established pattern where transforms own warnings (like `mermaid.py`).

```
strip_links_in_admonition_titles(nodes: tuple[IRNode, ...], page_path: str) -> tuple[IRNode, ...]
```

- Walks the IR (`ir.nodes.walk`) for `Admonition` nodes.
- For each `title`, applies the regex `(?<!!)\[([^\]]+)\]\(([^)]+)\)` → `\1`.
- If a title changed: rebuild that node via `dataclasses.replace(node, title=new)`,
  collect into a `{id(node): new_node}` map, and apply with
  `ir.treeutil.replace_nodes(nodes, replacements)`.
- For each affected title, print the warning to stderr.
- Returns the original `nodes` unchanged when nothing matched.

The emitter stays pure — `_emit_admonition` continues to `html.escape` a
now-clean title; no emitter change needed.

## Data flow

`compiler/page.py: compile_page` calls the transform immediately after
`ir_nodes = parse(preprocessed)`, passing `node.docs_path or ""` as `page_path`.
One line, mirroring how `render_mermaid_diagrams` is invoked.

## Components touched

| File | Change |
|---|---|
| `transforms/admonition_titles.py` | New transform (walk + rewrite + warn) |
| `compiler/page.py` | One line wiring the transform after `parse` |
| `tests/test_admonition_titles.py` | New unit tests |
| `tests/test_publish_pipeline.py` | One integration test |

## Testing (TDD)

**Transform unit tests** (`tests/test_admonition_titles.py`)
- Link in title is stripped to its text.
- Warning is emitted to stderr (captured via `capsys`), containing the page path
  and the original title.
- Title without a link is unchanged and emits no warning.
- Multiple links in one title are all stripped.
- An admonition nested inside a `Section` is still processed.
- An image (`![alt](src)`) in a title is left untouched (not mangled).

**Integration** (`tests/test_publish_pipeline.py`)
- `compile_page` on a page with `!!! warning "see [Hello](foobar.md#hello)"`
  produces an emitted title of `see Hello` with no `[`, `]`, or `(` leakage.

## Out of scope (YAGNI)

- Links in content-tab labels, code-block titles, or other macro parameters.
- Reference-style links, autolinks, and images in titles.
- Any attempt to make titles clickable (impossible in Confluence).
