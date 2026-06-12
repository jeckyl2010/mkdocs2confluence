# Confluence Feedback Loop — Backlog Feature

## Problem

Confluence is treated as a read-only viewer — the source of truth lives in Git.
However, managers and stakeholders who cannot use Git will naturally leave feedback
(inline comments, footer comments) directly on Confluence pages. Currently those
comments are invisible to the doc authors and risk being silently overwritten on
the next publish.

## Proposed Workflow

1. **Pre-publish scan** — before deploying a set of pages, check each page for
   open inline and footer comments via the Confluence API.

2. **If comments found:**
   - Create a feature branch (e.g. `feedback/YYYY-MM-DD-<space-key>`) in the repo.
   - Open one GitHub Issue per comment (or one per page — TBD) containing:
     - Page title + link
     - Anchor text (the highlighted text the inline comment is attached to)
     - Comment body
     - Commenter display name (Confluence identity, no GitHub mapping needed)
     - Date of comment
   - Post a reply on the Confluence comment: *"Captured as GitHub issue #N — resolving."*
   - Resolve the comment in Confluence (we already have `resolve_inline_comment` and
     `resolve_footer_comment` in the client).
   - **Block the publish** for any page that had open comments. The human must work
     the issues on the branch, merge, and re-run.

3. **Override** — `--force` flag to publish anyway (e.g. urgent hotfix), with a
   clear warning printed.

## Open Design Questions

- **Branch naming:** date + space key, or something from deploy context
  (git describe, a tag)? Should be human-readable and sortable.

- **Issue granularity:** one issue per comment (granular, noisy) vs one issue per
  page (tidy, loses individual anchor context). Leaning toward one-per-comment
  with the page as a label/grouping.

- **Git/GitHub access assumption:** requires `gh` CLI or GitHub API token available
  in the environment where `mk2conf publish` runs. Not always true in CI — needs
  a fallback (e.g. print a report and block, without creating the branch/issues).

- **Block scope:** block only pages with comments, or block the entire publish if
  any page has comments? Blocking per-page could leave a partial publish in an
  inconsistent state.

- **Body edits (separate from comments):** if someone has manually edited the page
  body in Confluence (not just commented), that is a different kind of drift. Simpler
  handling — warn and overwrite, since Git is the source of truth. Track via a stored
  Confluence version number property (`mk2conf-last-version`) compared against current.

## Existing Building Blocks

- `client.get_page_inline_comments(page_id)` — already implemented
- `client.get_page_footer_comments(page_id)` — already implemented
- `client.resolve_inline_comment(comment_id)` — already implemented
- `client.resolve_footer_comment(comment_id)` — already implemented (check)
- `client.add_comment_reply(comment_id, text)` — already implemented
- Content hash skip logic in planner — pages already checked before publish

## Implementation Sketch (when ready)

1. New `drift.py` module in `publisher/` — pure functions, no side effects at
   the edges (`check_page_drift(client, page_id) -> DriftResult`).
2. `DriftResult` dataclass: `page_id`, `title`, `inline_comments`, `footer_comments`.
3. Called from `plan_publish` after the existing hash-skip check.
4. New `feedback.py` module — GitHub Issue creation + branch creation via `gh` CLI.
5. `--check-drift` flag on `mk2conf publish` to opt in (default off until stable).
6. `--force` to bypass the block.
7. `PublishReport` gains a `drift_warnings` field.
