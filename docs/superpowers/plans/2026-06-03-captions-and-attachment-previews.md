# Image Captions & Attachment Inline Previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render visible image captions (from `<figcaption>` or image `title`) and optionally render PDF/Office attachment links as inline Confluence `view-file` previews via a new `mkdocs.yml` flag.

**Architecture:** Captions add a `caption` field to `ImageNode`; a `resolve_captions` transform fills it from `title`, and a preprocess pass rewrites `<figure>/<figcaption>` blocks into titled Markdown images (so figcaptions flow through the same path, taking precedence). Attachment previews add a `ConfluenceConfig.attachment_preview` flag, a new `AttachmentPreview` IR node, and a `resolve_attachment_previews` transform that swaps eligible attachment links for that node, which the emitter renders as a `view-file` macro.

**Tech Stack:** Python 3.12, frozen dataclasses for IR, pytest, ruff/mypy via pre-commit. Transforms use `walk` + `replace_nodes` from `ir/treeutil.py`.

---

## File Structure

| File | Responsibility | Create/Modify |
|---|---|---|
| `src/mkdocs_to_confluence/ir/nodes.py` | `ImageNode.caption` field; new `AttachmentPreview` node | Modify |
| `src/mkdocs_to_confluence/emitter/xhtml.py` | `_emit_image` caption wrapping; `_emit_attachment_preview` | Modify |
| `src/mkdocs_to_confluence/transforms/captions.py` | `title`→`caption` fallback transform | Create |
| `src/mkdocs_to_confluence/preprocess/captions.py` | `<figure>/<figcaption>` → `![alt](src "cap")` rewrite | Create |
| `src/mkdocs_to_confluence/transforms/attachment_previews.py` | eligible attachment link → `AttachmentPreview` | Create |
| `src/mkdocs_to_confluence/loader/config.py` | parse/validate `attachment_preview` | Modify |
| `src/mkdocs_to_confluence/compiler/page.py` | wire the new preprocess + two transforms into the pipeline | Modify |
| `tests/test_captions.py` | caption emitter + transform + preprocess + integration | Create |
| `tests/test_attachment_previews.py` | config + node emitter + transform + integration | Create |
| `docs/features.md`, `README.md` | document caption behavior + new config key | Modify |

---

## Part A — Image captions

### Task 1: `ImageNode.caption` field + emitter renders `<ac:caption>`

**Files:**
- Modify: `src/mkdocs_to_confluence/ir/nodes.py` (`ImageNode`, ~line 152)
- Modify: `src/mkdocs_to_confluence/emitter/xhtml.py` (`_emit_image`, ~line 754)
- Test: `tests/test_captions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_captions.py`:

```python
"""Tests for image captions and figure/figcaption support."""

from __future__ import annotations

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import ImageNode, Paragraph


def test_emit_image_with_caption_local():
    node = Paragraph(children=(ImageNode(src="arch.png", alt="A", caption="Figure 1"),))
    out = emit((node,))
    assert "<ac:caption><p>Figure 1</p></ac:caption>" in out
    assert 'ri:filename="arch.png"' in out


def test_emit_image_without_caption_has_no_caption_element():
    node = Paragraph(children=(ImageNode(src="arch.png", alt="A"),))
    out = emit((node,))
    assert "<ac:caption>" not in out


def test_emit_image_caption_external_url():
    node = Paragraph(
        children=(ImageNode(src="https://x.test/a.png", alt="A", caption="Remote"),)
    )
    out = emit((node,))
    assert "<ac:caption><p>Remote</p></ac:caption>" in out
    assert "ri:url" in out


def test_emit_image_caption_is_escaped():
    node = Paragraph(children=(ImageNode(src="a.png", alt="A", caption="x & <y>"),))
    out = emit((node,))
    assert "x &amp; &lt;y&gt;" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_captions.py -v`
Expected: FAIL — `ImageNode.__init__() got an unexpected keyword argument 'caption'`

- [ ] **Step 3: Add the `caption` field**

In `src/mkdocs_to_confluence/ir/nodes.py`, add `caption` to `ImageNode` (after `title`):

```python
    src: str
    alt: str
    title: str | None = None
    caption: str | None = None
    attachment_name: str | None = None
    width: int | None = None
    height: int | None = None
    align: str | None = None
```

- [ ] **Step 4: Wrap caption in the emitter**

In `src/mkdocs_to_confluence/emitter/xhtml.py`, replace the body of `_emit_image` so the caption is nested inside `<ac:image>` (it currently returns a self-contained `<ac:image .../>`):

