# mk2conf — MkDocs to Confluence

A Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML and publishes it to Confluence.

It is a **compiler/transpiler**, not an HTML converter — every Markdown construct is mapped to the equivalent native Confluence macro or element, so pages look and behave like hand-authored Confluence content.

---

## Installation

Requires Python 3.12+.

**From the latest GitHub release:**

```bash
pip install https://github.com/jeckyl2010/mkdocs2confluence/releases/latest/download/mkdocs_to_confluence-latest-py3-none-any.whl
```

Or with `pipx` for an isolated install:

```bash
pipx install https://github.com/jeckyl2010/mkdocs2confluence/releases/latest/download/mkdocs_to_confluence-latest-py3-none-any.whl
```

Find the exact URL for a specific version on the [Releases page](https://github.com/jeckyl2010/mkdocs2confluence/releases).

**From source** (see [Setup.md](Setup.md)):

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
| `--page PATH` | *(required)* | Relative path to the Markdown file |
| `--out FILE` | stdout | Write output to a file |
| `--html` | off | Render macros as styled HTML for local browser review |

The `--html` flag renders Confluence macros as visual HTML panels so you can review a page locally without a Confluence instance. It is for review only — the actual storage XHTML is always the `--html`-free output.

---

### `mk2conf publish`

Compile all pages listed in `nav:` and publish them to Confluence Cloud.

```
mk2conf publish [--config PATH] [--page PATH] [--section PATH] [--dry-run] [--report FILE]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to your `mkdocs.yml` |
| `--page PATH` | *(all nav pages)* | Publish a single page only |
| `--section PATH` | *(whole nav)* | Publish only a nav subtree (e.g. `Guide` or `Guide/Setup`) |
| `--dry-run` | off | Print the publish plan without making any API calls |
| `--report FILE` | *(none)* | Write a JSON publish report to `FILE` |

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
  full_width: true                   # optional: publish pages in full-width layout (default: true)
```

The API token is read from (in priority order):
1. The `token:` field in `mkdocs.yml` (typically via `!ENV CONFLUENCE_API_TOKEN`)
2. `CONFLUENCE_API_TOKEN` environment variable
3. `MK2CONF_TOKEN` environment variable

#### Publish rules

- **Only pages in `nav:` are published** — the nav is the publish gate. Pages not listed in the nav are never touched, keeping drafts and WIP content private.
- Pages with `ready: false` in their YAML front matter are **skipped**, even if listed in the nav.
- Section nodes (nav groups without a page) become empty parent pages in Confluence, mirroring the nav hierarchy.
- All locally linked assets are uploaded as Confluence page attachments automatically.

#### Mermaid rendering

| `mermaid_render` value | Behaviour |
|---|---|
| `kroki` *(default)* | Render via `https://kroki.io`. PNGs are cached in `~/.cache/mk2conf/mermaid/`. |
| `kroki:https://your-kroki` | Render via a self-hosted Kroki instance. |
| `none` | Skip rendering — fall back to a `code` macro labelled `mermaid`. |

If Kroki is unreachable the run continues, falling back to the `code` macro for affected diagrams.

#### Styling from extra.css

If your `mkdocs.yml` has an `extra_css:` list, mk2conf reads those files and applies a whitelisted set of CSS properties as inline `style="..."` attributes in the Confluence output.

| Selector | Applied to |
|---|---|
| `th`, `thead th` | Table header cells |
| `td` | Table body cells |
| `h1` – `h6` | Headings |
| `code` (not `pre code`) | Inline code spans |

Supported properties: `background-color`, `color`, `font-weight`, `font-style`, `font-size`, `text-align`, `border`.

CSS custom properties (`var(--name)`) are resolved automatically, including chained variables and `var(--name, fallback)` syntax.

**Works best with simple, flat CSS.** Complex Material for MkDocs theme overrides — compound selectors (`.md-typeset table:not([class]) thead th`), `color-mix()`, `@media` blocks, `:has()` etc. — are silently skipped. For these, maintain a small separate file:

```css
/* confluence-overrides.css */
:root { --primary: #d20014; }
th  { background-color: var(--primary); color: white; font-weight: 600; }
h1, h2, h3 { color: var(--primary); }
code { background-color: #f5f5f5; }
```

```yaml
extra_css:
  - stylesheets/extra.css             # full Material theme
  - stylesheets/confluence-overrides.css  # simple Confluence-targeted styles
```

---

## Supported Markdown features

### Block elements

| Feature | Confluence output |
|---|---|
| ATX headings `#` – `######` | `<h1>` – `<h6>` |
| Paragraphs | `<p>` |
| Fenced code blocks | `code` macro with language, title, and line numbers |
| Bullet lists | `<ul>/<li>` |
| Ordered lists | `<ol>/<li>` |
| Task lists `- [x]` / `- [ ]` | Native `<ac:task-list>` / `<ac:task>` macros |
| Tables (GFM pipe syntax) | `<table>` with header and column alignment |
| Blockquotes | `<blockquote>` |
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
| `<br>` / `<br/>` | `<br />` |
| `<sub>` / `<sup>` / `<u>` / `<small>` | Direct XHTML passthrough |
| `<mark>text</mark>` | `<span style="background-color: yellow;">` |
| `<kbd>text</kbd>` | `<code>` |
| `<s>text</s>` / `<del>text</del>` | `<span style="text-decoration: line-through;">` |

### MkDocs / Material extensions

| Feature | Confluence output |
|---|---|
| `--8<--` file includes | Resolved before parsing |
| Admonitions `!!! type "title"` | `info` / `tip` / `warning` / `note` macro |
| Danger admonitions (`danger`, `error`, `bug`) | Red `panel` macro with 🚨 prefix |
| Collapsible admonitions `??? type` | `expand` macro |
| Content tabs `=== "Label"` | `expand` macros (one per tab) |
| Details blocks `??? "title"` | `expand` macro |
| Footnotes `[^1]` | Superscript anchor links + *Footnotes* section at page bottom |
| Mermaid diagrams | PNG via Kroki, uploaded as attachment (`<ac:image ac:align="center">`) |
| Internal links `[text](page.md)` | Native Confluence page link; `#fragment` anchors preserved |
| `awesome-pages` nav (`.pages` files) | Fully supported |
| Edit link banner | `info` macro linking back to source in GitHub/GitLab |

### YAML front matter → Page Properties

A YAML front matter block is converted to a Confluence **Page Properties** macro, making it queryable via the Page Properties Report macro.

```yaml
---
title: "Architecture Proposal – IAM"
subtitle: "Hybrid Identity Hub"
documentId: AP-IAM-2026
version: "0.1"
lastUpdated: 2026-01-12
author: "Anders Hybertz"
tags: [architecture, iam]
ready: true
---
```

| Field | Notes |
|---|---|
| `title` | Used as the Confluence page title on publish |
| `subtitle` | Rendered as italic lead paragraph above the properties table |
| `tags` | Also applied as Confluence page labels |
| `ready` | `true` → ✅ Ready · `false` → 📝 Draft (skips publish) |
| `source` | Stripped (internal tooling field) |
| *other fields* | Title-cased key, value stringified |

If `repo_url` + `edit_uri` are set in `mkdocs.yml`, an **Edit Source** row links to the source file. If `site_url` is set, a **Published Page** row links to the rendered MkDocs site.

### Abbreviation expansion

MkDocs abbreviation definitions (`*[ABBR]: Full term`) are expanded inline — Confluence has no native `<abbr>` tooltip. The **first occurrence** in body text is expanded as `IAM (Identity and Access Management)`; subsequent occurrences are left as-is. Abbreviations that only appear in headings or code are collected into an auto-appended **Glossary** section.

### Graceful degradation

Any unrecognised block is preserved as a visible `warning` macro — no content is silently lost.

`<div class="grid" markdown>` (Material grid cards) has no Confluence equivalent. The wrapper is stripped; inner admonitions render sequentially.

---

## Known limitations

| Feature | Behaviour |
|---|---|
| **Admonition styling** | Native macros (`tip`, `info`, `warning`, `note`) use Confluence's fixed theme styling — no custom header/body colours. |
| **Abbreviation tooltips** | No native tooltip support. First occurrence expanded inline; remainder left as-is. |
| **Grid cards** | Wrapper stripped; inner admonitions rendered individually. |
| **Page width** | Confluence defaults to a narrow fixed-width column. mk2conf publishes with `fullWidth: true` by default (configurable). |
| **Page ordering** | Confluence sorts child pages alphabetically. The v2 REST API has no write endpoint for child ordering; nav order cannot be enforced. |
| **Code language aliases** | Pygments short aliases (`py`, `js`, `yml`, `ts`, `sh`) are passed through as-is; Confluence requires full language names for syntax highlighting. |

---

## Roadmap

- [ ] **Delete orphaned pages** — detect and remove Confluence pages that were previously published but have since been removed from `nav:`.
- [ ] **GitHub Actions workflow** — auto-publish on push to main.

---

## Development

See [Setup.md](Setup.md) for environment setup.

```bash
pytest           # run tests
ruff check src   # lint
mypy src         # type-check
```
