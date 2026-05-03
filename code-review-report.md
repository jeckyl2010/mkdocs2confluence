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