```python
def _emit_image(node: ImageNode) -> str:
    alt_attr = f' ac:alt="{html.escape(node.alt)}"' if node.alt else ""
    title_attr = f' ac:title="{html.escape(node.title)}"' if node.title else ""
    width_attr = f' ac:width="{node.width}"' if node.width is not None else ""
    height_attr = f' ac:height="{node.height}"' if node.height is not None else ""
    align_attr = f' ac:align="{html.escape(node.align)}"' if node.align else ""
    size_attrs = width_attr + height_attr + align_attr
    caption = (
        f"<ac:caption><p>{_emit_inlines((TextNode(text=node.caption),))}</p></ac:caption>"
        if node.caption
        else ""
    )
    # Local file → attachment reference; URL → external ri:url
    src = node.src
    if src.startswith(("http://", "https://", "//", "data:")):
        ref = f'<ri:url ri:value="{html.escape(src)}"/>'
        return f"<ac:image{alt_attr}{title_attr}{size_attrs}>{ref}{caption}</ac:image>"
    else:
        filename = html.escape(node.attachment_name or Path(src).name)
        # data-local-path is used by the preview renderer only (not valid XHTML)
        local_attr = f' data-local-path="{html.escape(src)}"'
        ref = f'<ri:attachment ri:filename="{filename}"/>'
        return f"<ac:image{alt_attr}{title_attr}{size_attrs}{local_attr}>{ref}{caption}</ac:image>"
```

