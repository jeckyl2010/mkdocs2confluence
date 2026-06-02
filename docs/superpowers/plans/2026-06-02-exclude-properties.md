# exclude_properties Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users list front matter keys in `mkdocs.yml` that should be excluded from the Confluence Page Properties table.

**Architecture:** Add an optional `exclude_properties` list to the `confluence:` block, parsed into `ConfluenceConfig`. Thread it from `compile_page` into the pure `extract_front_matter` function, which skips matching raw keys when building the properties table. Special behaviors (title, tags→labels, status) are computed independently and unaffected.

**Tech Stack:** Python 3.12+, pytest, ruff, mypy, vulture. Run tests with `uv run pytest -q`.

---

### Task 1: Exclude keys in front matter extraction

**Files:**
- Modify: `src/mkdocs_to_confluence/preprocess/frontmatter.py`
- Test: `tests/test_frontmatter.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_frontmatter.py` (the file already imports `extract_front_matter` and defines `_SAMPLE`, which contains keys `title`, `documentId`, `version`, `lastUpdated`, `author`, `tags: [architecture, iam, keycloak]`, `ready`, `source`):

```python
class TestExcludeProperties:
    def test_excluded_key_omitted_from_table(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("version",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Version" not in labels

    def test_non_excluded_keys_retained(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("version",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Author" in labels
        assert "Document ID" in labels

    def test_excluding_tags_still_yields_labels(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("tags",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Tags" not in labels
        # side-effect preserved: tags still become Confluence labels
        assert fm.labels == ("architecture", "iam", "keycloak")

    def test_excluding_title_keeps_page_title(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("title",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Title" not in labels
        assert fm.title == "Architecture Proposal – IAM"

    def test_excluding_nonexistent_key_is_noop(self) -> None:
        baseline, _ = extract_front_matter(_SAMPLE)
        excluded, _ = extract_front_matter(_SAMPLE, exclude_properties=("not_here",))
        assert baseline is not None and excluded is not None
        assert baseline.properties == excluded.properties

    def test_exclude_is_case_sensitive(self) -> None:
        # 'Version' != 'version' — wrong case does not exclude
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("Version",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Version" in labels

    def test_default_no_exclude_preserves_behavior(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE)
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Version" in labels and "Author" in labels
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_frontmatter.py::TestExcludeProperties -q`
Expected: FAIL — `extract_front_matter() got an unexpected keyword argument 'exclude_properties'`

- [ ] **Step 3: Add the `exclude_properties` parameter**

In `src/mkdocs_to_confluence/preprocess/frontmatter.py`, change the `extract_front_matter` signature and its call to `_build_node`. Current:

```python
def extract_front_matter(text: str) -> tuple[FrontMatter | None, str]:
```

becomes:

```python
def extract_front_matter(
    text: str, exclude_properties: tuple[str, ...] = ()
) -> tuple[FrontMatter | None, str]:
```

Update the docstring `Args:` section to add:

```
        exclude_properties: Raw front matter keys to omit from the Page
            Properties table. Matching is exact and case-sensitive. Special
            behaviors (title, tags->labels, status) are unaffected.
```

At the end of the function, change:

```python
    return _build_node(raw), remaining
```

to:

```python
    return _build_node(raw, exclude_properties), remaining
```

- [ ] **Step 4: Apply the exclusion in `_build_node`**

Change the `_build_node` signature. Current:

```python
def _build_node(raw: dict[str, Any]) -> FrontMatter:
    """Convert a raw front matter dict to a :class:`FrontMatter` IR node."""
```

becomes:

```python
def _build_node(raw: dict[str, Any], exclude: tuple[str, ...] = ()) -> FrontMatter:
    """Convert a raw front matter dict to a :class:`FrontMatter` IR node.

    ``exclude`` lists raw keys to omit from the properties table (table rows
    only — title/labels/status side-effects are computed independently below).
    """
    skip = _STRIP_FIELDS | set(exclude)
```

