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

A Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML and publishes it to Confluence.

It is a **compiler/transpiler**, not an HTML converter — every Markdown construct is mapped to the equivalent native Confluence macro or element, so pages look and behave like hand-authored Confluence content.

> **Zensical compatible** — [Zensical](https://zensical.org/) is the modern successor to MkDocs + Material for MkDocs, built by the same team. Since Zensical uses the same `mkdocs.yml` format and Python Markdown extensions, your Zensical project works with this tool today — no changes required.

---

## Architecture

![Architecture](https://raw.githubusercontent.com/jeckyl2010/mkdocs2confluence/main/docs/architecture.png)

Each stage is a separate Python module under `src/mkdocs_to_confluence/`. The **plan** phase makes all API read calls (find existing pages); the **execute** phase makes all write calls, ensuring parents always exist before children.

---

## Installation

Requires Python 3.12+.

**From PyPI:**

```bash
pip install mkdocs2confluence
```

Or with `pipx` for an isolated install:

```bash
pipx install mkdocs2confluence
```

**From source** (see [Setup.md](Setup.md)):

```bash
git clone https://github.com/jeckyl2010/mkdocs2confluence.git
cd mkdocs2confluence
pip install -e ".[dev]"
```

> **Package name vs. command name** — This follows the same convention used by many popular CLI tools (e.g. `pip install httpie` → `http` command). The PyPI package is `mkdocs2confluence` (descriptive, easy to find), and the CLI command is `mk2conf` (short, fast to type). Install once, run everywhere as `mk2conf`.

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

Compile a single page and inspect the output — no Confluence API calls required. Mermaid diagrams are rendered via Kroki unless `mermaid_render: none` is set.

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
mk2conf publish [--config PATH] [--page PATH] [--section PATH] [--dry-run] [--report FILE] [--prune]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to your `mkdocs.yml` |
| `--page PATH` | *(all nav pages)* | Publish a single page only |
| `--section PATH` | *(whole nav)* | Publish only a nav subtree (e.g. `Guide` or `Guide/Setup`) |
| `--dry-run` | off | Print the publish plan without making any Confluence API calls (Mermaid diagrams are still rendered via Kroki unless `mermaid_render: none` is set) |
| `--report FILE` | *(none)* | Write a JSON publish report to `FILE` |
| `--prune` | off | Delete managed Confluence pages no longer in `nav:` (see [Orphan pruning](#orphan-pruning)) |

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
- **Smart update detection** — before calling the Confluence update API, mk2conf compares a `sha256` hash of the compiled output against the hash stored from the previous run (kept as a hidden Confluence page property `mk2conf-content-hash`). Pages whose content has not changed are skipped entirely — no version bump, no watcher notification. As a side effect, Confluence's built-in version history becomes a meaningful audit trail: every version represents a real content change, each stamped *"Updated by mk2conf"* so automated publishes are clearly distinguishable from manual edits. You can diff any two versions directly inside Confluence, with inline highlighting showing exactly which paragraphs, headings, or code blocks changed.
- **Orphan pruning** — every page created by mk2conf is stamped with a hidden `mk2conf-managed` property. Pass `--prune` to automatically delete managed pages that have been removed from `nav:`. Manually-created Confluence pages are never deleted.

#### Orphan pruning

```bash
mk2conf publish --prune
```

After each publish run, `--prune` fetches all descendants of the configured `parent_page_id`, diffs them against the pages just published, and deletes any managed orphans — i.e. pages that carry the `mk2conf-managed` stamp but are no longer in the MkDocs nav.

> **Safety:** Only pages stamped by mk2conf are eligible for deletion. Any page created directly in Confluence will never be touched, even if it sits inside the managed hierarchy.
>
> **Partial runs:** `--prune` is silently ignored when `--page` or `--section` is used, because a partial publish would only cover a subset of the nav and would incorrectly identify out-of-scope pages as orphans.

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
| `![alt](src){ width="400" }` | `<ac:image ac:width="400">` — also supports `height` and `align` |
| `<br>` / `<br/>` | `<br />` |
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

- [x] **Delete orphaned pages** — `--prune` detects and removes managed Confluence pages that have been removed from `nav:`. Manually-created pages are never deleted.

---

## Development

See [Setup.md](Setup.md) for environment setup.

```bash
pytest              # run tests
ruff check src tests  # lint
mypy src            # type-check
bandit -r src -ll   # security scan
```
