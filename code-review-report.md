# Code Review Report

> Current-state note (2026-05-29)
>
> This file is a running review log. The **primary report immediately below**
> reflects the current state of the project at v0.13.12. Older dated sections
> are point-in-time artifacts kept for history — do not read them as a
> statement of the current design.

---

## Primary Report — Current State (v0.13.12)

**Scope**: v0.12.1 → v0.13.12 — changelog/"What's New" page + AI skill installer + link-map refactor
**Language**: Python 3.12+ (running on 3.14 venv)
**Review Date**: 2026-05-29
**Overall Decision**: **APPROVED** *(findings #1 and #2 remediated same day)*
**Quality Score**: ~~90~~ → **98/100** *(post-remediation)*

---

### Summary

Since the last review (sync-comments, 2026-05-06) the project gained two feature areas:

1. **Standalone changelog page** — `publisher/changelog.py` compiles a designated
   `docs/` markdown file into a dedicated "What's New" Confluence page, published
   alongside the normal nav tree. Driven by a new `confluence.changelog` config key.
2. **AI skill installer** — `skill_installer.py` + bundled `skills/mkdocs-changelog/`
   distributes a `/mk2conf-changelog` skill into detected AI tool directories
   (Hermes, Claude, Copilot, Cursor, `.github/skills`), with a fallback path.

Supporting refactor: `build_link_map` is now built once in `plan_publish` and
threaded into both page compilation and the changelog compiler, so changelog
prose can link to changed pages naturally. `find_section_by_folder` was added to
`loader/nav.py` to resolve a folder reference to a synthetic section node.

- Modules reviewed: 56 source files (was 45 at sync-comments review)
- New modules: `publisher/changelog.py`, `skill_installer.py`, `skills/mkdocs-changelog/scripts/changelog_data.py`
- KEEP: all; DISCARD: 0; ESCALATE: 0
- **All 3 carry-over debt items from the 2026-05-06 review are resolved** (see below)

---

### Technical Validation

| Check | Result |
|---|---|
| `uv run mypy src` | **Success: no issues in 56 source files** ✅ |
| `uv run pytest -q` | **1139 passed** in ~10s ✅ *(was 1132; +7 changelog tests added during remediation)* |
| `uv run ruff check src tests` | **All checks passed** ✅ |
| `uv run vulture src --min-confidence 80` | **Clean** ✅ |
| `uv run bandit -r src` | 12 Low, 0 Medium*/High — all expected (5× B110 try/except/pass, subprocess/`random` in bundled data script). *Was 16 Low / 9× B110 before remediation — four swallow blocks now warn.* |

\* one Medium-*confidence* Low-severity finding; no Medium/High *severity* issues.

**Overall coverage: 92%** (4203 stmts, 345 missed). *(was 91% / 366 missed)*

| New / touched module | Coverage | Notes |
|---|---|---|
| `publisher/changelog.py` | **100%** | Was 72% — closed during remediation (finding #1) |
| `skill_installer.py` | 93% | `github-skills` branch (79–82) untested |
| `transforms/internallinks.py` (`build_link_map`) | 98% | |
| `loader/nav.py` (`find_section_by_folder`) | 95% | |
| `publisher/planner.py` | 90% | |
| `publisher/executor.py` | 97% | |
| `publisher/pipeline.py` (facade) | 100% | |

---

### Detailed Review — KEEP Items

| File | Item | Rationale |
|---|---|---|
| `loader/config.py` | `changelog` parsing (264–277) | **Correct path-escape guard**: resolves the candidate and `relative_to(docs_dir)`, raising `ConfigError` on traversal. This is the right defensive pattern for a user-supplied path. |
| `publisher/changelog.py` | `publish_changelog` | Clean reuse of `compile_page`, `_xhtml_hash`, `_upload_assets`. Skips re-publish when content hash matches. Deliberately **does not stamp the page as managed** (93–94) so `--prune` never deletes it — a well-documented, correct design choice. |
| `publisher/changelog.py` | `_extract_title` | Minimal, defensive YAML front-matter title extraction with `OSError`/`YAMLError`/non-dict guards; falls back to "What's New". |
| `skill_installer.py` | `install_skill` | Readable per-tool detection. `explicit` (named tool) vs auto-detect (marker-exists) distinction is clear. Always writes the data script to a fixed `.mk2conf/scripts/` path so every tool's skill references it unconditionally. Fallback path when no markers found. |
| `transforms/internallinks.py` | `build_link_map` | Built once in `plan_publish` and passed to callers (commit `aa83995`) — removes redundant per-page reconstruction. |
| `loader/nav.py` | `find_section_by_folder` | Case-insensitive `folder/` prefix match over `flat_pages`; prefers an explicit nav `title:` when one matches, else humanises the folder name — consistent with how the loader titles bare directories elsewhere. |

---

### Carry-Over Debt — Status

All three Low-severity items from the 2026-05-06 review are **fixed**:

| Original item | Status |
|---|---|
| Bare `assert config.confluence is not None` (`sync/command.py:60`) | ✅ Now `raise RuntimeError(...)` at line 61 |
| `page_title` field stored PR title (`sync/state.py:16`) | ✅ Renamed to `pr_title` (line 15) |
| Redundant in-loop `url = self._v2(...)` in pagination (`client.py:557,575`) | ✅ Removed — `url` is now set once before the `while` loop |

---

### Findings

**1. `publisher/changelog.py` coverage — RESOLVED (was 72%, now 100%)**
Added 7 tests to `tests/test_changelog_publish.py`: an update-path test that drives
labels + `full_width` + Confluence status with `quiet=False` (covers the metadata
calls and progress prints), a swallow-and-continue test that makes every post-publish
metadata call raise to prove failures don't propagate, non-quiet created/unchanged
print tests, and three `_extract_title` guard tests (unreadable file, malformed YAML,
non-mapping front matter). Suite now **1139 passed**, overall coverage **92%**.

**2. Swallow-and-continue blocks (`except Exception: pass`) — RESOLVED**
Originally `changelog.py` had four silent swallows plus four in `executor.py` (the
9× B110 bandit signal), which hid unexpected errors behind best-effort metadata
writes. Remediated to a warn-and-continue policy: `content_hash` stays silent (its
failure self-heals — the next run re-publishes), while `labels` / `full_width` /
`status` now print `  [warn] …: {exc}` to stderr and continue. `executor.py`'s
previously-silent `labels` block was upgraded to match, so both modules are now
consistent. The catch is intentionally kept broad so a transient network error
cannot abort an already-saved page. B110 count dropped 9 → 5.

**3. `skill_installer.py` `github-skills` branch untested (Negligible)**
Lines 79–82 (the `.github/skills` install target) are not covered. Behaviourally
identical to the other branches; low risk. Add one parametrised case if convenient.

---

### Quality Score Breakdown

| Category | Score (initial → post-remediation) | Notes |
|---|---|---|
| Compilation / type check | 20/20 | mypy clean, 56 files |
| Test discovery | 20/20 | 1139 pass, no errors |
| Minimality | 19/20 | All new code maps to the two features; no speculative abstractions |
| Coding principles | 27 → **30**/30 | Finding #2 resolved — swallow blocks now warn-and-continue |
| Test quality | 8 → **9**/10 | Finding #1 resolved (`changelog.py` 100%); −1 remains for untested `github-skills` branch |
| **Final Score** | ~~90~~ → **98/100** | |

---

### Technical Debt

| File | Line | Type | Description |
|---|---|---|---|
| ~~`publisher/changelog.py`~~ | ~~73–132~~ | ~~`AIDEV-TEST`~~ | ~~Add an update-path test with labels + `full_width` + status.~~ **Resolved** — module at 100%, 7 tests added. |
| ~~`publisher/changelog.py`~~ | ~~113,117,124,129~~ | ~~`AIDEV-REFACTOR`~~ | ~~Narrow `except Exception: pass` / log.~~ **Resolved** — labels/full_width/status now warn-and-continue (`[warn] …: {exc}` to stderr), content_hash stays silent (self-healing). `executor.py` labels block upgraded to warn for consistency. Catch kept broad so a transient network error can't abort an already-saved page. |
| `skill_installer.py` | 79–82 | `AIDEV-TEST` | Cover the `github-skills` install target. |

---

### Recommendations

1. ~~**Close the changelog coverage gap**~~ → **Done** — `changelog.py` at 100% (+7 tests).
2. ~~**Tighten the swallow blocks**~~ → **Done** — warn-and-continue policy applied to `changelog.py` and `executor.py`.
3. **Remaining (negligible)**: cover the `skill_installer.py` `github-skills` branch (lines 79–82) when convenient.
4. No blocking issues. Branch is clean (one untracked `confluence_rovo_mockup.png` asset, not part of the package).

---

## Archived Reports

*(point-in-time artifacts below — see the current-state note at the top)*

---

# Code Review Report (archived — sync-comments, 2026-05-06)

**Scope**: v0.8.0–v0.8.3 — `sync-comments` feature (Confluence→GitHub PR bridge)
**Language**: Python 3.12+
**Review Date**: 2026-05-06
**Overall Decision**: **APPROVED** *(with technical debt noted)*
**Quality Score**: 86/100

---

## Summary
- Total Items Reviewed: 7 modules + 5 test files
- KEEP: all functional items
- DISCARD: 0
- ESCALATE: 0
- Technical debt items: 4

---

## Technical Validation

### Compilation / Type Check
- `uv run mypy src` → **Success: no issues found in 45 source files** ✅

### Test Discovery & Execution
- `uv run pytest -q` → **1041 passed** ✅
- `uv run ruff check src tests` → **All checks passed** ✅
- `uv run vulture src --min-confidence 80` → **Clean** ✅

### Coverage
- `sync/` package: 100% (anchoring, command, comments, github, state), platform excluded (`# pragma: no cover`)
- Overall project: 90%

---

## Detailed Review

### KEEP Items

| File | Item | Requirement | Rationale |
|---|---|---|---|
| `sync/anchoring.py` | `find_anchor_line` | Line-anchoring for inline comments | Clean, minimal, correct. Exact substring match on raw source lines is appropriate — Confluence's `inlineOriginalSelection` is verbatim source text. |
| `sync/comments.py` | `ConfluenceComment`, `fetch_open_comments`, `format_github_comment` | Fetch + format Confluence comments | Well-separated responsibilities. `_strip_tags` is minimal. `format_github_comment` produces a readable review body with deep-link. |
| `sync/state.py` | `PRRecord`, `SyncState` | Persisted state for PR tracking | Clean dataclass + JSON round-trip. `has_open_pr_for` is the right guard against duplicate PRs. |
| `sync/platform.py` | `ReviewPlatformClient` Protocol | Abstraction for platform adapters | Correct use of `typing.Protocol`. `# pragma: no cover` on stub bodies is appropriate. |
| `sync/github.py` | `GitHubReviewClient` | GitHub REST + GraphQL bridge | Correct use of `addPullRequestReviewThread` with `subjectType: LINE/FILE` to post on unchanged files. GraphQL constants as module-level strings is clean. |
| `sync/command.py` | `run_sync_comments`, `check_and_resolve_merges` | Core orchestration | Readable, linear control flow. `dry_run` and `force` flags implemented correctly. State is saved per-PR (not only at end), so a partial run doesn't lose progress. |
| `publisher/client.py` | `get_page_inline/footer_comments`, `add_comment_reply`, `resolve_*` | Confluence API integration | GET-then-PUT for resolve is the correct pattern given the Confluence v2 API requirement to supply current version number. |

---

## DISCARD Items

None.

---

## ESCALATE Items

None.

---

## Coding Principles Violations

### 1. Bare `assert` in production code
**File**: `src/mkdocs_to_confluence/sync/command.py`, **line 60**
**Principle**: KISS / defensive programming
**Description**: `assert config.confluence is not None` will be silently disabled when Python is run with `-O` (optimisation flag). The CLI validates this before calling `run_sync_comments`, so it never triggers in practice — but it is not a guarantee from the function's perspective. Should be a guard with a proper `RuntimeError` or `ValueError`.
**Severity**: Low (pre-validated by caller, never triggered in practice).

### 2. `page_title` field stores PR title, not Confluence page title
**File**: `src/mkdocs_to_confluence/sync/command.py`, **line 124** / `src/mkdocs_to_confluence/sync/state.py`, **line 16**
**Principle**: Readability / naming accuracy
**Description**: `PRRecord.page_title` is documented as the Confluence page title, but is populated with `pr_title` ("Documentation review: docs/foo.md"). The field value is only stored in the JSON state file and never read back for any logic, so it has no runtime impact. However, it will confuse anyone inspecting `.mk2conf-sync-state.json`.
**Severity**: Low (no functional impact).

### 3. Redundant URL reassignment in pagination loops
**File**: `src/mkdocs_to_confluence/publisher/client.py`, **lines 557 and 575**
**Principle**: KISS / readability
**Description**: Inside the pagination `while True` loops, after detecting `next_url`, both `get_page_inline_comments` and `get_page_footer_comments` re-assign `url` to the original constructed URL (e.g. `self._v2(f"/pages/{page_id}/inline-comments")`). This is dead code — the URL never changes because cursor-based pagination is used. The `url` variable could simply be set once before the loop. It does not cause a bug because the cursor param correctly identifies the next page, but it creates false impression that `url` changes per page.
**Severity**: Low (no bug, misleading pattern).

### 4. `httpx.Client` created per method call
**File**: `src/mkdocs_to_confluence/sync/github.py`, **lines 32, 51, 89, 100**
**Principle**: Performance / resource efficiency
**Description**: Every method on `GitHubReviewClient` opens and closes a new `httpx.Client` (TCP connection + TLS handshake). For a typical run that calls `create_review_branch` + `create_pull_request` + N×`post_review_comment`, this creates N+2 connections. For the current use case (handful of pages, handful of comments) this is acceptable overhead. Not worth fixing until the feature is used at scale.
**Severity**: Negligible in current use.

---

## Minimality Analysis

The feature scope is precisely implemented:
- No speculative abstractions beyond `ReviewPlatformClient` Protocol (which is directly motivated by the design requirement to avoid GitHub lock-in).
- No unused config fields.
- `_branch_name`, `_build_pr_body` are private helpers only used within `command.py` — correct scope.
- `platform.py` adds 51 lines for an interface with one real implementor. This is the one area where minimality is traded against the stated architectural goal. Given the explicit requirement ("interface to GitHub is abstracted away so other integrations can easily be added"), it is justified.

---

## Quality Score Breakdown

| Category | Score | Notes |
|---|---|---|
| Compilation/Type Check | 20/20 | mypy clean |
| Test Discovery | 20/20 | 1041 tests pass |
| Minimality | 18/20 | `page_title` naming mismatch, platform Protocol is 1 implementor |
| Coding Principles | 22/30 | 3 violations (bare assert, naming, dead url reassignment) |
| Test Quality | 9/10 | One fragile assertion in `test_sync_comments.py` line 111 (`body.split("\n")[2]` positional check) |
| **Deductions** | **-3** | 1× coding principle violation (URL reassignment in 2 places, treated as one pattern) |
| **Final Score** | **86/100** | |

---

## Technical Debt

| File | Line | Type | Description |
|---|---|---|---|
| `sync/command.py` | 60 | `AIDEV-TODO` | Replace bare `assert config.confluence is not None` with `if not config.confluence: raise RuntimeError(...)` |
| `sync/state.py` | 16 | `AIDEV-TODO` | Rename `page_title` field to `pr_title` to match what is actually stored, or populate it with the actual Confluence page title |
| `publisher/client.py` | 557, 575 | `AIDEV-REFACTOR` | Remove redundant `url = self._v2(...)` reassignment in both pagination loops; `url` never changes when using cursor pagination |
| `sync/github.py` | 32,51,89,100 | `AIDEV-PERF` | Consider a single shared `httpx.Client` as a context manager wrapping the full sync run, rather than one per method call |
| `sync/command.py` | 217 | `AIDEV-TODO` | `_branch_name` does not handle collisions — two paths that slugify identically (e.g. `docs/api-ref.md` and `docs/api ref.md`) will cause GitHub 422 on branch creation |

---

## Recommendations

1. **Fix bare assert** (low effort) — `command.py:60`: replace with an explicit `RuntimeError`. The CLI already validates this, so it is purely defensive, but it is the correct pattern for a library function.
2. **Fix `page_title` naming** (low effort) — rename the field or populate it correctly. The state JSON is user-visible and the current value is confusing.
3. **Remove dead `url` reassignment** (trivial) — `client.py:557,575`: delete the `url = self._v2(...)` lines inside the pagination loops.
4. The remaining items (httpx-per-call, branch name collision) can be deferred until they cause real problems.

---

## Previous Report
*(archived below)*

# Code Review Report
**Scope**: v0.6.7 → v0.6.9 (grid cards + livereload preview)
**Language**: Python 3.12+
**Review Date**: 2026-05-03
**Overall Decision**: ~~**BLOCKED / REJECTED**~~ → **APPROVED** *(post-remediation)*
**Quality Score**: ~~77/100~~ → **91/100**

---

## Summary
- Total Items Reviewed: 13 files (8 source + 5 test) + 1 new test file (post-remediation)
- KEEP: 11
- DISCARD: 0
- ESCALATE: 2 → **0 (both resolved)**
- Tests: ~~902~~ → **918 passed**
- Ruff: all checks passed
- Vulture: clean
- Mypy: clean
- Bandit: clean (1 pre-existing nosec, out of scope)

---

## Technical Validation

### Test Execution
```
918 passed in ~4s
```

### Type / Lint Check
```
ruff: All checks passed
vulture: no unused code
mypy: Success
bandit: 1 nosec (pre-existing, loader/config.py:149 — out of scope)
```

### Coverage
| File | Coverage | Note |
|---|---|---|
| `preview/server.py` | ~~**0%**~~ → **100%** | Resolved by `tests/test_server.py` (15 tests) |
| `preview/render.py` | 100% | |
| `emitter/xhtml.py` | ~97% | Grid card paths fully covered |
| `ir/nodes.py` | ~98% | `walk()` new branches covered |
| `cli.py` | ~97% | Watch HTML-rendering assertion added |

---

## Detailed Review

### KEEP Items (11)

**`ir/nodes.py` — `GridCards` dataclass** ✅
Frozen, typed, minimal. Maps exactly to the feature.

**`ir/__init__.py` — export** ✅
Single-line addition, correct.

**`emitter/xhtml.py` — `_grid_layout_type(n)`** ✅
Pure function, clearly documented, correct logic for 1/2/3-column auto-detect.

**`emitter/xhtml.py` — `_emit_grid_cards(node)`** ✅
Correct padding logic for last row. `emit()` called on each card correctly.

**`parser/markdown.py` — grid card tokenizer** ✅
Correctly identifies grid div, delegates to `_tokenize_grid_cards`, maps to `GridCards` IR node.

**`preprocess/includes.py` — grid card preservation** ✅
`_GRID_CARD_RE` check correctly carves out grid divs before the generic strip pass.

**`preview/render.py` — `_render_layout()`** ✅
Six targeted regex substitutions, correct flexbox mapping, no raw XML leaking to browser.

**`preview/render.py` — `inject_livereload()`** ✅
Minimal JS injection before `</body>`. Polling interval 800ms is reasonable.

**`preview/server.py` — `start_server()` / `_Handler`** ✅ *(logic correct, coverage absent — see ESCALATE)*
Path-traversal guard via `.resolve()` + `.relative_to()` is correct. Daemon thread is correct. `Cache-Control: no-store` is correct.

**`cli.py` — `--watch` flag + `_cmd_preview` watch branch** ✅
Temp dir creation, `--watch` implies `--html`, browser open, `watch_and_rebuild` call — all correct.

**Tests: `test_ir.py`, `test_emitter.py`, `test_parser.py`** ✅
Coverage is thorough: immutability, equality, `walk()`, all layout types, padding, admonition-inside-card, `ac:layout` wrapper. Meaningful assertions throughout.

---

### DISCARD Items

**None.**

---

### ESCALATE Items

**ESCALATE-1 — `preview/server.py`: 0% test coverage** ✅ *Resolved*
`File: tests/test_server.py` (new, 15 tests)

~~The entire server module was untested.~~ Now fully covered:
- `bump_version()` — thread-safety verified under 20 concurrent increments
- `_Handler.do_GET("/__livereload")` — correct body, `Cache-Control: no-store`
- `do_GET("/../etc/passwd")` — path-traversal returns 403
- `_serve_file()` — correct MIME for HTML, 404 on missing file
- `start_server()` — binds, responds on assigned port
- `watch_and_rebuild()` — fires on mtime change, errors caught, `bump_version` called

**ESCALATE-2 — `test_cli.py` `TestWatchFlag`: missing testable assertion** ✅ *Resolved*
`File: tests/test_cli.py — TestWatchFlag.test_watch_renders_html_not_raw_xhtml`

Added test verifies that `--watch` triggers `render_page` (HTML output path), not raw XHTML passthrough. Mocks `compile_page`, `render_page`, `inject_livereload`, `start_server`, `watch_and_rebuild`.

---

## Coding Principles Violations

| File | Line | Principle | Description |
|---|---|---|---|
| `ir/nodes.py` | 503–510 | Maintainability | `walk()` handles only 2 levels of tuple nesting. A third level would silently miss nodes. Recursive approach would generalise correctly. **(Non-blocking — no 3-level nesting exists in current IR.)** |
| `preview/server.py` | 13–21 | KISS / readability | `_reload_version` as a module-level global mutated via `global` statement. A `threading.Lock`-wrapped counter class would be cleaner. **(Non-blocking — lock handles thread safety correctly.)** |
| `preview/server.py` | 58 | Correctness | ~~`_serve_file` only differentiates `text/html` vs `application/octet-stream`. CSS, JS, PNG served for the preview would get the wrong MIME type.~~ **Investigated and closed**: preview HTML is 100% self-contained (inline CSS, inline JS, base64 images). Server never receives requests for CSS/JS/image assets. Not a real bug. |

---

## Minimality Analysis

All 8 source changes map directly to the two features (grid cards, livereload). No speculative code found. The removed comment (`# Map page title → html filename for cross-page link rewriting`) in `cli.py` was a minor readability loss — not blocking but noted.

---

## Quality Score Breakdown

| Category | Score | Notes |
|---|---|---|
| Compilation / type check | 20/20 | Clean across all tools |
| Test discovery | 20/20 | 918 pass, no discovery errors |
| Minimality | 19/20 | All code maps to features; minor: removed useful inline comment |
| Coding principles | 27/30 | −3 walk() depth limit (theoretical, non-blocking); global state item downgraded (lock is correct) |
| Test quality | 10/10 | server.py 100% coverage; TestWatchFlag HTML-rendering assertion added |
| Deductions | −5 | −3 walk() depth, −2 global readability |
| **Final Score** | **91/100** | |

---

## Technical Debt

| File | Line | Type | Description |
|---|---|---|---|
| `ir/nodes.py` | 503 | `AIDEV-REFACTOR` | `walk()` tuple recursion is depth-limited to 2. Rewrite with a proper recursive helper when a third nesting level appears. |
| `preview/server.py` | 13 | `AIDEV-REFACTOR` | Replace module-level `_reload_version` global + `global` statement with a small `_Counter` class wrapping the lock. Cosmetic improvement only — threading is already correct. |
| ~~`preview/server.py`~~ | ~~58~~ | ~~`AIDEV-TODO`~~ | ~~Add `mimetypes.guess_type()` to `_serve_file`.~~ **Closed**: preview HTML is self-contained; MIME gap has no practical impact. |

---

## Recommendations

1. ~~**Unblock ESCALATE-1**: Add `tests/test_server.py`~~ → **Done** (15 tests, 100% coverage)
2. ~~**Unblock ESCALATE-2**: Add assertion to `TestWatchFlag`~~ → **Done** (`test_watch_renders_html_not_raw_xhtml`)
3. **Non-blocking**: `walk()` recursion depth — fix when a 3-level nested IR field is introduced.
4. ~~MIME type gap in `_serve_file`~~ → **Closed**: not a real issue; preview HTML is self-contained.

---

## Final Verdict

~~**BLOCKED / REJECTED — 77/100**~~

**APPROVED — 91/100** *(post-remediation)*

Both ESCALATEs resolved: `server.py` at 100% coverage (15 tests including path-traversal guard), `TestWatchFlag` extended with a behavioral assertion. MIME type debt item investigated and closed — preview HTML is self-contained. One remaining non-blocking debt item: `walk()` depth limit in `ir/nodes.py` (no current IR node triggers it).

Previous report (v0.5.12): Approved 97/100.