Then in the two property-appending loops, replace the `_STRIP_FIELDS` checks with `skip`. First loop, current:

```python
    for key in _FIELD_ORDER:
        if key in raw and key not in _STRIP_FIELDS and key != "subtitle":
```

becomes:

```python
    for key in _FIELD_ORDER:
        if key in raw and key not in skip and key != "subtitle":
```

Second loop, current:

```python
    for key, value in raw.items():
        if key in seen or key in _STRIP_FIELDS or key == "subtitle":
            continue
```

becomes:

```python
    for key, value in raw.items():
        if key in seen or key in skip or key == "subtitle":
            continue
```

Leave the `title`, `subtitle`, `confluence_status`, and `labels` computations (above the loops) untouched — that is what preserves the side-effects.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_frontmatter.py -q`
Expected: PASS (new `TestExcludeProperties` class plus all existing frontmatter tests).

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/preprocess/frontmatter.py tests/test_frontmatter.py
git commit -m "feat(frontmatter): support excluding keys from properties table"
```

---

### Task 2: Parse `exclude_properties` config key

**Files:**
- Modify: `src/mkdocs_to_confluence/loader/config.py`
- Test: `tests/test_exclude_properties_config.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exclude_properties_config.py`:

```python
"""Tests for confluence.exclude_properties config key."""

from __future__ import annotations

from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import ConfigError, load_config


def _write_mkdocs(tmp_path: Path, extra: str = "") -> Path:
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (tmp_path / "mkdocs.yml").write_text(f"site_name: Test\n{extra}", encoding="utf-8")
    return tmp_path / "mkdocs.yml"


_BASE = """
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
  token: tok
"""


def test_exclude_properties_absent_gives_empty_tuple(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _BASE))
    assert cfg.confluence is not None
    assert cfg.confluence.exclude_properties == ()


def test_exclude_properties_list_parsed(tmp_path: Path) -> None:
    extra = _BASE + "  exclude_properties:\n    - source_documents\n    - internal_ref\n"
    cfg = load_config(_write_mkdocs(tmp_path, extra))
    assert cfg.confluence is not None
    assert cfg.confluence.exclude_properties == ("source_documents", "internal_ref")


def test_exclude_properties_entries_stringified(tmp_path: Path) -> None:
    # YAML may parse bare tokens as non-strings; entries must be coerced to str.
    extra = _BASE + "  exclude_properties:\n    - 123\n"
    cfg = load_config(_write_mkdocs(tmp_path, extra))
    assert cfg.confluence is not None
    assert cfg.confluence.exclude_properties == ("123",)


def test_exclude_properties_non_list_raises(tmp_path: Path) -> None:
    extra = _BASE + "  exclude_properties: source_documents\n"
    with pytest.raises(ConfigError, match="exclude_properties"):
        load_config(_write_mkdocs(tmp_path, extra))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_exclude_properties_config.py -q`
Expected: FAIL — `ConfluenceConfig` has no attribute `exclude_properties`.

- [ ] **Step 3: Add the field to `ConfluenceConfig`**

In `src/mkdocs_to_confluence/loader/config.py`, in the `ConfluenceConfig` dataclass, after the existing `changelog_file` field, add:

```python
    exclude_properties: tuple[str, ...] = ()  # front matter keys to omit from Page Properties table
```

- [ ] **Step 4: Parse and validate in `load_config`**

In `load_config`, immediately before the `confluence = ConfluenceConfig(` constructor call (currently at line ~279), add:

```python
        # exclude_properties (optional) — raw front matter keys to omit from
        # the Page Properties table. Pure list of literal keys, no wildcards.
        raw_exclude = raw_conf.get("exclude_properties")
        if raw_exclude is None:
            exclude_properties: tuple[str, ...] = ()
        elif isinstance(raw_exclude, list):
            exclude_properties = tuple(str(k) for k in raw_exclude)
        else:
            raise ConfigError(
                "mkdocs.yml: 'confluence.exclude_properties' must be a list of "
                f"front matter keys, got {type(raw_exclude).__name__}."
            )
```

