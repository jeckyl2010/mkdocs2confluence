# mk2conf — MkDocs to Confluence

A Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML and publishes it to Confluence.

It is a **compiler/transpiler**, not an HTML converter — every Markdown construct is mapped to the equivalent native Confluence macro or element, so pages look and behave like hand-authored Confluence content.

---

## Installation

Requires Python 3.12+.

**From the latest GitHub release** (recommended):

```bash
pip install https://github.com/jeckyl2010/mkdocs2confluence/releases/download/v0.1.4/mkdocs_to_confluence-0.1.4-py3-none-any.whl
```

Or with `pipx` for an isolated install (no virtual environment needed):

```bash
pipx install https://github.com/jeckyl2010/mkdocs2confluence/releases/download/v0.1.4/mkdocs_to_confluence-0.1.4-py3-none-any.whl
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
mk2conf publish [--config PATH] [--page PATH] [--dry-run]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to your `mkdocs.yml` |
| `--page PATH` | *(all nav pages)* | Publish a single page only |
| `--dry-run` | off | Print the publish plan without making any API calls |

#### Configuration

Add a `confluence:` block to your `mkdocs.yml`:

```yaml
confluence:
  base_url: https://yourorg.atlassian.net
  space_key: TECH
  email: user@example.com
  token: !ENV CONFLUENCE_API_TOKEN   # never hardcode the token
  parent_page_id: "123456"           # optional root page
```

The API token is read from (in priority order):
1. The `token:` field in `mkdocs.yml` (typically via `!ENV CONFLUENCE_API_TOKEN`)
2. `CONFLUENCE_API_TOKEN` environment variable
3. `MK2CONF_TOKEN` environment variable

#### Publish rules

- **Only pages in `nav:` are published** — the nav is the publish gate. Pages not listed in the nav are never touched, keeping drafts and WIP content private.
- Pages with `ready: false` in their YAML front matter are **skipped**, even if listed in the nav.
- Section nodes (nav groups without a page) are created as empty parent pages in Confluence, mirroring the nav hierarchy.
- Local images and file links are uploaded as Confluence page attachments automatically.

#### Examples

```bash
# See exactly what would be published (no API calls)
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml --dry-run

# Publish everything
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml

# Publish a single page
CONFLUENCE_API_TOKEN=xxx mk2conf publish --config mkdocs.yml --page guide/setup.md
```

---

## Supported Markdown features

### Block elements

| Feature | Confluence output |
|---|---|
| ATX headings `#` – `######` | `<h1>` – `<h6>` |
| Paragraphs | `<p>` |
| Fenced code blocks (`` ``` `` / `~~~`) | `code` macro with language, title, and line numbers |
| Bullet lists `- ` / `* ` / `+ ` | `<ul>/<li>` |
| Ordered lists `1. ` | `<ol>/<li>` |
| Task lists `- [x]` / `- [ ]` | `<ul>/<li>` (checked state preserved) |
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

### MkDocs / Material extensions

| Feature | Confluence output |
|---|---|
| `--8<--` file includes | Resolved before parsing |
| Admonitions `!!! type "title"` | `info` / `tip` / `warning` / `note` macro |
| Danger admonitions (`danger`, `error`, `bug`) | Custom red `panel` macro with 🚨 prefix |
| Collapsible admonitions `??? type` | `expand` macro |
| Content tabs `=== "Label"` | `expand` macros (one per tab) |
| Mermaid diagrams | `code` macro labelled `mermaid` |

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
│   ├── abbrevs.py      # *[ABBR]: definition extractor and stripper
│   ├── frontmatter.py  # YAML front matter extractor and field mapper
│   └── icons.py        # :material-x: / :fontawesome-x: shortcode → emoji mapping
├── transforms/
│   ├── abbrevs.py      # IR tree transform: abbreviation first-occurrence expansion
│   └── assets.py       # IR tree transform: local image/file path resolution + attachment naming
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
| **HTML comments** | Author notes (`<!-- ... -->`) | Stripped — no Confluence equivalent. |

---

## Roadmap

Planned features, roughly in priority order:

- [ ] **Internal link resolution** — rewrite `.md` hrefs to Confluence page titles using the nav resolver
- [ ] **View-only restrictions** — lock Confluence pages to the publishing service account so they can't be edited directly; Confluence is a read-only mirror of the Markdown source of truth
- [ ] **Full-width layout** — set `fullWidth: true` via the API so pages aren't constrained to the narrow default column
- [ ] **Mermaid diagram rendering** — currently degrades to a `code` macro labelled `mermaid` (readable, and renders automatically if the instance has a Mermaid plugin). Pre-rendering via self-hosted [Kroki](https://kroki.io) (`docker run -p 8000:8000 yuzutech/kroki`) is the preferred future path — no browser dependency.

**Completed:**

- [x] **Publish command** — Confluence Cloud v2 REST API; nav-driven (only pages in `nav:` are published); creates/updates pages and uploads attachments; `ready: false` front matter skips pages; section nodes become parent pages to mirror nav hierarchy; `--dry-run` support
- [x] **Local image and file attachments** — local images and file links resolved to absolute paths; collision-safe attachment names derived from `docs_dir`-relative path; uploaded per-page at publish time; local images embedded as base64 data URIs in the browser preview
- [x] **Material icon shortcodes** — `:material-x:` / `:fontawesome-x:` / `:octicons-x:` mapped to nearest Unicode emoji; unknown shortcodes stripped cleanly
- [x] **Abbreviation expansion** — first-occurrence inline expansion with Glossary fallback section
- [x] **YAML front matter** → Confluence Page Properties macro with field mapping and label extraction

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

