# Design: Image captions & attachment inline previews

**Date:** 2026-06-03
**Status:** Approved

## Problem

Two fidelity gaps when transpiling Material/MkDocs Markdown to Confluence:

1. **Image captions** are lost. `ImageNode` carries `alt` and `title`, but `title`
   is only emitted as an `ac:title` hover tooltip. Authors who write figure
   captions (the Material `md_in_html` `<figure>`/`<figcaption>` convention, or a
   plain image `title`) get no visible caption on the Confluence page.
2. **Linked source documents** (PDFs, Office files) referenced from the docs render
   as bare download links. Confluence can preview these inline via the `view-file`
   macro, which is far more useful when the docs point at reference material.

## Goals

- Render a visible caption beneath images, sourced from a `<figcaption>` when
  present, otherwise the image `title` attribute.
- Optionally render links to PDF/Office files as inline Confluence previews,
  controlled by a new `mkdocs.yml` config flag (default off).

---

## Feature A — Image captions

### Decisions

- **New IR field:** `ImageNode.caption: str | None = None`, kept distinct from
  `alt` (accessibility) and `title` (tooltip).
- **Source precedence:**
  1. `<figure>…<figcaption>…</figcaption></figure>` wrapping the image →
     caption = figcaption text; the figure wrapper is unwrapped to a bare
     `ImageNode`.
  2. Else image `title` (`![alt](img.png "cap")`) → caption = title, and `title`
     is **cleared** so it is not *also* emitted as a hover tooltip.
- **Applies to** both local (`ri:attachment`) and external (`ri:url`) images.
- **Emission:** when `caption` is set, nest a caption child inside `<ac:image>`:

  ```xml
  <ac:image ...>
    <ri:attachment ri:filename="arch.png"/>
    <ac:caption><p>Figure 1: System overview</p></ac:caption>
  </ac:image>
  ```

  (Exact `ac:caption` placement/wrapping verified against Atlassian storage-format
  docs and pinned by tests at implementation time.)

### Sequencing (two sub-parts of unequal cost)

The parser does **not** currently model figures — `<figure markdown>` lands as a
`RawHTML` block today. So:

- **A1 — title path (low-hanging, build first):** IR field + emitter caption
  wrapping + `title`→`caption` fallback with tooltip suppression. Small, self-
  contained, ships the core value.
- **A2 — figure/figcaption path (larger, build second):** recognize the
  `<figure>`/`<figcaption>` structure and collapse it into an `ImageNode` with
  caption, taking precedence over `title`. This is real parsing/transform work.

Both land in the same spec; A1 is independently shippable.

### Data flow

1. Parser produces `ImageNode` with `title` as today (unchanged).
2. New `transforms/captions.py` `resolve_captions(nodes)`:
   - **A2:** detect figure-wrapped images, set `caption` from figcaption, unwrap.
   - **A1:** for any `ImageNode` with a `title` and no `caption`, set
     `caption = title` and clear `title`.
3. `compiler/page.py` calls `resolve_captions` in the transform pipeline.
4. `emitter/xhtml.py` `_emit_image` nests `<ac:caption>` when `caption` is set.

### Components touched

| File | Change |
|---|---|
| `ir/nodes.py` | Add `ImageNode.caption: str \| None = None` |
| `transforms/captions.py` | New transform: figcaption + title→caption resolution |
| `compiler/page.py` | One line: run `resolve_captions` in the pipeline |
| `emitter/xhtml.py` | `_emit_image` nests `<ac:caption>` when caption present |
| `docs/features.md`, `README.md` | Document caption behavior |

### Testing (TDD)

- Image with `title` → caption rendered; no `ac:title` tooltip remains.
- Image with no title and no figure → no caption (unchanged output).
- External (`ri:url`) image with title → caption rendered.
- `<figure>`+`<figcaption>` → caption from figcaption; figure unwrapped.
- Figure caption takes precedence over a title on the same image.
- `alt` is always preserved as `ac:alt` independent of caption.

---

## Feature B — Attachment inline preview

### Decisions

- **Config:** new `ConfluenceConfig.attachment_preview: bool = False`, parsed from
  `confluence.attachment_preview`. Default **off** → current download-link output
  is byte-for-byte unchanged (backwards compatible).
- **Previewable extension set (module constant):**
  `.pdf .doc .docx .xls .xlsx .ppt .pptx`. Anything else stays a normal attachment
  download link.
- **Placement:** *always* preview an eligible link, even inside a sentence
  (user decision). The `view-file` macro is block-level; Confluence tolerates a
  structured macro in inline flow.
- **Label caveat:** the `view-file` macro renders from the attachment and has no
  label slot, so the Markdown link text is dropped in favor of the file preview.
- **New IR node** rather than an emitter global — consistent with the codebase's
  node-per-construct pattern (`MermaidDiagram`, `GridCards`, `ChildrenMacro`).

### Config

```yaml
confluence:
  base_url: https://yourorg.atlassian.net/wiki
  # ...
  attachment_preview: true   # default false
```

- Absent / false → download links (current behavior).
- Non-bool value → `ConfigError`, matching existing validation style.

### Data flow

1. `load_config` parses `attachment_preview` into
   `ConfluenceConfig.attachment_preview: bool = False`.
2. `resolve_local_assets` runs as today, setting `LinkNode.attachment_name` on
   local non-`.md` file links (no change).
3. New `transforms/attachment_previews.py`
   `resolve_attachment_previews(nodes, *, enabled)`: when `enabled`, replace any
   `LinkNode` with an `attachment_name` whose extension is in the previewable set
   with a new `AttachmentPreview(filename=…)` node. Runs **after**
   `resolve_local_assets`.
4. `compiler/page.py` passes
   `config.confluence.attachment_preview` (falling back to `False` when no
   confluence block) to the new transform.
5. `emitter/xhtml.py` `_emit_attachment_preview` emits:

   ```xml
   <ac:structured-macro ac:name="view-file">
     <ac:parameter ac:name="name"><ri:attachment ri:filename="spec.pdf"/></ac:parameter>
   </ac:structured-macro>
   ```

   (Exact macro name/params verified against Atlassian docs and pinned by tests.)

### Components touched

| File | Change |
|---|---|
| `loader/config.py` | New `attachment_preview` field; parse + validate from `confluence:` block |
| `ir/nodes.py` | New `AttachmentPreview` node (`filename: str`) |
| `transforms/attachment_previews.py` | New transform: eligible link → `AttachmentPreview` |
| `compiler/page.py` | Thread config flag → new transform |
| `emitter/xhtml.py` | `_emit_attachment_preview` → `view-file` macro |
| `docs/features.md`, `README.md` | Document the new config key |

### Testing (TDD)

**config**
- `attachment_preview: true` parses to `True`; absent → `False`; non-bool →
  `ConfigError`.

**transform**
- Enabled + `.pdf`/`.docx`/etc. link with `attachment_name` → `AttachmentPreview`.
- Enabled + non-previewable extension (`.zip`, `.csv`) → unchanged download link.
- Disabled → no change for any extension.
- External URL / internal `.md` link → never previewed.

**emitter**
- `AttachmentPreview` → correct `view-file` storage XML with the attachment
  filename.

**integration**
- One `compile_page` test: enabled flag yields a `view-file` macro; default
  (off) yields the existing download link.

---

## Out of scope (YAGNI)

- Per-extension or configurable preview lists (fixed PDF + Office set).
- A "preview only when alone in a paragraph" placement rule (user chose always).
- Preview display tuning (height, thumbnail vs full) beyond the macro default.
- Caption styling / numbering / cross-references.
- Captions sourced from `alt` text.
