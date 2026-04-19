# mk2conf — MkDocs to Confluence

A Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML and publishes it to Confluence.

It is a **compiler/transpiler**, not an HTML converter — every Markdown construct is mapped to the equivalent native Confluence macro or element, so pages look and behave like hand-authored Confluence content.

---

## Installation

Requires Python 3.12+.

**From the latest GitHub release** (recommended):

```bash
pip install https://github.com/jeckyl2010/mkdocs2confluence/releases/download/v0.1.0/mkdocs_to_confluence-0.1.0-py3-none-any.whl
```

Or with `pipx` for an isolated install (no virtual environment needed):

```bash
pipx install https://github.com/jeckyl2010/mkdocs2confluence/releases/download/v0.1.0/mkdocs_to_confluence-0.1.0-py3-none-any.whl
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

# Write XHTML to a file
mk2conf preview --config mkdocs.yml --page guide/installation.md --out out.xml

# Open a browser-friendly HTML preview (simulates Confluence rendering)
mk2conf preview --config mkdocs.yml --page index.md --html --out /tmp/preview.html
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

### `mk2conf publish`

> **Not yet implemented.** Planned for a future milestone.

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
| `![alt](src)` | `<ac:image>` with `<ri:url>` |

### MkDocs / Material extensions

| Feature | Confluence output |
|---|---|
| `--8<--` file includes | Resolved before parsing |
| Admonitions `!!! type "title"` | `info` / `tip` / `warning` / `note` macro |
| Collapsible admonitions `??? type` | `expand` macro |
| Content tabs `=== "Label"` | `expand` macros (one per tab) |
| Mermaid diagrams | `code` macro labelled `mermaid` |

### Graceful degradation

Any block the parser does not recognise is preserved as a visible `warning` macro in the output so no content is silently lost.

---

## Local browser preview

The `--html` flag post-processes the Confluence XHTML and renders macros as styled HTML panels, so you can review a page in any browser without a Confluence instance:

- **Code macros** → dark code panel with language label
- **Info / tip / warning / note macros** → colour-coded panels (blue / green / orange / grey)
- **Expand macros** → collapsible `<details>` elements
- **Unknown macros** → labelled placeholder

> **Note:** `--html` output is for local review only. The actual content sent to Confluence is always the raw XHTML (without `--html`).

---

## Project structure

```
src/mkdocs_to_confluence/
├── cli.py              # CLI entrypoint (mk2conf)
├── loader/
│   ├── config.py       # mkdocs.yml loader
│   ├── nav.py          # nav resolver
│   └── page.py         # single-page loader
├── preprocess/
│   └── includes.py     # --8<-- include/snippet preprocessor
├── ir/
│   └── nodes.py        # immutable IR node types
├── parser/
│   └── markdown.py     # Markdown → IR compiler
├── emitter/
│   └── xhtml.py        # IR → Confluence storage XHTML emitter
└── preview/
    └── render.py       # XHTML → browser HTML renderer
```

---

## Roadmap

Planned features, roughly in priority order:

- [ ] **Internal link resolution** — rewrite `.md` hrefs to Confluence page titles using the nav resolver
- [ ] **Image attachments** — collect local images and upload as Confluence attachments at publish time
- [ ] **Publish command** — Confluence REST API client to create/update pages and upload attachments
- [ ] **Material icon shortcodes** — map `:material-x:` / `:fontawesome-x:` to Confluence emoticons or Unicode, with graceful fallback
- [ ] **Mermaid native macro** — target the Confluence Mermaid marketplace macro instead of a plain code block

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