Then add the field to the constructor call, after `changelog_file=changelog_file,`:

```python
            exclude_properties=exclude_properties,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_exclude_properties_config.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/loader/config.py tests/test_exclude_properties_config.py
git commit -m "feat(config): parse confluence.exclude_properties"
```

---

### Task 3: Thread config into the compile pipeline

**Files:**
- Modify: `src/mkdocs_to_confluence/compiler/page.py:58`
- Test: `tests/test_publish_pipeline.py`

- [ ] **Step 1: Write the failing test**

`tests/test_publish_pipeline.py` already imports `ConfluenceConfig, MkDocsConfig`, `NavNode`, and `compile_page`, and defines helpers `_make_config(docs_dir)` and `_page_node(title, path)`. The default `_make_config` sets no `confluence` block, so add a test that builds its own config carrying `exclude_properties`. Add to `tests/test_publish_pipeline.py`, after `test_compile_page_with_source_path_none_returns_empty`:

```python
def test_compile_page_excludes_configured_properties(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text(
        "---\nauthor: Alice\nsecret_field: hush\n---\n\n# Page\n",
        encoding="utf-8",
    )

    node = _page_node("Page", md)
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=docs,
        repo_url=None,
        edit_uri=None,
        nav=None,
        confluence=ConfluenceConfig(
            base_url="https://example.atlassian.net",
            space_key="TECH",
            email="user@example.com",
            token="tok",
            exclude_properties=("secret_field",),
        ),
    )
    xhtml, attachments, labels, _, _ = compile_page(node, config)

    assert "hush" not in xhtml
    assert "Alice" in xhtml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_pipeline.py -q -k exclude`
Expected: FAIL — `hush` still present in `xhtml` (exclusion not yet wired in).

- [ ] **Step 3: Wire the config through**

In `src/mkdocs_to_confluence/compiler/page.py`, change line 58. Current:

```python
    front_matter, preprocessed = extract_front_matter(preprocessed)
```

becomes:

```python
    exclude_properties = (
        config.confluence.exclude_properties if config.confluence else ()
    )
    front_matter, preprocessed = extract_front_matter(
        preprocessed, exclude_properties=exclude_properties
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_pipeline.py -q -k exclude`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mkdocs_to_confluence/compiler/page.py tests/test_publish_pipeline.py
git commit -m "feat(compile): apply exclude_properties to page front matter"
```

---

### Task 4: Documentation

**Files:**
- Modify: `docs/features.md`
- Modify: `README.md`

- [ ] **Step 1: Document in features.md**

In `docs/features.md`, in the YAML front matter / Page Properties area, add a sentence describing the new key. Use this wording:

```markdown
Set `confluence.exclude_properties` in `mkdocs.yml` to a list of raw front
matter keys to omit from the Page Properties table — e.g. internal tooling
fields like `source_documents`. Matching is exact and case-sensitive. Special
behaviors are unaffected: `title` still sets the page title, `tags` still
become Confluence labels, and `status` still sets the page status.
```

- [ ] **Step 2: Document in README.md Configuration section**

In `README.md`, under the `## Configuration` section (around line 107), add a short `confluence:` example showing the key:

```markdown
To hide internal front matter fields from the Page Properties table:

```yaml
confluence:
  exclude_properties:
    - source_documents
    - internal_ref
```
```

- [ ] **Step 3: Commit**

```bash
git add docs/features.md README.md
git commit -m "docs: document confluence.exclude_properties"
```

---

### Final verification

- [ ] **Step 1: Run the full pre-release checklist**

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run vulture src --min-confidence 80
```

Expected: all pass, no warnings. Then the feature is ready for a release (separate `/release` step — minor version bump, since this is a `feat`).
