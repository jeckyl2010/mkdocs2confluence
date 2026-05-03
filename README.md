# mk2conf — MkDocs / Zensical to Confluence

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/mkdocs2confluence)](https://pypi.org/project/mkdocs2confluence/)
[![Downloads](https://img.shields.io/pypi/dm/mkdocs2confluence)](https://pypi.org/project/mkdocs2confluence/)
[![Latest Release](https://img.shields.io/github/v/release/jeckyl2010/mkdocs2confluence)](https://github.com/jeckyl2010/mkdocs2confluence/releases/latest)
[![CI](https://github.com/jeckyl2010/mkdocs2confluence/actions/workflows/ci.yml/badge.svg)](https://github.com/jeckyl2010/mkdocs2confluence/actions/workflows/ci.yml)
[![Release](https://github.com/jeckyl2010/mkdocs2confluence/actions/workflows/release.yml/badge.svg)](https://github.com/jeckyl2010/mkdocs2confluence/actions/workflows/release.yml)
[![codecov](https://codecov.io/gh/jeckyl2010/mkdocs2confluence/graph/badge.svg)](https://codecov.io/gh/jeckyl2010/mkdocs2confluence)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/type--checked-mypy-blue.svg)](https://mypy-lang.org/)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

A Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML and publishes it directly to Confluence Cloud. It is a **compiler/transpiler**, not an HTML converter — every construct maps to its native Confluence equivalent, so pages look and behave like hand-authored Confluence content.

> **Zensical compatible** — [Zensical](https://zensical.org/) is the modern successor to MkDocs + Material for MkDocs. Since it uses the same `mkdocs.yml` format and Python Markdown extensions, your Zensical project works with mk2conf today with no changes required.

---

## Installation

Requires Python 3.12+. The PyPI package is `mkdocs2confluence`; the CLI command is `mk2conf`.

```bash
pip install mkdocs2confluence
# or, for an isolated install:
pipx install mkdocs2confluence
```

**From source** (see [Setup.md](Setup.md)):

```bash
git clone https://github.com/jeckyl2010/mkdocs2confluence.git
cd mkdocs2confluence && pip install -e ".[dev]"
```

---

## Quick start

```bash
# Inspect the Confluence storage XHTML for a page
mk2conf preview --page index.md

# Open a live browser preview — rebuilds on every file save
mk2conf preview --page index.md --watch
mk2conf preview --section Guide --watch

# Dry-run: see what would be published without touching Confluence
mk2conf publish --dry-run

# Publish all nav pages to Confluence
mk2conf publish
```

---

## Configuration

Add a `confluence:` block to your `mkdocs.yml`:

```yaml
confluence:
  base_url: https://yourorg.atlassian.net
  space_key: TECH
  email: user@example.com
  token: !ENV CONFLUENCE_API_TOKEN   # never hardcode the token
  parent_page_id: "123456"           # optional root page
  mermaid_render: kroki              # "kroki" (default) | "kroki:https://your-kroki" | "none"
  full_width: true                   # default: true
```

The API token is read from (in priority order):

1. `token:` in `mkdocs.yml` — typically via `!ENV CONFLUENCE_API_TOKEN`
2. `CONFLUENCE_API_TOKEN` environment variable
3. `MK2CONF_TOKEN` environment variable

---

## Commands

### `mk2conf preview`

Compile and inspect output locally — no Confluence API calls. Mermaid diagrams are rendered via Kroki unless `mermaid_render: none` is set.

```
mk2conf preview [--config PATH] --page PATH [--out FILE] [--html] [--watch]
mk2conf preview [--config PATH] --section NAME [--out FILE] [--watch]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to `mkdocs.yml` |
| `--page PATH` | *(required unless --section)* | Relative path to the Markdown file |
| `--section NAME` | *(none)* | Render all pages in a nav section as a browseable HTML index |
| `--out FILE` | stdout | Write output to a file or directory |
| `--html` | off | Render macros as styled browser-viewable HTML |
| `--watch` | off | Serve on `http://localhost:8765` and auto-rebuild on file changes. Implies `--html`. `Ctrl+C` to stop. |

`--html` is for local review only — the actual Confluence storage XHTML is the `--html`-free output.

---

### `mk2conf publish`

Compile all pages in `nav:` and publish to Confluence Cloud.

```
mk2conf publish [--config PATH] [--page PATH] [--section PATH] [--dry-run] [--report FILE] [--prune]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to `mkdocs.yml` |
| `--page PATH` | *(all nav pages)* | Publish a single page only |
| `--section PATH` | *(whole nav)* | Publish only a nav subtree (e.g. `Guide/Setup`) |
| `--dry-run` | off | Print the publish plan; no Confluence API writes |
| `--report FILE` | *(none)* | Write a JSON publish report |
| `--prune` | off | Delete managed pages no longer in `nav:`. Only pages stamped by mk2conf are eligible — manually-created Confluence pages are never touched. Ignored on partial (`--page` / `--section`) runs. |

#### Publish behaviour

- **Only `nav:` pages are published** — pages absent from the nav are never touched (natural draft gate).
- Pages with `ready: false` in front matter are skipped, even if listed in `nav:`.
- Section nodes (nav groups without a page) become empty parent pages, mirroring the nav hierarchy.
- Local assets are uploaded as Confluence page attachments automatically.
- **Unchanged pages are skipped** — a `sha256` hash of the compiled output is stored as a hidden page property; pages with identical content since the last run produce no version bump and no notification.

#### Mermaid rendering

| `mermaid_render` | Behaviour |
|---|---|
| `kroki` *(default)* | Render via `https://kroki.io`. PNGs cached in `~/.cache/mk2conf/mermaid/`. |
| `kroki:https://your-kroki` | Render via a self-hosted Kroki instance. |
| `none` | Fall back to a `code` macro labelled `mermaid`. |

If Kroki is unreachable the run continues, falling back to the `code` macro for affected diagrams.

#### Styling from extra.css

If `mkdocs.yml` lists `extra_css:` files, mk2conf reads them and applies a whitelisted set of CSS properties as inline `style="..."` attributes on Confluence output.

| Selector | Applied to |
|---|---|
| `th`, `thead th` | Table header cells |
| `td` | Table body cells |
| `h1` – `h6` | Headings |
| `code` (not `pre code`) | Inline code spans |

Supported properties: `background-color`, `color`, `font-weight`, `font-style`, `font-size`, `text-align`, `border`. CSS custom properties (`var(--name)`) are resolved automatically, including chained variables and `var(--name, fallback)` syntax.

Complex Material theme overrides (compound selectors, `color-mix()`, `@media`, `:has()`) are silently skipped. For best results, maintain a small dedicated overrides file:

```css
/* confluence-overrides.css */
:root { --primary: #d20014; }
th  { background-color: var(--primary); color: white; font-weight: 600; }
h1, h2, h3 { color: var(--primary); }
code { background-color: #f5f5f5; }
```

```yaml
extra_css:
  - stylesheets/extra.css                   # full Material theme
  - stylesheets/confluence-overrides.css    # simple Confluence-targeted styles
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
| `~subscript~` | `<sub>` (pymdownx.tilde) |
| `^superscript^` | `<sup>` (pymdownx.caret) |
| `^^inserted^^` | `<u>` (pymdownx.caret insert) |
| `` `inline code` `` | `<code>` |
| `[text](url)` | `<a href="...">` |
| `https://bare-url` | `<a href="...">` (autolink) |
| `[text](file.pdf)` | `<ac:link><ri:attachment .../>` (uploaded as attachment) |
| `![alt](src)` | `<ac:image>` with `<ri:attachment>` (local) or `<ri:url>` (remote) |
| `![alt](src){ width="400" }` | `<ac:image ac:width="400">` — also supports `height` and `align` |
| `<br>` / `<br/>` / trailing `\` | `<br />` |
| `<sub>` / `<sup>` / `<u>` / `<small>` | Direct XHTML passthrough |
| `<mark>text</mark>` | `<span style="background-color: yellow;">` |
| `<kbd>text</kbd>` | `<code>` |
| `++ctrl+alt+del++` | `<code>Ctrl</code>+<code>Alt</code>+<code>Del</code>` (pymdownx.keys) |
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
| Grid cards `<div class="grid cards" markdown>` | Native `ac:layout` multi-column sections (auto-detects 1/2/3 columns from card count) |

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
| *other fields* | Title-cased key, value stringified |

If `repo_url` + `edit_uri` are set in `mkdocs.yml`, an **Edit Source** row links to the source file. If `site_url` is set, a **Published Page** row links to the rendered MkDocs site.

### Abbreviation expansion

MkDocs abbreviation definitions (`*[ABBR]: Full term`) are expanded inline — Confluence has no native `<abbr>` tooltip. The **first occurrence** in body text is expanded as `IAM (Identity and Access Management)`; subsequent occurrences are left as-is. Abbreviations that only appear in headings or code are collected into an auto-appended **Glossary** section.

---

## Known limitations

| Feature | Behaviour |
|---|---|
| **Admonition styling** | `tip`, `info`, `warning`, `note` use Confluence's fixed native macro colours. `danger`, `error`, `bug` use a custom red `panel` macro with 🚨 prefix. All other types are mapped to the nearest native macro. |
| **Abbreviation tooltips** | No native tooltip support. First occurrence expanded inline; remainder left as-is. |
| **Page ordering** | Confluence sorts child pages alphabetically; the v2 REST API has no write endpoint for ordering. |
| **Code language aliases** | Short aliases (`py`, `js`, `yml`, `ts`, `sh`) are passed through as-is; Confluence requires full language names for syntax highlighting. |
| **Unrecognised blocks** | Preserved as a visible `warning` macro — no content is silently lost. |

---

## Architecture

![Architecture](https://raw.githubusercontent.com/jeckyl2010/mkdocs2confluence/main/docs/architecture.png)

Each stage is a separate Python module under `src/mkdocs_to_confluence/`. The **plan** phase makes all API read calls (find existing pages); the **execute** phase makes all write calls, ensuring parent pages always exist before their children.

---

## Development

See [Setup.md](Setup.md) for environment setup.

```bash
uv run pytest -q                        # run tests
uv run ruff check src tests             # lint
uv run vulture src --min-confidence 80  # dead code check
uv run mypy src                         # type-check
uv run bandit -r src -ll                # security scan
```
