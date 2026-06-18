# Confluence Feedback Loop

## Status: core workflow shipped as `mk2conf sync-comments`

The original plan below the fold is superseded. The feature was implemented in
`07d4b60` (+ follow-ups `9898465`, `3ba6f4a`) with a different — and better —
design than originally sketched. Verified against the code 2026-06-12:

| Piece | Where | State |
|---|---|---|
| Fetch open inline + footer comments (paginated) | `publisher/client.py` (`get_page_inline_comments`, `get_page_footer_comments`) | done, tested |
| Comment parsing (anchor text, author, webui link) | `sync/comments.py` | done, tested |
| Source-line anchoring of inline comments | `sync/anchoring.py` (`find_anchor_line`) | done, tested |
| Branch + PR + review-thread creation | `sync/github.py` (REST + GraphQL `addPullRequestReviewThread`) | done, tested |
| Resolve-on-merge with reply + commit SHA | `sync/command.py` (`check_and_resolve_merges`) | done, tested |
| State tracking | `sync/state.py` → `.mk2conf-sync-state.json` | done, tested |
| Page map written at publish | `cli.py` → `.mk2conf-pages.json` | done |
| CLI: `sync-comments` with `--check-merges`, `--dry-run`, `--force`, `--quiet` | `cli.py` | done |

Test coverage on all sync modules is 99–100% (1219 tests passing).

### As-built design decisions (answers to the original open questions)

- **PRs, not issues.** One PR per page, one review thread per comment,
  line-anchored when the inline selection text is found in the source file,
  file-level thread otherwise. Resolves the per-comment vs per-page dilemma.
- **Resolve on merge, not on capture.** Confluence comments stay open until the
  PR merges; the resolution reply includes PR number + merge commit SHA.
- **Decoupled from publish.** `sync-comments` is a standalone command; publish
  only writes the page map. No publish blocking (see remaining work).
- **Branch naming:** deterministic `mk2conf/review/<source-path-slug>`.
- **GitHub access:** direct API via `GITHUB_TOKEN` / `confluence.github_token`,
  behind a `ReviewPlatformClient` protocol (`sync/platform.py`).

## Remaining work

### 1. Pre-publish guard for uncaptured comments

The original motivation — "comments risk being silently overwritten" — is not
yet enforced. `mk2conf publish` happily republishes a page with open comments;
if the anchored text changed, the inline comment is orphaned before
`sync-comments` ever saw it.

- In `plan_publish` (or just before execute), for each page that will be
  *updated* (not skipped by hash), fetch open comments.
- If a page has open comments **not already tracked in
  `.mk2conf-sync-state.json`**, warn and block that page (or the whole run —
  prefer whole run, partial publishes are confusing). `--force` bypasses.
- Opt-in via `--check-comments` initially; flip to default once trusted.
- Cost note: one extra API call per to-be-updated page; pages skipped by the
  content hash should also be skipped here.

### 2. Body-edit drift detection (separate concern)

Someone editing the page body directly in Confluence is a different drift than
comments. Git remains the source of truth, so handling is simpler: detect and
warn, then overwrite.

- On publish, store the resulting Confluence version number as a content
  property (`mk2conf-last-version`) — the pattern already exists
  (`mk2conf-content-hash`, `mk2conf-managed` in `publisher/client.py`).
- On next publish, if current version > stored version, the page was edited
  manually → print a warning with the page link (the lost edits are still in
  Confluence page history, mention that).

### 3. Known gaps in the shipped implementation (small fixes)

- **`--force` crashes on existing branch.** `_branch_name()` is deterministic
  per source path; re-syncing a page that already has an open PR hits
  `create_review_branch` → HTTP 422 "Reference already exists". Either reuse
  the existing branch/PR or suffix the branch name.
- **New comments on a page with an open PR are never synced.**
  `has_open_pr_for` skips the page; `--force` (after the fix above) would
  re-post *all* open comments, duplicating the ones already in the PR. Fix:
  track synced comment IDs in the PR record (already stored) and post only
  unseen ones onto the *existing* PR.
- **Commenter shows as Atlassian account ID.** `_parse_comment` uses raw
  `version.authorId`; GitHub threads render `💬 **712020:abc...**`. Resolve
  display names via `GET /wiki/rest/api/user?accountId=` (cache per run).
- **PRs closed without merging are tracked forever.** `get_pr_merge_info`
  only detects merge; a closed-unmerged PR keeps its page blocked from
  re-sync. Detect `state == closed && !merged` in `--check-merges` and mark
  the record abandoned (leave Confluence comments open).
- **No automation example.** Add a GitHub Actions workflow to the docs:
  cron or post-publish job running `sync-comments` and
  `sync-comments --check-merges`.

### Suggested order

1 (guard) and 2 (version drift) deliver the missing safety net and are
independent. The items under 3 are polish; "new comments on existing PR" and
the `--force` crash are the same code path and should be fixed together.
