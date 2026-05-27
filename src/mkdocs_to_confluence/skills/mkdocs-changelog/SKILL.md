---
name: mkdocs-changelog
description: Analyse doc changes since the last CHANGELOG.md update and draft a major-change entry if the changes qualify.
version: "1.3.0"
tags: [documentation, git, changelog, mkdocs, confluence]
specificity: context-specific
tool_agnostic: true
authors: [Anders Hybertz]
tested_on: []
---

# MkDocs Changelog Entry

Analyse git changes to the docs directory since the last `CHANGELOG.md` commit. If any changes qualify as **MAJOR**, draft a dated changelog entry in the collapsible format and prepend it to `CHANGELOG.md`. If not, explain why and exit without modifying any file.

## When to Use

- After making one or more documentation changes and before running `mk2conf publish`
- Any point in the writing flow when you want to assess whether a "What's New" entry is warranted

## Steps

1. **Extract git data** — run the bundled data script to get structured, deterministic input:

   Normal update (since last CHANGELOG.md commit):
   ```
   python .mk2conf/scripts/changelog_data.py --docs-dir <docs_dir>
   ```

   Initial changelog (from a specific date):
   ```
   python .mk2conf/scripts/changelog_data.py --docs-dir <docs_dir> --since YYYY-MM-DD
   ```

   The script prints a JSON object to stdout. Use this as your sole source of truth for
   commits, changed files, and contributors. Do not run git commands yourself.

   If the script is missing, tell the user to run `mk2conf install-skill` first.

   When `--since` is used, the JSON will contain `"mode": "since_date"`. Use this to
   trigger the initial changelog flow described below.

2. **Read the existing changelog** — read `<docs_dir>/CHANGELOG.md` for context on what
   was previously recorded.

3. **Decide: is this MAJOR?**

   **MAJOR criteria — any one of these qualifies:**
   - A new top-level documentation area or section added (a new folder or nav section that didn't exist before)
   - A significant area deleted or substantially restructured (not just moved or renamed)
   - A fundamental definition, concept, or policy changed in a way that affects how readers understand the subject

   **NOT major — do not draft an entry for:**
   - Typo fixes, grammar corrections, spelling
   - Formatting, diagram adjustments, image swaps
   - Small additions (a paragraph, a note, a clarification) that do not change the substance
   - Rewordings that preserve the original meaning
   - Internal restructuring with no reader-facing impact

4. **If NOT MAJOR** — report what was found, explain in one sentence why it did not qualify,
   and stop. Do not modify any file.

5. **If MAJOR** — draft an entry using the collapsible format below and prepend it to
   `CHANGELOG.md`. The previous latest entry (if any) must be converted from `???+` to `???`
   so only the new entry is expanded by default.

## Entry format

The latest entry uses `???+` (expanded by default on Material, always visible on Confluence).
All older entries use `???` (collapsed, showing only the date and title as the trigger).

```markdown
???+ note "YYYY-MM-DD — Brief title describing the major change"

    ### Added
    - …

    ### Changed
    - …

    ### Deprecated
    - …

    ### Removed
    - …

    ### Fixed
    - …

    ### Security
    - …

    Contributors: Name One, Name Two
```

Rules for the entry:

- Date is the `date` field from the script output (`YYYY-MM-DD`)
- Title is a brief, reader-facing description — not a git commit message
- No version numbers — dates only
- **Include only sections that have actual content** — omit any empty section entirely
- Section meanings: `Added` (new content), `Changed` (updated content), `Deprecated`
  (content being phased out), `Removed` (deleted content), `Fixed` (corrected errors or
  misleading information), `Security` (security-related documentation updates)
- `Contributors:` line — include when the `contributors` array from the script output has
  **more than one name**. Omit when there is only one contributor.
- Content inside the admonition block must be indented with **4 spaces**
- When prepending, convert the previous `???+` opener to `???` first

## CHANGELOG.md structure

If `CHANGELOG.md` does not exist yet, create it with this header before the first entry:

```markdown
# Changelog

All notable changes to this documentation are recorded here.
The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
```

## Initial changelog (--since DATE)

When the script is run with `--since` and the JSON contains `"mode": "since_date"`,
the user wants to bootstrap a CHANGELOG.md from scratch for a given time window.

Different rules apply:

- **Always draft** — the MAJOR threshold does not apply. This is a retrospective
  summary, not an incremental gate.
- **Group by theme**, not by individual commit. Synthesise the changed files and
  commit subjects into meaningful categories.
- **Date range in the title** — use the `since` value from the JSON as the start
  and `date` as the end, e.g. `2026-05-01 → 2026-05-27`.
- **If CHANGELOG.md already exists**, stop and ask the user whether they want to
  prepend, append, or replace. Do not overwrite silently.
- **If CHANGELOG.md does not exist**, create it with the standard header and the
  entry as `???+`.

Example title: `2026-05-01 → 2026-05-27 — Initial documentation release`

## Pitfalls

- **Do not draft an entry for every change.** The changelog is for readers who want to know
  what fundamentally changed — not a git log. When in doubt, do not draft.
- **Do not commit.** Always leave the file for the user to review. The user runs `git add`
  and `git commit` themselves before publishing.
- **The script is the only source of git data.** Do not interpret commit messages or diffs
  yourself — the script output is deterministic and already scoped to the docs directory.
- **4-space indent is required** inside the admonition block. 2-space or tab indent will
  break both Material rendering and the Confluence compile step.

## Verification

After drafting, show the user the proposed entry in the terminal and remind them to review
`CHANGELOG.md` before committing and running `mk2conf publish`.
