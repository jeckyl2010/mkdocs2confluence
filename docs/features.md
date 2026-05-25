# Supported Features

## Block elements

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

## Inline elements

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
| `[text][label]` / `[text][]` with `[label]: url` | Resolved to inline link before parsing |
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

## MkDocs / Material extensions

| Feature | Confluence output |
|---|---|
| `--8<--` file includes | Resolved before parsing |
| Admonitions `!!! type "title"` | `info` / `tip` / `warning` / `note` macro |
| Danger admonitions (`danger`, `error`, `bug`) | Red `panel` macro with 🚨 prefix |
| Collapsible admonitions `??? type` | `expand` macro |
| Content tabs `=== "Label"` | `expand` macros (one per tab) |
| Details blocks `??? "title"` | `expand` macro |
| Footnotes `[^1]` | Superscript anchor links + *Footnotes* section at page bottom |
| In-page anchors `<a id="...">` / `<a name="...">` | Confluence `anchor` macro; same-page links `[text](#target)` resolve correctly |
| Mermaid diagrams | PNG via Kroki, uploaded as attachment (`<ac:image ac:align="center">`) |
| Internal links `[text](page.md)` | Native Confluence page link; `#fragment` anchors preserved |
| `awesome-pages` nav (`.pages` files) | Fully supported |
| Edit link banner | `info` macro linking back to source in GitHub/GitLab |
| Grid cards `<div class="grid cards" markdown>` | Native `ac:layout` multi-column sections (auto-detects 1/2/3 columns from card count) |

## YAML front matter → Page Properties

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
status: in-progress
---
```

| Field | Notes |
|---|---|
| `title` | Used as the Confluence page title on publish |
| `subtitle` | Rendered as italic lead paragraph above the properties table |
| `tags` | Also applied as Confluence page labels |
| `ready` | `true` → ✅ Ready · `false` → 📝 Draft (skips publish) |
| `status` | Sets the Confluence page status badge — common values: `rough-draft`, `in-progress`, `ready-for-review`. Space-specific values are also supported. Not shown in the properties table. |
| *other fields* | Title-cased key, value stringified |

If `site_url` is set in `mkdocs.yml`, a **Published Page** row links to the rendered MkDocs site.

## Changelog / What's New page

Set `changelog: CHANGELOG.md` (path relative to `docs_dir`) in the `confluence:` block to designate a Markdown file as a **pinned top-level page** in your Confluence space:

```yaml
confluence:
  base_url: https://yourorg.atlassian.net
  space_key: TECH
  email: user@example.com
  token: !ENV CONFLUENCE_API_TOKEN
  changelog: CHANGELOG.md
```

On every full `mk2conf publish` run the changelog file is compiled and published at the top level of the space (or as a sibling of the root nav pages when `parent_page_id` is set). The page title comes from YAML front matter `title:`; it defaults to `"What's New"` if absent.

**Behaviour at a glance:**

| Aspect | Detail |
|---|---|
| Placement | Top-level page, not nested within the nav hierarchy |
| Skip-unchanged | SHA-256 hash checked — unchanged content produces no API call and no Confluence notification |
| `--prune` | Never deleted — the page is pinned, not nav-derived |
| Partial runs | Skipped with `--page` / `--section` (consistent with existing partial-run behaviour) |
| `--dry-run` | Listed alongside other pages in the plan output |
| Disabled | Omit `changelog:` or set it to an empty string |

The changelog file is a plain Markdown file committed alongside your docs. Content is entirely up to you — mk2conf publishes whatever is there, the same way it publishes any other page.

### AI skill — drafting changelog entries

Run `mk2conf install-skill` once to install the bundled `mkdocs-changelog` skill into every detected AI tool (Claude Code, Copilot, Cursor, Hermes). Once installed, invoke it from your AI assistant while working on your docs:

1. It finds the last commit that touched `CHANGELOG.md` as the baseline.
2. It diffs all doc changes in `docs/` since that baseline.
3. It decides whether any change is **MAJOR** — a new top-level area, a significant deletion, or a fundamental definition change. Typos, formatting, and small additions do not qualify.
4. If MAJOR: drafts a dated Keep-a-Changelog entry and prepends it to `CHANGELOG.md` for you to review before committing.
5. If not MAJOR: explains why and exits without touching any file.

You always commit and publish manually — the skill never commits or calls the Confluence API.

```bash
mk2conf install-skill              # auto-detect and install to all found tools
mk2conf install-skill --tool claude
```

## Source footer

When `repo_url` + `edit_uri` are set in `mkdocs.yml`, a **Page source** footer panel is appended containing:

- **Edit this page** — links to the source file in your VCS
- **View history** — links to the file's commit history (auto-derived for GitHub and GitLab)
- **Last commit** — short SHA (linked), message, author, and relative date from `git log` at publish time

The commit SHA and message are also written to the **Confluence version history** on every publish.

## Section index child pages

When a MkDocs nav section has an `index.md`, the published Confluence page automatically includes the native **Children Display macro** below the page content — a live, auto-maintained list of all direct child pages.

## Abbreviation expansion

MkDocs abbreviation definitions (`*[ABBR]: Full term`) are rendered as inline superscript anchor links. The **first occurrence** of each abbreviation in body text gets a superscript number (`API¹`) that links to a numbered glossary appended at the bottom of the page. Uses only native Confluence storage format — no plugins required.

---

## Known limitations

| Feature | Behaviour |
|---|---|
| **Admonition styling** | `tip`, `info`, `warning`, `note` use Confluence's fixed native macro colours. `danger`, `error`, `bug` use a custom red `panel` macro with 🚨 prefix. All other types are mapped to the nearest native macro. |
| **Abbreviation tooltips** | No native tooltip support. First occurrence gets a superscript anchor link (`API¹`); definitions collected in a numbered glossary at page bottom. |
| **Page ordering** | Confluence sorts child pages alphabetically; the v2 REST API has no write endpoint for ordering. |
| **Code language aliases** | Short aliases (`py`, `js`, `yml`, `ts`, `sh`) are passed through as-is; Confluence requires full language names for syntax highlighting. |
| **Unrecognised blocks** | Preserved as a visible `warning` macro — no content is silently lost. |
