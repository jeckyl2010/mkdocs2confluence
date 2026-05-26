# MkDocs Changelog Entry

Analyse git changes to the docs directory since the last `CHANGELOG.md` commit. If any changes qualify as **MAJOR**, draft a dated changelog entry and prepend it to `CHANGELOG.md`. If not, explain why and exit without modifying any file.

## When to Use

- After making one or more documentation changes and before running `mk2conf publish`
- Any point in the writing flow when you want to assess whether a "What's New" entry is warranted

## Steps

1. **Find the baseline** — run `git log --follow -1 --format="%H" -- <docs_dir>/CHANGELOG.md` to get the last commit that touched `CHANGELOG.md`. If no commit is found, use the root commit as the baseline.

2. **Collect doc changes** — run `git diff <baseline>..HEAD -- <docs_dir>/` to see everything that changed in the docs directory since that baseline.

3. **Read the existing changelog** — read `<docs_dir>/CHANGELOG.md` for context on what was previously recorded.

4. **Decide: is this MAJOR?**

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

5. **If NOT MAJOR** — report what was found, explain in one sentence why it did not qualify, and stop. Do not modify any file.

6. **If MAJOR** — draft an entry using this format and prepend it to `CHANGELOG.md`:

```markdown
## YYYY-MM-DD — Brief title describing the major change

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
```

   Rules for the entry:
   - Date is today's date in `YYYY-MM-DD` format
   - Title is a brief, reader-facing description (not a git commit message)
   - No version numbers — dates only
   - **Include only sections that have actual content** — omit any empty section entirely
   - Section meanings: `Added` (new content), `Changed` (updated content), `Deprecated` (content being phased out), `Removed` (deleted content), `Fixed` (corrected errors or misleading information), `Security` (security-related documentation updates)

   Prepend the entry above any existing entries in `CHANGELOG.md`. Do not commit — the user reviews, edits if needed, and commits manually.

## Pitfalls

- **Do not draft an entry for every change.** The changelog is for readers who want to know what fundamentally changed, not a git log. When in doubt, do not draft.
- **Do not commit.** Always leave the file for the user to review. The user runs `git add` and `git commit` themselves before publishing.
- **If `CHANGELOG.md` does not exist yet**, create it with this header before the first entry:

```markdown
# Changelog

All notable changes to this documentation are recorded here.
The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
```

## Verification

After drafting, show the user the proposed entry in the terminal and remind them to review `CHANGELOG.md` before committing and running `mk2conf publish`.
