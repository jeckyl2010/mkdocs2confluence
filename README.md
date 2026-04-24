# mk2conf — MkDocs to Confluence

A Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML and publishes it to Confluence.

It is a **compiler/transpiler**, not an HTML converter — every Markdown construct is mapped to the equivalent native Confluence macro or element, so pages look and behave like hand-authored Confluence content.

---

## Installation

Requires Python 3.12+.

**From the latest GitHub release** (recommended):

```bash
pip install https://github.com/jeckyl2010/mkdocs2confluence/releases/download/v0.4.39/mkdocs_to_confluence-0.4.39-py3-none-any.whl
```

Or with `pipx` for an isolated install (no virtual environment needed):

```bash
pipx install https://github.com/jeckyl2010/mkdocs2confluence/releases/download/v0.4.39/mkdocs_to_confluence-0.4.39-py3-none-any.whl
```

**From source** (see [Setup.md](Setup.md) for the full dev environment guide):

```bash
git clone https://github.com/jeckyl2010/mkdocs2confluence.git
cd mkdocs2confluence
pip install -e ".[dev]"
```

---

## Quick start

```bash
# Print Confluence storage XHTML to stdout
mk2conf preview --config mkdocs.yml --page index.md

# Open a browser-friendly HTML preview
mk2conf preview --config mkdocs.yml --page index.md --html --out /tmp/preview.html

# Dry-run: see what would be published without touching Confluence
mk2conf publish --config mkdocs.yml --dry-run

# Publish all nav pages to Confluence
CONFLUENCE_API_TOKEN=your_token mk2conf publish --config mkdocs.yml
```

---

## Commands

### `mk2conf preview`

Compile a single page and inspect the output — no network connection required.

```
mk2conf preview [--config PATH] --page PATH [--out FILE] [--html]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to your `mkdocs.yml` |
| `--page PATH` | *(required)* | Relative path to the Markdown file (matches the path used in `nav`) |
| `--out FILE` | stdout | Write output to a file instead of printing |
| `--html` | off | Render Confluence macros as styled browser HTML for local inspection |

#### Examples

```bash
# Raw Confluence XHTML (what gets sent to Confluence)
mk2conf preview --config docs/mkdocs.yml --page index.md

# Browser preview — opens nicely in any browser
mk2conf preview --config docs/mkdocs.yml --page guide/installation.md \
  --html --out /tmp/preview.html && open /tmp/preview.html
```

---

### `mk2conf publish`

Compile all pages listed in the `nav:` and publish them to Confluence Cloud.

```
mk2conf publish [--config PATH] [--page PATH] [--section PATH] [--dry-run] [--report FILE]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to your `mkdocs.yml` |
| `--page PATH` | *(all nav pages)* | Publish a single page only |
| `--section PATH` | *(whole nav)* | Publish only a nav subtree (e.g. `Guide` or `Guide/Setup`) |
| `--dry-run` | off | Print the publish plan without making any API calls |
| `--report FILE` | *(none)* | Write a JSON publish report to `FILE` after the run |

#### Configuration

Add a `confluence:` block to your `mkdocs.yml`:

```yaml
confluence:
  base_url: https://yourorg.atlassian.net
  space_key: TECH
  email: user@example.com
  token: !ENV CONFLUENCE_API_TOKEN   # never hardcode the token
  parent_page_id: "123456"           # optional root page
  mermaid_render: kroki              # optional: "kroki" (default), "kroki:https://your-kroki" or "none"
```

The API token is read from (in priority order):
1. The `token:` field in `mkdocs.yml` (typically via `!ENV CONFLUENCE_API_TOKEN`)
2. `CONFLUENCE_API_TOKEN` environment variable
3. `MK2CONF_TOKEN` environment variable

#### Mermaid rendering

| `mermaid_render` value | Behaviour |
|---|---|
| `kroki` *(default)* | Render via `https://kroki.io` (public instance). Diagrams are POSTed as plain text; PNGs are cached locally in `~/.cache/mk2conf/mermaid/`. |
| `kroki:https://your-kroki` | Render via a self-hosted Kroki instance (e.g. `docker run -p 8000:8000 yuzutech/kroki`). |
| `none` | Skip rendering entirely — fall back to a `code` macro labelled `mermaid`. |

If Kroki is unreachable, rendering degrades gracefully to the `code` macro fallback and a warning is printed — the publish run continues.

#### Publish rules

