# Design: Changelog / What's New Page

**Date:** 2026-05-25
**Status:** Approved

---

## Problem

mk2conf has no way to surface significant documentation changes to Confluence readers. Colleagues must check individual page version histories to discover what changed. There is no single "What's New" signal in the Confluence space.

---

## Architecture

Two independent pieces that compose naturally:

- **mk2conf feature** — a `changelog:` config key in `mkdocs.yml` designates a Markdown file as the changelog. mk2conf compiles and publishes it on every `publish` run as a top-level Confluence page. No changes to the compile pipeline; it is treated as a standalone managed page.
- **AI skill** — an on-demand Claude Code / Hermes / Copilot / Cursor skill that analyses git changes to the docs directory since the last `CHANGELOG.md` commit, decides whether they constitute a MAJOR change, and if so drafts a dated entry for the user to review before committing.

The two pieces are deliberately decoupled. mk2conf does not know or care how `CHANGELOG.md` got its content. The skill does not touch Confluence directly. The user may also update `CHANGELOG.md` manually at any time.

---

## Part 1 — mk2conf: changelog config and publish behaviour

### Configuration

New optional key inside the `confluence:` block in `mkdocs.yml`:

```yaml
confluence:
  base_url: https://yourorg.atlassian.net
  space_key: TECH
  email: user@example.com
  token: !ENV CONFLUENCE_API_TOKEN
  changelog: CHANGELOG.md        # path relative to docs_dir
```

- Path is resolved relative to `docs_dir` (consistent with all other doc paths in mk2conf).
- mk2conf applies the same boundary check used for nav and asset paths — any path that escapes `docs_dir` is rejected at config load time with a clear error.
- If the key is absent, `null`, or an empty string, the changelog page is silently skipped with no error.

### Publish behaviour

- The changelog page is compiled and published on every full `mk2conf publish` run. It does not need to appear in `nav:`. If it also appears in `nav:`, it is published once (deduplicated by file path).
- It is placed as a top-level page directly under the Confluence space root, or as a sibling peer to the top-level nav sections when `parent_page_id` is set — not nested within the nav hierarchy.
- Page title is taken from front matter `title:`; defaults to `"What's New"` if absent.
- SHA-based skip applies identically to all other pages — if the file is unchanged since the last publish, no Confluence API call is made.
- `--prune` never touches it — it is a pinned managed page, not a nav-derived page.
- Partial runs (`--page` / `--section`) skip the changelog page (consistent with existing partial-run behaviour).
- `--dry-run` lists it alongside other pages in the plan output.

---

## Part 2 — AI skill: changelog entry generation

### Trigger

User-invoked at any point in the writing flow, after making one or more documentation changes.

### What the skill does

1. Runs `git log --follow -- <docs_dir>/CHANGELOG.md` to find the last commit that touched `CHANGELOG.md`. This is the baseline.
2. Runs `git diff <baseline>..HEAD -- <docs_dir>/` to collect all doc changes since that baseline.
3. Reads the existing `CHANGELOG.md` for context on what was previously recorded.
4. Uses the AI's own reasoning to decide: are any of these changes **MAJOR**?

**MAJOR criteria (explicit in the skill prompt):**
- A new top-level documentation area or section added.
- A significant area deleted or substantially restructured.
- A fundamental definition, concept, or policy changed in a way that affects how readers understand the subject.

**Not MAJOR:**
- Typo fixes, grammar corrections, spelling.
- Formatting, diagram adjustments, image swaps.
- Small additions (a paragraph, a note, a clarification) that do not change the substance.
- Rewordings that preserve the original meaning.

5. **If not MAJOR**: reports what was found and explains why it did not qualify. Exits without modifying any file.
6. **If MAJOR**: drafts a dated changelog entry in Keep-a-Changelog style and prepends it to `CHANGELOG.md`. Does not commit — the user reviews, edits if needed, and commits manually before running `mk2conf publish`.

### Entry format

```markdown
## 2026-05-25 — Brief title describing the major change

One or two sentences summarising what fundamentally changed and why it matters to readers.

### Added
- …

### Changed
- …

### Removed
- …
```

Dates only — no version numbers. Sections (`Added`, `Changed`, `Removed`) are included only when non-empty.

---

## Part 3 — Skill distribution: `mk2conf install-skill`

### Overview

The skill template is bundled as package data inside the `mkdocs2confluence` pip package, following the skills repo schema (`name`, `description ≤150 chars`, `version`, `tags`, `tool_agnostic: true` frontmatter).

A new CLI command installs the skill into **all detected AI tools** in the current environment:

```bash
mk2conf install-skill            # auto-detect and install everywhere
mk2conf install-skill --tool claude
mk2conf install-skill --tool hermes
mk2conf install-skill --tool copilot
mk2conf install-skill --tool cursor
```

### Detection and install targets

| Detected marker | Installs to | Level |
|---|---|---|
| `~/.hermes/` | `~/.hermes/skills/tooling/mkdocs-changelog/SKILL.md` | user |
| `.github/skills/` | `.github/skills/tooling/mkdocs-changelog/SKILL.md` | project |
| `.claude/` | `.claude/commands/changelog.md` (YAML frontmatter stripped) | project |
| `.github/copilot-instructions.md` | `.github/instructions/mk2conf-changelog.instructions.md` | project |
| `.cursor/` | `.cursor/rules/mk2conf-changelog.mdc` | project |
| None found | `.mk2conf/changelog-skill.md` + printed guidance | project |

- All detected targets are installed, not just the first match.
- Hermes is user-level (`~/.hermes/`) — installed regardless of which project `install-skill` runs from.
- All other targets are written into the current project directory.
- The skill content is identical across all targets; only the wrapper format and location differ.
- Claude Code commands are plain Markdown — YAML frontmatter is stripped on install.
- The skill content is also documented in `README.md` for users to adapt to tools not explicitly supported.

### Bundled skill metadata (skills repo schema)

```yaml
name: mkdocs-changelog
description: Analyse doc changes since the last CHANGELOG.md update and draft a major-change entry if the changes qualify.
version: "1.0.0"
tags: [documentation, git, changelog, mkdocs, confluence]
specificity: context-specific
tool_agnostic: true
authors: [Anders Hybertz]
tested_on: []
```

---

## Out of scope

- Automatic publish on file save (deliberate: user controls when to publish).
- Version numbers in changelog entries (dates only).
- Two-way Confluence → Markdown sync.
- AI deciding to commit or push — user always reviews before committing.