(`TextNode` is already imported in this module; `_emit_inlines` escapes text via `html.escape`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_captions.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/ir/nodes.py src/mkdocs_to_confluence/emitter/xhtml.py tests/test_captions.py
git commit -m "feat: render ImageNode.caption as ac:caption"
```

---

### Task 2: `resolve_captions` transform — `title` → `caption` fallback

**Files:**
- Create: `src/mkdocs_to_confluence/transforms/captions.py`
- Test: `tests/test_captions.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_captions.py`:

```python
from mkdocs_to_confluence.transforms.captions import resolve_captions


def test_resolve_captions_title_becomes_caption():
    nodes = (Paragraph(children=(ImageNode(src="a.png", alt="A", title="Cap"),)),)
    out = resolve_captions(nodes)
    img = out[0].children[0]
    assert img.caption == "Cap"
    assert img.title is None  # cleared so it is not also a tooltip


def test_resolve_captions_existing_caption_wins():
    nodes = (
        Paragraph(children=(ImageNode(src="a.png", alt="A", title="T", caption="C"),)),
    )
    out = resolve_captions(nodes)
    img = out[0].children[0]
    assert img.caption == "C"
    assert img.title == "T"  # untouched when caption already set


def test_resolve_captions_no_title_unchanged():
    nodes = (Paragraph(children=(ImageNode(src="a.png", alt="A"),)),)
    out = resolve_captions(nodes)
    assert out[0].children[0].caption is None


def test_resolve_captions_external_image():
    nodes = (
        Paragraph(children=(ImageNode(src="https://x.test/a.png", alt="A", title="Cap"),)),
    )
    out = resolve_captions(nodes)
    assert out[0].children[0].caption == "Cap"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_captions.py -k resolve_captions -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mkdocs_to_confluence.transforms.captions'`

- [ ] **Step 3: Implement the transform**

Create `src/mkdocs_to_confluence/transforms/captions.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_captions.py -k resolve_captions -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mkdocs_to_confluence/transforms/captions.py tests/test_captions.py
git commit -m "feat: resolve_captions transform promotes image title to caption"
```

---

### Task 3: Wire `resolve_captions` into the pipeline + integration test

**Files:**
- Modify: `src/mkdocs_to_confluence/compiler/page.py` (after `resolve_local_assets`, ~line 80)
- Test: `tests/test_captions.py`

- [ ] **Step 1: Write the failing test**

This test drives the real publish path (`publisher.pipeline.compile_page`, a tuple-returning wrapper around `compiler/page.py`), so it genuinely fails until the wiring exists. Append to `tests/test_captions.py`:

```python
def test_compile_page_renders_image_caption(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    from mkdocs_to_confluence.loader.nav import NavNode
    from mkdocs_to_confluence.publisher.pipeline import compile_page

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (docs / "index.md").write_text('![Logo](logo.png "Our logo")\n', encoding="utf-8")

    node = NavNode(
        title="Index", docs_path="index.md", source_path=docs / "index.md", level=0
    )
    config = MkDocsConfig(
        site_name="T", docs_dir=docs, repo_url=None, edit_uri=None, nav=None
    )
    xhtml, _, _, _, _ = compile_page(node, config)
    assert "<ac:caption><p>Our logo</p></ac:caption>" in xhtml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_captions.py::test_compile_page_renders_image_caption -v`
Expected: FAIL — `compile_page` does not yet apply `resolve_captions`, so the output has `ac:title="Our logo"` and no `<ac:caption>`.

- [ ] **Step 3: Wire into `compile_page`**

In `src/mkdocs_to_confluence/compiler/page.py`, add the import near the other transform imports:

```python
from mkdocs_to_confluence.transforms.captions import resolve_captions
```

Then, immediately after the `resolve_local_assets(...)` call (the block that assigns `ir_nodes, attachments = resolve_local_assets(...)`), add:

```python
    ir_nodes = resolve_captions(ir_nodes)
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/test_captions.py -v`
Expected: PASS (all caption tests)

- [ ] **Step 5: Commit**

```bash
git add src/mkdocs_to_confluence/compiler/page.py tests/test_captions.py
git commit -m "feat: apply resolve_captions in compile pipeline"
```

---

### Task 4: `<figure>/<figcaption>` preprocess rewrite (figcaption precedence)

**Files:**
- Create: `src/mkdocs_to_confluence/preprocess/captions.py`
- Modify: `src/mkdocs_to_confluence/compiler/page.py` (after `strip_unsupported_html`, ~line 58)
- Test: `tests/test_captions.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_captions.py`:

```python
def test_rewrite_figure_caption_basic():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = (
        '<figure markdown="span">\n'
        "  ![Arch](arch.png)\n"
        "  <figcaption>System overview</figcaption>\n"
        "</figure>\n"
    )
    out = rewrite_figure_captions(md)
    assert out.strip() == '![Arch](arch.png "System overview")'


def test_rewrite_figure_caption_precedence_over_title():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = (
        "<figure>\n"
        '![Arch](arch.png "ignored title")\n'
        "<figcaption>Real caption</figcaption>\n"
        "</figure>\n"
    )
    out = rewrite_figure_captions(md)
    assert out.strip() == '![Arch](arch.png "Real caption")'


def test_rewrite_figure_caption_escapes_quotes():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = '<figure>\n![A](a.png)\n<figcaption>a "quoted" cap</figcaption>\n</figure>\n'
    out = rewrite_figure_captions(md)
    assert out.strip() == "![A](a.png \"a 'quoted' cap\")"


def test_rewrite_figure_caption_no_figure_unchanged():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = "Just text with ![A](a.png) inline.\n"
    assert rewrite_figure_captions(md) == md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_captions.py -k rewrite_figure -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mkdocs_to_confluence.preprocess.captions'`

- [ ] **Step 3: Implement the preprocess rewrite**

Create `src/mkdocs_to_confluence/preprocess/captions.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_captions.py -k rewrite_figure -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire into `compile_page`**

In `src/mkdocs_to_confluence/compiler/page.py`, add the import:

```python
from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions
```

Then add the call immediately after the `strip_unsupported_html(preprocessed)` line:

```python
    preprocessed = rewrite_figure_captions(preprocessed)
```

- [ ] **Step 6: Add an end-to-end figure test**

Append to `tests/test_captions.py`:

```python
def test_figure_pipeline_end_to_end():
    from mkdocs_to_confluence.parser.markdown import parse
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions
    from mkdocs_to_confluence.transforms.captions import resolve_captions

    md = "<figure>\n![Arch](arch.png)\n<figcaption>Overview</figcaption>\n</figure>\n"
    out = emit(resolve_captions(parse(rewrite_figure_captions(md))))
    assert "<ac:caption><p>Overview</p></ac:caption>" in out
```

- [ ] **Step 7: Run the full caption suite**

Run: `uv run pytest tests/test_captions.py -v`
Expected: PASS (all)

- [ ] **Step 8: Commit**

```bash
git add src/mkdocs_to_confluence/preprocess/captions.py src/mkdocs_to_confluence/compiler/page.py tests/test_captions.py
git commit -m "feat: rewrite figure/figcaption blocks into captioned images"
```

---

## Part B — Attachment inline previews

### Task 5: Config `attachment_preview` flag

**Files:**
- Modify: `src/mkdocs_to_confluence/loader/config.py` (`ConfluenceConfig` dataclass + `load_config` parse block + `ConfluenceConfig(...)` constructor call)
- Test: `tests/test_attachment_previews.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_attachment_previews.py`:

```python
"""Tests for attachment inline previews (config, IR node, transform, emitter)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import ConfigError, load_config


def _write_mkdocs(tmp_path: Path, extra: str = "") -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "mkdocs.yml").write_text(
        f"site_name: Test Site\n{extra}", encoding="utf-8"
    )
    return tmp_path / "mkdocs.yml"


_CONF = (
    "confluence:\n"
    "  base_url: https://x.atlassian.net/wiki\n"
    "  email: a@b.test\n"
    "  space_key: TECH\n"
)


def test_attachment_preview_true(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _CONF + "  attachment_preview: true\n"))
    assert cfg.confluence.attachment_preview is True


def test_attachment_preview_default_false(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _CONF))
    assert cfg.confluence.attachment_preview is False


def test_attachment_preview_non_bool_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="attachment_preview"):
        load_config(_write_mkdocs(tmp_path, _CONF + "  attachment_preview: maybe\n"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_attachment_previews.py -v`
Expected: FAIL — `AttributeError: 'ConfluenceConfig' object has no attribute 'attachment_preview'`

- [ ] **Step 3: Add the dataclass field**

In `src/mkdocs_to_confluence/loader/config.py`, add to `ConfluenceConfig` (after `exclude_properties`):

```python
    exclude_properties: tuple[str, ...] = ()  # front matter keys to omit from Page Properties table
    attachment_preview: bool = False  # render PDF/Office attachment links as view-file macros
```

- [ ] **Step 4: Parse + validate in `load_config`**

In `load_config`, immediately after the `exclude_properties` parsing block (before the `confluence = ConfluenceConfig(` call), add:

```python
        # attachment_preview (optional) — render PDF/Office attachment links inline
        raw_preview = raw_conf.get("attachment_preview", False)
        if not isinstance(raw_preview, bool):
            raise ConfigError(
                "mkdocs.yml: 'confluence.attachment_preview' must be a boolean, "
                f"got {type(raw_preview).__name__}."
            )
        attachment_preview = raw_preview
```

Then add the keyword to the `ConfluenceConfig(...)` constructor call (alongside `full_width=...`):

```python
            attachment_preview=attachment_preview,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_attachment_previews.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/loader/config.py tests/test_attachment_previews.py
git commit -m "feat: add confluence.attachment_preview config flag"
```

---

### Task 6: `AttachmentPreview` IR node + `view-file` emitter

**Files:**
- Modify: `src/mkdocs_to_confluence/ir/nodes.py` (new node, near other macro nodes)
- Modify: `src/mkdocs_to_confluence/emitter/xhtml.py` (import, `_emit_inline` dispatch, new `_emit_attachment_preview`)
- Test: `tests/test_attachment_previews.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_attachment_previews.py`:

```python
from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import AttachmentPreview, Paragraph


def test_emit_attachment_preview_macro():
    out = emit((Paragraph(children=(AttachmentPreview(filename="docs_spec.pdf"),)),))
    assert '<ac:structured-macro ac:name="view-file">' in out
    assert '<ac:parameter ac:name="name"><ri:attachment ri:filename="docs_spec.pdf"/></ac:parameter>' in out
    assert "</ac:structured-macro>" in out


def test_emit_attachment_preview_escapes_filename():
    out = emit((Paragraph(children=(AttachmentPreview(filename='a&b".pdf'),)),))
    assert "a&amp;b&quot;.pdf" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_attachment_previews.py -k emit_attachment -v`
Expected: FAIL — `ImportError: cannot import name 'AttachmentPreview'`

- [ ] **Step 3: Add the IR node**

In `src/mkdocs_to_confluence/ir/nodes.py`, add near the other macro nodes (e.g. after `ChildrenMacro`):

```python
@dataclass(frozen=True)
class AttachmentPreview(IRNode):
    """An inline preview of an uploaded attachment (PDF/Office file).

    ``filename`` is the collision-safe Confluence attachment name (the same
    value carried on the originating ``LinkNode.attachment_name``). The emitter
    renders a ``view-file`` macro referencing the attachment.
    """

    filename: str
```

- [ ] **Step 4: Implement the emitter**

In `src/mkdocs_to_confluence/emitter/xhtml.py`:

1. Add `AttachmentPreview` to the IR imports near the top of the file (the block importing node types).

2. In `_emit_inline`, add this branch near the other inline node checks (e.g. just after the `LinkNode` branch):

```python
    if isinstance(node, AttachmentPreview):
        return _emit_attachment_preview(node)
```

3. Add the emitter function next to `_emit_link`:

```python
def _emit_attachment_preview(node: AttachmentPreview) -> str:
    filename = html.escape(node.filename, quote=True)
    return (
        '<ac:structured-macro ac:name="view-file">'
        f'<ac:parameter ac:name="name"><ri:attachment ri:filename="{filename}"/></ac:parameter>'
        "</ac:structured-macro>"
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_attachment_previews.py -k emit_attachment -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/ir/nodes.py src/mkdocs_to_confluence/emitter/xhtml.py tests/test_attachment_previews.py
git commit -m "feat: AttachmentPreview node renders view-file macro"
```

---

### Task 7: `resolve_attachment_previews` transform

**Files:**
- Create: `src/mkdocs_to_confluence/transforms/attachment_previews.py`
- Test: `tests/test_attachment_previews.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_attachment_previews.py`:

```python
from mkdocs_to_confluence.ir.nodes import AttachmentPreview, LinkNode, Paragraph, TextNode
from mkdocs_to_confluence.transforms.attachment_previews import resolve_attachment_previews


def _link(href: str, attachment_name=None) -> Paragraph:
    return Paragraph(
        children=(
            LinkNode(href=href, children=(TextNode(text="x"),), attachment_name=attachment_name),
        )
    )


def test_preview_pdf_when_enabled():
    nodes = (_link("spec.pdf", attachment_name="docs_spec.pdf"),)
    out = resolve_attachment_previews(nodes, enabled=True)
    child = out[0].children[0]
    assert isinstance(child, AttachmentPreview)
    assert child.filename == "docs_spec.pdf"


def test_office_extensions_when_enabled():
    for ext in ("doc", "docx", "xls", "xlsx", "ppt", "pptx"):
        nodes = (_link(f"f.{ext}", attachment_name=f"f.{ext}"),)
        out = resolve_attachment_previews(nodes, enabled=True)
        assert isinstance(out[0].children[0], AttachmentPreview)


def test_non_previewable_extension_unchanged():
    nodes = (_link("data.zip", attachment_name="data.zip"),)
    out = resolve_attachment_previews(nodes, enabled=True)
    assert isinstance(out[0].children[0], LinkNode)


def test_disabled_leaves_links_unchanged():
    nodes = (_link("spec.pdf", attachment_name="docs_spec.pdf"),)
    out = resolve_attachment_previews(nodes, enabled=False)
    assert isinstance(out[0].children[0], LinkNode)


def test_non_attachment_link_unchanged():
    nodes = (_link("https://x.test/spec.pdf", attachment_name=None),)
    out = resolve_attachment_previews(nodes, enabled=True)
    assert isinstance(out[0].children[0], LinkNode)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_attachment_previews.py -k "preview or extension or disabled or non_attachment" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mkdocs_to_confluence.transforms.attachment_previews'`

- [ ] **Step 3: Implement the transform**

Create `src/mkdocs_to_confluence/transforms/attachment_previews.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_attachment_previews.py -k "preview or extension or disabled or non_attachment" -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mkdocs_to_confluence/transforms/attachment_previews.py tests/test_attachment_previews.py
git commit -m "feat: resolve_attachment_previews transform"
```

---

### Task 8: Wire transform into the pipeline + integration test

**Files:**
- Modify: `src/mkdocs_to_confluence/compiler/page.py` (import + call after `resolve_local_assets`)
- Test: `tests/test_attachment_previews.py`

- [ ] **Step 1: Write the failing test**

This drives the real publish path so it fails until the wiring exists. Append to `tests/test_attachment_previews.py`:

```python
def test_compile_page_attachment_preview(tmp_path):
    from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
    from mkdocs_to_confluence.loader.nav import NavNode
    from mkdocs_to_confluence.publisher.pipeline import compile_page

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "spec.pdf").write_bytes(b"%PDF-1.4\n")
    (docs / "index.md").write_text("See the [spec](spec.pdf).\n", encoding="utf-8")
    node = NavNode(
        title="Index", docs_path="index.md", source_path=docs / "index.md", level=0
    )

    def _cfg(preview: bool) -> MkDocsConfig:
        return MkDocsConfig(
            site_name="T", docs_dir=docs, repo_url=None, edit_uri=None, nav=None,
            confluence=ConfluenceConfig(
                base_url="https://x.atlassian.net",
                space_key="TECH",
                email="a@b.test",
                token="t",
                attachment_preview=preview,
            ),
        )

    xhtml_on, _, _, _, _ = compile_page(node, _cfg(True))
    assert 'ac:name="view-file"' in xhtml_on

    xhtml_off, _, _, _, _ = compile_page(node, _cfg(False))
    assert 'ac:name="view-file"' not in xhtml_off
    assert "<ac:link>" in xhtml_off  # default: attachment download link
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_attachment_previews.py::test_compile_page_attachment_preview -v`
Expected: FAIL — `compile_page` does not yet apply `resolve_attachment_previews`, so the enabled case still emits `<ac:link>` and no `view-file` macro.

- [ ] **Step 3: Wire into `compile_page`**

In `src/mkdocs_to_confluence/compiler/page.py`, add the import:

```python
from mkdocs_to_confluence.transforms.attachment_previews import resolve_attachment_previews
```

Then, after the `resolve_captions(ir_nodes)` line added in Task 3, add:

```python
    attachment_preview = (
        config.confluence.attachment_preview if config.confluence else False
    )
    ir_nodes = resolve_attachment_previews(ir_nodes, enabled=attachment_preview)
```

- [ ] **Step 4: Run the full suites**

Run: `uv run pytest tests/test_attachment_previews.py tests/test_captions.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/mkdocs_to_confluence/compiler/page.py tests/test_attachment_previews.py
git commit -m "feat: apply attachment previews in compile pipeline"
```

---

### Task 9: Documentation

**Files:**
- Modify: `docs/features.md`
- Modify: `README.md`

- [ ] **Step 1: Document image captions in `docs/features.md`**

Add a section describing both caption sources. Use this content (adjust heading level to match the file):

```markdown
### Image captions

Images render with a visible Confluence caption when either is present:

- An image title: `![Alt text](diagram.png "Figure 1: Overview")`.
- A Material `md_in_html` figure:

  ```markdown
  <figure markdown="span">
    ![Alt text](diagram.png)
    <figcaption>Figure 1: Overview</figcaption>
  </figure>
  ```

When both are present on the same image, the `<figcaption>` wins. Captions work
for both local (attached) and external (URL) images.
```

- [ ] **Step 2: Document attachment previews in `docs/features.md`**

```markdown
### Inline attachment previews

Links to local PDF or Office files (`.pdf`, `.doc(x)`, `.xls(x)`, `.ppt(x)`) can
render as inline Confluence previews instead of download links. Enable it in
`mkdocs.yml`:

```yaml
confluence:
  attachment_preview: true   # default: false
```

Other file types (`.zip`, `.csv`, …) always remain download links.
```

- [ ] **Step 3: Add the config key to the `README.md` config reference**

Find the `confluence:` options list/table in `README.md` and add a row/entry:

```markdown
- `attachment_preview` (bool, default `false`) — render PDF/Office attachment links as inline `view-file` previews.
```

- [ ] **Step 4: Run the full test suite + pre-commit**

Run: `uv run pytest -q`
Expected: PASS (entire suite)

Run: `uv run pre-commit run --files $(git diff --name-only HEAD~8)`
Expected: ruff, mypy, import-linter all pass.

- [ ] **Step 5: Commit**

```bash
git add docs/features.md README.md
git commit -m "docs: document image captions and attachment previews"
```

---

## Verification (whole feature)

- [ ] Run the full suite: `uv run pytest -q` — all green.
- [ ] Confirm no regression in existing image/link tests: `uv run pytest tests/test_images.py tests/test_internallinks.py -q`.
- [ ] Confirm default behavior unchanged: a page with a plain attachment link and no `attachment_preview` flag still emits `<ac:link><ri:attachment/></ac:link>`.

> **Storage-format note for the implementer:** the exact `<ac:caption>` wrapping
> and `view-file` macro parameters are pinned by the tests in this plan. If a
> manual publish to a real Confluence Cloud space reveals a different required
> form (e.g. caption ordering relative to `<ri:attachment>`, or a `view-file`
> display/height parameter), update the emitter and its tests together.

## Out of scope (YAGNI)

- Configurable preview extension lists or display tuning (height/thumbnail).
- "Preview only when alone in a paragraph" placement rule.
- Caption numbering, styling, or cross-references.
- Captions sourced from `alt` text.