- **Only pages in `nav:` are published** — the nav is the publish gate. Pages not listed in the nav are never touched, keeping drafts and WIP content private.
- Pages with `ready: false` in their YAML front matter are **skipped**, even if listed in the nav.
- Section nodes (nav groups without a page) are created as empty parent pages in Confluence, mirroring the nav hierarchy.
- All locally linked assets (images, PDFs, Word, Excel, and any other file type) are uploaded as Confluence page attachments automatically.

#### Examples

```bash
# See exactly what would be published (no API calls)
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml --dry-run

# Publish everything
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml

# Publish a single page
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml --page guide/setup.md

# Publish only one nav section
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml --section appendix

# Publish and write a JSON report
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml --report publish-report.json
```

---

## Supported Markdown features

### Block elements

| Feature | Confluence output |
|---|---|
| ATX headings `#` – `######` | `<h1>` – `<h6>` |
| Paragraphs | `<p>` |
| Fenced code blocks (`` ``` `` / `~~~`) | `code` macro with language, title, and line numbers. Confluence accepts the full language name (e.g. `python`, `javascript`, `yaml`); Pygments short aliases (`py`, `js`, `yml`, `ts`, `sh`) are passed through as-is and will render without syntax highlighting on Confluence. |
| Bullet lists `- ` / `* ` / `+ ` | `<ul>/<li>` |
| Ordered lists `1. ` | `<ol>/<li>` |
| Task lists `- [x]` / `- [ ]` | Native `<ac:task-list>` / `<ac:task>` macros with `complete`/`incomplete` status |
| Tables (GFM pipe syntax) | `<table>` with header and column alignment |
| Blockquotes `> ` | `<blockquote>` |
| Horizontal rules `---` | `<hr/>` |

### Inline elements

| Feature | Confluence output |
|---|---|
| `**bold**` / `__bold__` | `<strong>` |
| `*italic*` | `<em>` |
| `~~strikethrough~~` | `<s>` |
| `` `inline code` `` | `<code>` |
| `[text](url)` | `<a href="...">` |
| `[text](file.pdf)` | `<ac:link><ri:attachment .../>` (uploaded as attachment) |
| `![alt](src)` | `<ac:image>` with `<ri:attachment>` (local) or `<ri:url>` (remote) |
| `<br>` / `<br/>` | `<br />` (hard line break) |
| `<sub>` / `<sup>` / `<u>` / `<small>` | Direct XHTML passthrough |
| `<mark>text</mark>` | `<span style="background-color: yellow;">` |
| `<kbd>text</kbd>` | `<code>` (monospace) |
| `<s>text</s>` / `<del>text</del>` | `<span style="text-decoration: line-through;">` |

### MkDocs / Material extensions

| Feature | Confluence output |
|---|---|
| `--8<-- ` file includes | Resolved before parsing |
| Admonitions `!!! type "title"` | `info` / `tip` / `warning` / `note` macro |
| Danger admonitions (`danger`, `error`, `bug`) | Custom red `panel` macro with 🚨 prefix |
| Collapsible admonitions `??? type` | `expand` macro |
| Content tabs `=== "Label"` (`pymdownx.tabbed`) | `expand` macros (one per tab) |
| Details blocks `??? "title"` (`pymdownx.details`) | `expand` macro |
| Footnotes `[^1]` / `[^1]: text` (`pymdownx.footnotes`) | Inline superscript anchor links + *Footnotes* section at page bottom |
| Mermaid diagrams ` ```mermaid ` | Rendered to PNG via [Kroki](https://kroki.io) and uploaded as a page attachment (`<ac:image>`). SHA256-keyed local cache (`~/.cache/mk2conf/mermaid/`) avoids re-fetching unchanged diagrams. Falls back to a `code` macro if rendering fails. Configurable via `mermaid_render` — see below. |
| Internal links `[text](page.md)` | `<ac:link><ri:page ac:title="...">` native Confluence page link; `#fragment` anchors preserved |
| `awesome-pages` nav (`.pages` files) | Fully supported — nav is resolved from `.pages` files; bare directory entries auto-expand into sections |
| Edit link banner | `info` macro with a link back to the source file in GitHub/GitLab (uses `repo_url` + `edit_uri` from `mkdocs.yml`) |

### YAML front matter → Page Properties

Pages with a YAML front matter block are automatically converted to a Confluence **Page Properties** macro (`details`), making the metadata queryable across your space via the Page Properties Report macro.

```yaml
---
title: "Architecture Proposal – IAM"
subtitle: "Hybrid Identity Hub for manufacturing sites"
documentId: AP-IAM-HYBRID-2026
version: "0.1"
lastUpdated: 2026-01-12
author: "Anders Hybertz"
tags: [architecture, iam, keycloak]
ready: true
---
```

Field mapping:

| Front matter field | Display name | Notes |
|---|---|---|
| `title` | Title | Used as the Confluence page title on publish |
| `subtitle` | — | Rendered as an italic lead paragraph above the properties table |
| `documentId` | Document ID | — |
| `version` | Version | — |
| `lastUpdated` | Last Updated | — |
| `author` | Author | — |
| `tags` | Tags | Also applied as Confluence page labels on publish |
| `ready` | Status | `true` → ✅ Ready · `false` → 📝 Draft |
| `source` | — | **Stripped** (internal tooling field) |
| *other fields* | Title-cased key | Value stringified |

> **Auto-generated rows:** if `repo_url` + `edit_uri` are set in `mkdocs.yml`, an **Edit Source** row is added linking to the source file in GitHub/GitLab. If `site_url` is set, a **Published Page** row links to the rendered MkDocs page.

### Abbreviation expansion

MkDocs abbreviation definitions (`*[ABBR]: Full term`) are expanded automatically — Confluence has no native tooltip/`<abbr>` equivalent.

**Behaviour:**

- The **first occurrence** of each abbreviation in body text is expanded inline: `IAM` → `IAM (Identity and Access Management)`
- **Subsequent occurrences** are left as plain text
- Headings, table headers, admonition titles, code blocks, and link text are **skipped** (expansion there would look odd)
- If an abbreviation only appears in skipped contexts, it is listed in an auto-appended **Glossary** section at the bottom of the page
- Definition lines are stripped from the output — they never appear as raw text

Abbreviation definitions can live in the page itself or in an included file (e.g. `--8<-- "includes/legend-glossary.md"`).

### Graceful degradation

Any block the parser does not recognise is preserved as a visible `warning` macro in the output so no content is silently lost.

The following Material for MkDocs features are **intentionally suppressed** (wrapper stripped, inner content preserved):

| Feature | Reason | Behaviour |
|---|---|---|
| `<div class="grid" markdown>` | CSS-only multi-column layout — no Confluence equivalent | Wrapper removed; admonitions inside render sequentially |

---

## Local browser preview

The `--html` flag post-processes the Confluence XHTML and renders macros as styled HTML panels, so you can review a page in any browser without a Confluence instance:

| Macro | Preview rendering |
|---|---|
| `code` | Dark code panel with language label and optional title |
| `info` / `tip` / `warning` / `note` | Colour-coded panels (blue / green / orange / grey) |
| `panel` (danger types) | Red panel with 🚨 title prefix |
| `expand` | Collapsible `<details>` element |
| `details` (Page Properties) | 📋 Page Properties card with metadata table |
| Unknown macros | Labelled dashed placeholder |

> **Note:** `--html` output is for local review only. The actual content sent to Confluence is always the raw XHTML (without `--html`).

---

## Project structure

```
src/mkdocs_to_confluence/
├── cli.py              # CLI entrypoint (mk2conf)
├── loader/
│   ├── config.py       # mkdocs.yml loader (!ENV + confluence: block)
│   ├── nav.py          # nav resolver (auto-discovers pages when nav: is absent)
│   └── page.py         # single-page loader (exact + suffix matching)
├── preprocess/
│   ├── includes.py     # --8<-- include/snippet preprocessor + HTML comment stripping
│   ├── fence.py        # FenceTracker: shared fenced-code-block state machine
│   ├── abbrevs.py      # *[ABBR]: definition extractor and stripper
│   ├── frontmatter.py  # YAML front matter extractor and field mapper
│   └── icons.py        # :material-x: / :fontawesome-x: shortcode → emoji mapping
├── transforms/
│   ├── abbrevs.py      # IR tree transform: abbreviation first-occurrence expansion
│   ├── assets.py       # IR tree transform: local image/file path resolution + attachment naming
│   ├── images.py       # IR tree transform: image src resolution
│   ├── internallinks.py# IR tree transform: .md hrefs → Confluence page title links
│   ├── mermaid.py      # IR tree transform: Mermaid diagram rendering via Kroki → PNG attachments
│   └── editlink.py     # IR tree transform: inject edit-on-GitHub banner
├── ir/
│   └── nodes.py        # immutable IR node types
├── parser/
│   └── markdown.py     # Markdown → IR compiler
├── emitter/
│   └── xhtml.py        # IR → Confluence storage XHTML emitter
├── preview/
│   └── render.py       # XHTML → browser HTML renderer (local images as base64)
└── publisher/
    ├── client.py       # Confluence Cloud REST client (v2 pages API, v1 attachments)
    └── pipeline.py     # nav-driven compile + plan/execute publish loop
```

---

## Known Confluence Limitations

These are deliberate tradeoffs, not bugs. The tool maps MkDocs constructs to the closest native Confluence equivalent; some visual fidelity is lost by design.

| Feature | MkDocs / Material | Confluence behaviour |
|---|---|---|
| **Admonition styling** | Distinct header background + pastel body | Single-block macro with fixed theme styling — no separate header/body colours. Native macros (`tip`, `info`, `warning`, `note`) are used as they are portable, dark-mode safe, and work everywhere. |
| **Abbreviation tooltips** | `*[ABBR]: definition` hover tooltips | No native tooltip support. First occurrence in body text is expanded inline (`ABBR (definition)`); remaining occurrences are left as-is. A Glossary section is appended for any abbreviations that only appear in headings or other non-expandable contexts. |
| **Grid cards** (`<div class="grid" markdown>`) | Side-by-side admonition cards | Suppressed — Confluence has no equivalent responsive grid layout. The inner admonitions are still rendered individually. |
| **Page width** | Full responsive width | Confluence defaults to a narrow fixed-width column. Set **Full width** in page settings (⚙️), or the upcoming `publish` command will set this automatically via the API. |
| **Page ordering** | Nav order from `mkdocs.yml` | Confluence sorts child pages alphabetically by default. The Confluence REST API v2 exposes `childPosition` as a readable field but provides no write endpoint to set it. The v1 API has a `PUT /content/{id}/move/{position}/{targetId}` endpoint that can reorder pages, but it is not available in v2 and may be deprecated in future. Until Atlassian adds writable ordering to v2, nav order cannot be reliably enforced. |

---

## Roadmap

Planned features, roughly in priority order:

- [ ] **Delete orphaned pages** — detect pages in Confluence that were previously published but have since been removed from `nav:`, and delete or archive them automatically.
- [ ] **GitHub Actions auto-publish** — workflow that builds and publishes to Confluence on push to main, driven by the existing `--report` JSON output.

**Completed:**

- [x] **Inline HTML passthrough** — `<br>`, `<mark>`, `<kbd>`, `<sub>`, `<sup>`, `<u>`, `<s>`/`<del>`, `<small>` detected in inline text and mapped to Confluence storage-format equivalents: direct XHTML passthrough for the valid tags; `<mark>` → `<span style="background-color: yellow;">`, `<kbd>` → `<code>`, `<s>`/`<del>` → `<span style="text-decoration: line-through;">`. Unclosed tags fall through safely as literal text.
- [x] **Section index page** — if a nav section contains an `index.md` child, it is published as a Confluence page (titled after the section) with the `index.md` content as its body. All other children nest under it. Mirrors Material for MkDocs section index behaviour exactly. Sections without `index.md` continue to use Confluence folders.
- [x] **Task lists** (`- [x]` / `- [ ]`) — checked/unchecked items rendered as native Confluence `<ac:task-list>` / `<ac:task>` macros with `complete`/`incomplete` status.
- [x] **Smart asset skip** — assets already in Confluence are skipped if the local file's `mtime` is not newer than the attachment's `version.createdAt` timestamp; no local state required. Summary shows `N uploaded, N skipped`.
- [x] **Full-width layout** — pages published with `fullWidth: true` via the content properties API; configurable via `full_width:` in `confluence:` config block.
- [x] **Tables** — GFM pipe tables rendered as native Confluence `<table>` storage format.
- [x] **Mermaid diagram rendering** — ` ```mermaid ` blocks rendered to PNG via [Kroki](https://kroki.io) (POST API, no encoding, no URL-length limits). PNGs uploaded as page attachments. SHA256 cache avoids re-fetching unchanged diagrams. Self-hosted Kroki supported via `mermaid_render: kroki:https://your-host`. Graceful fallback to `code` macro if rendering fails.
- [x] **Published Page link in Page Properties** — if `site_url` is set in `mkdocs.yml`, each published page gets a "Published Page" row in its Page Properties macro linking to the rendered MkDocs site URL.
- [x] **Scoped publish by nav section** — `--section "Guide"` scopes compile and publish to a single subtree of the nav; supports bare folder names as well as slash-separated paths (`"Guide/Setup"`)
- [x] **Sequential asset uploads** — assets uploaded one at a time per page; Confluence holds a page-level write lock per attachment POST so concurrent uploads cause HTTP 500 transaction rollbacks.
- [x] **Publish summary report** — structured output after every run (`N created, N updated, N skipped · N uploaded, N skipped`); `--report FILE` writes a JSON report; non-zero exit on errors.
- [x] **Source link in Page Properties** — each published page includes a link back to its editable source file in GitHub/GitLab as a row in the Page Properties table (driven by `repo_url` + `edit_uri` in `mkdocs.yml`).
- [x] **Confluence REST API v2 compliance** — `minorEdit: true` prevents watcher notifications on automated updates; `find_page` no longer fetches the full page body; `id` removed from PUT body; `list_attachments` migrated to v2 endpoint; session `Content-Type` fixed for multipart uploads.
- [x] **Material icon shortcodes** — `:material-x:` / `:fontawesome-x:` / `:octicons-x:` mapped to BMP-safe Unicode symbols (≤ U+FFFF); unknown shortcodes stripped cleanly; nav titles are also cleaned.
- [x] **Internal link resolution** — `.md` hrefs rewritten to `<ac:link><ri:page ri:content-title="...">` Confluence page links using the nav resolver; anchors (`#fragment`) stripped gracefully.
- [x] **Ordered list numbering** — loose lists (blank-line-separated items) and items with continuation text correctly merge into a single `<ol>` node instead of each item rendering as `1.`
- [x] **Publish command** — Confluence Cloud v2 REST API; nav-driven (only pages in `nav:` are published); creates/updates pages and uploads attachments; `ready: false` front matter skips pages; section nodes become parent pages to mirror nav hierarchy; `--dry-run` support.
- [x] **Local asset attachments** — all locally linked assets (images, PDFs, Word, Excel, and any other file type) resolved to absolute paths; collision-safe attachment names derived from `docs_dir`-relative path; uploaded as Confluence page attachments at publish time; local images embedded as base64 data URIs in the browser preview.
- [x] **Abbreviation expansion** — first-occurrence inline expansion with Glossary fallback section.
- [x] **YAML front matter** → Confluence Page Properties macro with field mapping and label extraction.
- [x] **Footnotes** (`pymdownx.footnotes`) — `[^label]` inline refs → superscript anchor links; definitions → anchored *Footnotes* section at page bottom.
- [x] **Content tabs** (`pymdownx.tabbed`) — `=== "Label"` blocks → `expand` macros (one per tab).
- [x] **Collapsible details** (`pymdownx.details`) — `??? "title"` blocks → `expand` macro.
- [x] **awesome-pages nav** — `.pages` files resolved natively; bare directory entries auto-expand into sections; full hierarchy preserved in Confluence folder structure.

---

## Architecture Decisions

Key design choices recorded for future contributors.

### Output format — Confluence Storage Format (XHTML), not ADF

The emitter produces **Confluence Storage Format** (XHTML strings; `"representation": "storage"` in the API payload). The newer **Atlassian Document Format (ADF)** (`"representation": "atlas_doc_format"`) is JSON-based and is what the Confluence editor writes internally.

Storage format was chosen because:
- **Full macro coverage** — Code Block, Info/Warning/Note/Tip, Page Properties, Expand, and other native macros have complete Storage Format support. Many are not yet exposed in ADF.
- **v2 API accepts both** — we are not locked in. If ADF gains full macro parity this could be revisited.
- **Proven approach** — all existing open-source MkDocs-to-Confluence tools use Storage Format for the same reason.

### Markdown parser — hand-rolled, swap-ready

The parser (`parser/markdown.py`) is deliberately hand-rolled rather than wrapping a third-party library. This was the right call for the current feature set, but the architecture is designed so the parser can be replaced without touching the IR or the emitter.

Two candidates worth evaluating when we hit complex CommonMark edge cases (tables, nested lists, inline HTML):

| Library | Fit for this project |
|---|---|
| **`markdown-it-py`** | Best fit — closest in spirit to Python-Markdown (which MkDocs uses), good plugin ecosystem, Material extensions are more likely to map cleanly |
| **`marko`** | Elegant custom-renderer API (write `render_heading(element)` etc.), pure CommonMark, but Material-specific extensions (admonitions, content tabs, attr lists) would need custom element extensions |

Decision deferred until the hand-rolled parser becomes a maintenance burden or blocks a feature.

---

## Development

See [Setup.md](Setup.md) for environment setup.

```bash
# Run tests
pytest

# Lint
ruff check src tests

# Type-check
mypy src
```

