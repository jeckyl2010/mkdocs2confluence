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
[![SLSA Level 3](https://slsa.dev/images/gh-badge-level3.svg)](https://slsa.dev)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/jeckyl2010/mkdocs2confluence/badge)](https://securityscorecards.dev/viewer/?uri=github.com/jeckyl2010/mkdocs2confluence)

A Python CLI tool that compiles MkDocs-flavoured Markdown into **native Confluence storage XHTML** and publishes it directly to Confluence Cloud. It is a **compiler/transpiler**, not an HTML converter — every construct maps to its native Confluence equivalent, so pages look and behave like hand-authored Confluence content.

It also bridges the gap between Confluence reviewers and developers: the `sync-comments` command turns open Confluence page comments into GitHub pull request review threads, and auto-resolves them in Confluence when the PR is merged.

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
cd mkdocs2confluence && uv sync
```

---

## GitHub Actions

Publish docs automatically on every push — no local install needed:

```yaml
- name: Publish docs to Confluence
  uses: jeckyl2010/mkdocs2confluence@v1
  with:
    token: ${{ secrets.CONFLUENCE_API_TOKEN }}
```

**Full workflow** — triggers on changes to `docs/` or `mkdocs.yml`:

```yaml
name: Publish docs

on:
  push:
    branches: [main]
    paths: ['docs/**', 'mkdocs.yml']

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: jeckyl2010/mkdocs2confluence@v1
        with:
          token: ${{ secrets.CONFLUENCE_API_TOKEN }}
          prune: 'true'
```

Available inputs: `token` (required), `config`, `version`, `dry-run`, `section`, `page`, `prune`, `quiet`. See [docs/commands.md](docs/commands.md) for details.

---

## Quick start

```bash
# Preview a page locally (no Confluence API calls)
mk2conf preview --page index.md --watch

# Dry-run: see what would be published
mk2conf publish --dry-run

# Publish all nav pages
mk2conf publish

# Export a section to PDF
mk2conf pdf --section Guide --out guide.pdf

# Sync Confluence comments to GitHub PR review threads
mk2conf sync-comments
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
  changelog: CHANGELOG.md           # optional: publish as a top-level "What's New" page
```

The `confluence:` block is also accepted under `extra:` for MkDocs strict-mode compatibility. The API token is read from `token:` in `mkdocs.yml`, then `CONFLUENCE_API_TOKEN`, then `MK2CONF_TOKEN`.

### Changelog / What's New page

Set `changelog:` to a Markdown file path (relative to `docs_dir`) to have mk2conf publish it as a permanent top-level page on every full `mk2conf publish` run. The page title comes from YAML front matter `title:`; it defaults to `"What's New"` if absent.

```yaml
confluence:
  changelog: CHANGELOG.md   # relative to docs_dir
```

- The page does **not** need to appear in `nav:` — it is always placed at the top level of the space (or under `parent_page_id` if set).
- If it also appears in `nav:`, it is published once; no duplication.
- `--prune` never deletes it — it is a pinned page, not a nav-derived page.
- Partial runs (`--page` / `--section`) skip the changelog page, consistent with other publish behaviour.
- Omit the key, or set it to an empty string, to disable the feature entirely.

Run `mk2conf install-skill` once after setting `changelog:` to install the changelog AI skill into your AI tool (Claude Code, Copilot, Cursor, Hermes). The skill analyses git changes to your docs since the last `CHANGELOG.md` commit and drafts an entry when the changes qualify as significant.

**Your first publish:**

```bash
export CONFLUENCE_API_TOKEN=your_api_token_here
mk2conf preview --page docs/index.md --watch   # verify output locally
mk2conf publish --dry-run                       # check the plan
mk2conf publish                                 # go live
```

---

## Documentation

| | |
|---|---|
| [docs/commands.md](docs/commands.md) | Full flag reference for all five commands |
| [docs/features.md](docs/features.md) | Supported Markdown / Material features and known limitations |
| [Setup.md](Setup.md) | Development environment setup |

---

## Architecture

![Architecture](https://raw.githubusercontent.com/jeckyl2010/mkdocs2confluence/main/docs/architecture.png)

Pipeline stages: **loader → preprocess → IR → transforms → emitter → publisher**.

The publisher is split into two phases:
- `planner.py` builds a nav-ordered publish plan, compiles pages, and makes the read-side API calls needed to decide create vs update vs skip.
- `executor.py` applies that plan, performs the write-side API calls, uploads attachments, and wires parent/child relationships in nav order so parent pages always exist before their children.

`publisher/pipeline.py` remains a compatibility facade that re-exports the public publish surface used by the CLI and tests.

---

## Development

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run vulture src --min-confidence 80
```

