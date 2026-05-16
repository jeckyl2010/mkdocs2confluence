# Command Reference

## `mk2conf preview`

Compile and inspect output locally — no Confluence API calls. Mermaid diagrams are rendered via Kroki unless `mermaid_render: none` is set.

```
mk2conf preview [--config PATH] --page PATH [--out FILE] [--html] [--watch]
mk2conf preview [--config PATH] --section SECTION [--out FILE] [--watch]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to `mkdocs.yml` |
| `--page PATH` | *(required unless --section)* | Relative path to the Markdown file |
| `--section SECTION` | *(none)* | Nav section title (slash-separated for nested, e.g. `Guide` or `Guide/Setup`). Renders all pages as a browseable HTML index. |
| `--out FILE` | stdout | Write output to a file or directory |
| `--html` | off | Render macros as styled browser-viewable HTML |
| `--watch` | off | Serve on `http://localhost:8765` and auto-rebuild on file changes. Implies `--html`. `Ctrl+C` to stop. |

`--html` is for local review only — the actual Confluence storage XHTML is the `--html`-free output.

---

## `mk2conf publish`

Compile all pages in `nav:` and publish to Confluence Cloud.

```
mk2conf publish [--config PATH] [--page PATH] [--section SECTION] [--dry-run] [--report FILE] [--prune] [--quiet]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to `mkdocs.yml` |
| `--page PATH` | *(all nav pages)* | Publish a single page only |
| `--section SECTION` | *(whole nav)* | Publish only a nav subtree (slash-separated, e.g. `Guide` or `Guide/Setup`) |
| `--dry-run` | off | Print the publish plan; no Confluence API writes |
| `--report FILE` | *(none)* | Write a JSON publish report |
| `--prune` | off | Delete managed pages no longer in `nav:`. Only pages stamped by mk2conf are eligible — manually-created pages are never touched. Ignored on partial runs. |
| `--quiet` | off | Suppress per-item progress output |

### Publish behaviour

- **Only `nav:` pages are published** — pages absent from the nav are never touched (natural draft gate).
- Pages with `ready: false` in front matter are skipped even if listed in `nav:`.
- Section nodes (nav groups without a page) become empty parent pages, mirroring the nav hierarchy.
- Local assets are uploaded as Confluence page attachments automatically.
- **Unchanged pages are skipped** — a `sha256` hash of the compiled output is stored as a hidden page property; identical content produces no version bump and no notification.

### Mermaid rendering

| `mermaid_render` | Behaviour |
|---|---|
| `kroki` *(default)* | Render via `https://kroki.io`. PNGs cached in `~/.cache/mk2conf/mermaid/`. |
| `kroki:https://your-kroki` | Render via a self-hosted Kroki instance. |
| `none` | Fall back to a `code` macro labelled `mermaid`. |

If Kroki is unreachable the run continues, falling back to the `code` macro for affected diagrams.

**Automatic mermaid.ink fallback:** when using the public `kroki.io` service and a diagram receives a 504 timeout, mk2conf retries via [mermaid.ink](https://mermaid.ink) transparently. Self-hosted Kroki instances never contact mermaid.ink.

### Styling from extra.css

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

## `mk2conf pdf`

Export a nav section or single page to a stand-alone, printer-ready PDF. Requires `pip install "mkdocs2confluence[pdf]"`.

```
mk2conf pdf [--config PATH] (--section SECTION | --page PATH) [--out FILE] [--author TEXT] [--doc-version TEXT] [--quiet]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to `mkdocs.yml` |
| `--section SECTION` | *(required unless --page)* | Export a nav subtree by section title |
| `--page PATH` | *(required unless --section)* | Export a single page |
| `--out FILE` | `<section-or-page>.pdf` | Output PDF path |
| `--author TEXT` | *(none)* | Author name on the cover page |
| `--doc-version TEXT` | *(none)* | Document version on the cover page |
| `--quiet` | off | Suppress progress output |

The PDF includes a **cover page**, **table of contents** with page numbers, and one chapter per nav page with automatic page breaks. Code blocks avoid mid-block splits; Mermaid diagrams appear as embedded PNGs.

WeasyPrint requires system libraries:

| Platform | Command |
|---|---|
| macOS | `brew install pango` |
| Ubuntu / Debian | `apt install libpango-1.0-0 libpangoft2-1.0-0` |
| Windows 11 | `choco install gtk-runtime` |

---

## `mk2conf sync-comments`

Bridge Confluence page/inline comments to GitHub pull request review threads. Non-technical reviewers comment in Confluence; developers address feedback on a GitHub feature branch; comments are auto-resolved when the PR is merged.

```
mk2conf sync-comments [--config PATH] [--check-merges] [--force] [--dry-run] [--quiet]
```

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `./mkdocs.yml` | Path to `mkdocs.yml` |
| `--check-merges` | off | Check tracked PRs for merges and auto-resolve Confluence comments |
| `--force` | off | Re-sync pages that already have an open review PR |
| `--dry-run` | off | Print what would be synced without making any API calls |
| `--quiet` | off | Suppress progress output |

**Required config** (add to the `confluence:` block in `mkdocs.yml`):

```yaml
confluence:
  # ... base fields ...
  github_repo: owner/repo            # required for sync-comments
  github_token: !ENV GITHUB_TOKEN    # falls back to GITHUB_TOKEN env var
  github_base_branch: main           # default: main
```

### Workflow

1. Run `mk2conf publish` — writes `.mk2conf-pages.json` mapping source files to Confluence page IDs. Partial `--page` / `--section` runs merge into the same file.
2. Run `mk2conf sync-comments` — for each page with open Confluence comments, creates a `mk2conf/review/{slug}` branch and PR, then posts each comment as a GitHub review thread. Inline comments are anchored to the matching source line; page-level comments fall back to file-level threads. Every thread includes a **View in Confluence** deep-link.
3. Developer addresses feedback on the branch and merges the PR.
4. Run `mk2conf sync-comments --check-merges` — detects merged PRs, adds a resolution reply with commit info, and marks comments as resolved in Confluence.

**State files** (add to `.gitignore`):

| File | Purpose |
|---|---|
| `.mk2conf-pages.json` | Source path → Confluence page ID map |
| `.mk2conf-sync-state.json` | Tracks open/merged review PRs and associated comment IDs |
