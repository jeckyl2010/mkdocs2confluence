# Admonition Title Link Degradation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip Markdown inline links from admonition titles (which Confluence macro `title` parameters cannot render) down to their link text, emitting a transpiler warning so the author can adjust the source.

**Architecture:** A new pure transform walks the IR for `Admonition` nodes, regex-replaces `[text](target)` with `text` in each title, rebuilds changed nodes via `replace_nodes`, and warns to stderr. Wired into `compile_page` right after parsing. The emitter is unchanged (it keeps escaping a now-clean title).

**Tech Stack:** Python 3.12+, pytest, ruff, mypy, vulture. Run tests with `uv run pytest -q`.

---

### Task 1: The admonition-title link transform

**Files:**
- Create: `src/mkdocs_to_confluence/transforms/admonition_titles.py`
- Test: `tests/test_admonition_titles.py` (create)

Reference patterns already in the codebase:
- `src/mkdocs_to_confluence/transforms/internallinks.py` iterates `for top in nodes: for node in walk(top)` and builds a `{id(node): new_node}` dict, then calls `replace_nodes(nodes, replacements)`.
- `src/mkdocs_to_confluence/transforms/mermaid.py:_warn` prints `f"  warning    {msg}"` to `sys.stderr`.
- `Admonition` (in `ir/nodes.py`) is a frozen dataclass with fields `kind`, `title: str | None`, `children`, `collapsible`, `expanded`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admonition_titles.py`:

```python
"""Tests for the admonition-title link degradation transform."""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import Admonition, Section, TextNode
from mkdocs_to_confluence.transforms.admonition_titles import (
    strip_links_in_admonition_titles,
)


def _adm(title: str | None) -> Admonition:
    return Admonition(kind="warning", title=title, children=())


def test_link_in_title_stripped_to_text() -> None:
    nodes = (_adm("Conflict - see [Hello](foobar.md#hello)"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "Conflict - see Hello"


def test_warning_emitted_with_page_and_title(capsys) -> None:
    nodes = (_adm("see [Hello](foobar.md#hello)"),)
    strip_links_in_admonition_titles(nodes, "guide/index.md")
    err = capsys.readouterr().err
    assert "warning" in err
    assert "guide/index.md" in err
    assert "see [Hello](foobar.md#hello)" in err


def test_title_without_link_unchanged_and_no_warning(capsys) -> None:
    nodes = (_adm("Just a plain title"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "Just a plain title"
    assert capsys.readouterr().err == ""


def test_none_title_is_safe(capsys) -> None:
    nodes = (_adm(None),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title is None
    assert capsys.readouterr().err == ""


def test_multiple_links_all_stripped() -> None:
    nodes = (_adm("[A](a.md) and [B](b.md#x)"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "A and B"


def test_nested_admonition_in_section_processed() -> None:
    inner = _adm("see [Hello](foobar.md#hello)")
    section = Section(level=2, anchor="s", title=(TextNode("S"),), children=(inner,))
    out = strip_links_in_admonition_titles((section,), "index.md")
    nested = out[0].children[0]
    assert isinstance(nested, Admonition)
    assert nested.title == "see Hello"


def test_image_in_title_not_mangled() -> None:
    nodes = (_adm("look ![alt](img.png)"),)
    out = strip_links_in_admonition_titles(nodes, "index.md")
    assert out[0].title == "look ![alt](img.png)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_admonition_titles.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'mkdocs_to_confluence.transforms.admonition_titles'`

- [ ] **Step 3: Implement the transform**

Create `src/mkdocs_to_confluence/transforms/admonition_titles.py`:

```python
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
import sys

from mkdocs_to_confluence.ir.nodes import Admonition, IRNode, walk
from mkdocs_to_confluence.ir.treeutil import replace_nodes

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


def _warn(msg: str) -> None:
    print(f"  warning    {msg}", file=sys.stderr)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_admonition_titles.py -q --no-cov`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/mkdocs_to_confluence/transforms/admonition_titles.py tests/test_admonition_titles.py
git commit -m "feat(admonition): degrade links in titles to plain text with warning"
```

---

### Task 2: Wire the transform into the compile pipeline

**Files:**
- Modify: `src/mkdocs_to_confluence/compiler/page.py`
- Test: `tests/test_publish_pipeline.py`

The pipeline file already imports transforms near the top and calls
`parse(preprocessed)` to build `ir_nodes` (look for the line
`ir_nodes = parse(preprocessed)`).

- [ ] **Step 1: Write the failing integration test**

`tests/test_publish_pipeline.py` already defines helpers `_make_config(docs_dir)`
and `_page_node(title, path)` and imports `compile_page`. Add this test after the
existing `compile_page` tests:

```python
def test_compile_page_strips_link_from_admonition_title(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text(
        '!!! warning "Conflict - see [Hello](foobar.md#hello)"\n\n'
        "    Body text.\n",
        encoding="utf-8",
    )

    node = _page_node("Page", md)
    config = _make_config(docs)
    xhtml, _, _, _, _ = compile_page(node, config)

    assert "Conflict - see Hello" in xhtml
    assert "[Hello]" not in xhtml
    assert "foobar.md#hello" not in xhtml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_pipeline.py -q -k admonition_title --no-cov`
Expected: FAIL — `[Hello]` and `foobar.md#hello` still present in `xhtml`.

- [ ] **Step 3: Add the import**

In `src/mkdocs_to_confluence/compiler/page.py`, with the other
`from mkdocs_to_confluence.transforms...` imports, add:

```python
from mkdocs_to_confluence.transforms.admonition_titles import (
    strip_links_in_admonition_titles,
)
```

- [ ] **Step 4: Call the transform after parse**

In `compile_page`, find:

```python
    ir_nodes = parse(preprocessed)
```

and add immediately after it:

```python
    ir_nodes = strip_links_in_admonition_titles(ir_nodes, node.docs_path or "")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_pipeline.py -q -k admonition_title --no-cov`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/compiler/page.py tests/test_publish_pipeline.py
git commit -m "feat(compile): strip links from admonition titles during compile"
```

---

### Task 3: Document the limitation

**Files:**
- Modify: `docs/features.md`

`docs/features.md` has a `## Known limitations` table (rows like `| **Feature** | Notes |`).

- [ ] **Step 1: Add a Known limitations row**

In `docs/features.md`, add a row to the Known limitations table:

```markdown
| **Links in admonition titles** | Confluence macro titles are plain text and cannot hold links. A Markdown link in an admonition title is reduced to its link text and a transpiler warning is emitted — move the link into the admonition body to keep it clickable. |
```

- [ ] **Step 2: Commit**

```bash
git add docs/features.md
git commit -m "docs: note links-in-admonition-titles limitation"
```

---

### Final verification

- [ ] **Step 1: Run the full pre-release checklist**

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run vulture src --min-confidence 80
```

Expected: all pass, no warnings. Then the feature is ready for a release (separate `/release` step — minor version bump, since this is a `feat`).
