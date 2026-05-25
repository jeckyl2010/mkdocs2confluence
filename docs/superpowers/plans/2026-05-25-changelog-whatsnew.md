# Changelog / What's New Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `changelog:` config key so mk2conf publishes a designated Markdown file as a top-level "What's New" Confluence page, and ship an `install-skill` command that installs an AI changelog-generation skill into all detected AI tools.

**Architecture:** Part 1 adds `changelog_file` to `ConfluenceConfig`, creates `publisher/changelog.py` with a self-contained `publish_changelog()` function, and wires it into `_cmd_publish` in `cli.py`. Part 2 bundles a `SKILL.md` as package data and adds an `install-skill` CLI command backed by `skill_installer.py`.

**Tech Stack:** Python 3.12+, existing `ConfluenceClient`, `compile_page` from `publisher/planner.py`, `importlib.resources` for package data, `argparse` for the new CLI subcommand.

---

## File map

**Part 1 — changelog publish:**
- Modify: `src/mkdocs_to_confluence/loader/config.py` — add `changelog_file` field + parse/validate
- Create: `src/mkdocs_to_confluence/publisher/changelog.py` — compile + publish changelog page
- Modify: `src/mkdocs_to_confluence/cli.py` — wire `publish_changelog` into `_cmd_publish`
- Create: `tests/test_changelog_config.py` — config parsing + path validation tests
- Create: `tests/test_changelog_publish.py` — `publish_changelog` unit tests

**Part 2 — skill + installer:**
- Create: `src/mkdocs_to_confluence/skills/mkdocs-changelog/SKILL.md` — bundled skill template
- Modify: `pyproject.toml` — add `[tool.setuptools.package-data]` for `skills/**/*`
- Create: `src/mkdocs_to_confluence/skill_installer.py` — detection + installation logic
- Modify: `src/mkdocs_to_confluence/cli.py` — add `install-skill` subcommand
- Create: `tests/test_skill_installer.py` — installer unit tests

---

## Task 1: Add `changelog_file` to `ConfluenceConfig`

**Files:**
- Modify: `src/mkdocs_to_confluence/loader/config.py`
- Create: `tests/test_changelog_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_changelog_config.py
"""Tests for confluence.changelog config key."""

from __future__ import annotations

from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import ConfigError, load_config


def _write_mkdocs(tmp_path: Path, extra: str = "") -> Path:
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (tmp_path / "mkdocs.yml").write_text(
        f"site_name: Test\n{extra}", encoding="utf-8"
    )
    return tmp_path / "mkdocs.yml"


_BASE = """
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
  token: tok
"""


def test_changelog_absent_gives_none(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _BASE))
    assert cfg.confluence is not None
    assert cfg.confluence.changelog_file is None


def test_changelog_empty_string_gives_none(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _BASE + "  changelog: ''\n"))
    assert cfg.confluence is not None
    assert cfg.confluence.changelog_file is None


def test_changelog_null_gives_none(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _BASE + "  changelog: ~\n"))
    assert cfg.confluence is not None
    assert cfg.confluence.changelog_file is None


def test_changelog_valid_path_stored(tmp_path: Path) -> None:
    (tmp_path / "docs" / "CHANGELOG.md").write_text("# Log\n", encoding="utf-8")
    cfg = load_config(_write_mkdocs(tmp_path, _BASE + "  changelog: CHANGELOG.md\n"))
    assert cfg.confluence is not None
    assert cfg.confluence.changelog_file == "CHANGELOG.md"


def test_changelog_path_escaping_docs_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="escapes docs_dir"):
        load_config(_write_mkdocs(tmp_path, _BASE + "  changelog: ../secret.md\n"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_changelog_config.py -v
```
Expected: FAIL — `ConfluenceConfig` has no `changelog_file` attribute.

- [ ] **Step 3: Add `changelog_file` field to `ConfluenceConfig`**

In `src/mkdocs_to_confluence/loader/config.py`, add one line to the `ConfluenceConfig` dataclass after `allow_any_host`:

```python
    allow_any_host: bool = False  # set True to allow non-Atlassian Cloud base_url hosts
    changelog_file: str | None = None  # path relative to docs_dir; None means disabled
```

- [ ] **Step 4: Parse and validate `changelog` in `load_config`**

In `load_config`, inside the `if raw_conf is not None:` block, add this block **before** the `confluence = ConfluenceConfig(...)` constructor call (around line 258, after the `github_base_branch` line):

```python
        # changelog (optional) — path relative to docs_dir
        changelog_file: str | None = None
        raw_changelog = raw_conf.get("changelog")
        if raw_changelog is not None:
            cl_str = str(raw_changelog).strip()
            if cl_str:
                candidate = (docs_dir / cl_str).resolve()
                try:
                    candidate.relative_to(docs_dir)
                except ValueError:
                    raise ConfigError(
                        f"mkdocs.yml: 'confluence.changelog' path {cl_str!r} "
                        "escapes docs_dir. The path must be relative to the docs directory."
                    )
                changelog_file = cl_str
```

- [ ] **Step 5: Pass `changelog_file` to the `ConfluenceConfig` constructor**

In the same `load_config` function, add `changelog_file=changelog_file,` to the `ConfluenceConfig(...)` call:

```python
        confluence = ConfluenceConfig(
            base_url=base_url.rstrip("/"),
            space_key=space_key,
            email=email.strip(),
            token=token,
            parent_page_id=parent_page_id,
            full_width=bool(raw_conf.get("full_width", True)),
            nav_file=str(raw_conf.get("nav_file", ".pages")),
            mermaid_render=str(raw_conf.get("mermaid_render", "kroki")),
            github_repo=str(raw_conf["github_repo"]) if raw_conf.get("github_repo") else None,
            github_token=(str(raw_conf["github_token"]) if raw_conf.get("github_token")
                          else os.environ.get("GITHUB_TOKEN") or None),
            github_base_branch=str(raw_conf.get("github_base_branch", "main")),
            allow_any_host=allow_any_host,
            changelog_file=changelog_file,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_changelog_config.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 7: Run the full suite to catch regressions**

```bash
uv run pytest -q
```
Expected: All existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add src/mkdocs_to_confluence/loader/config.py tests/test_changelog_config.py
git commit -m "feat: add changelog_file to ConfluenceConfig with docs_dir boundary check"
```

---

## Task 2: Create `publisher/changelog.py`

**Files:**
- Create: `src/mkdocs_to_confluence/publisher/changelog.py`
- Create: `tests/test_changelog_publish.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_changelog_publish.py
"""Unit tests for publisher/changelog.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.publisher.changelog import publish_changelog


def _conf(tmp_path: Path, changelog: str | None = "CHANGELOG.md") -> ConfluenceConfig:
    return ConfluenceConfig(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        token="tok",
        space_key="TECH",
        changelog_file=changelog,
    )


def _config(tmp_path: Path) -> MkDocsConfig:
    return MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path / "docs",
        repo_url=None,
        edit_uri=None,
        nav=None,
    )


def _make_client(*, existing_id: str | None = None, stored_hash: str = "") -> MagicMock:
    client = MagicMock()
    if existing_id is not None:
        client.find_page.return_value = {"id": existing_id, "version": {"number": 3}}
    else:
        client.find_page.return_value = None
    client.get_content_hash.return_value = stored_hash
    client.create_page.return_value = {"id": "999"}
    return client


def test_publish_changelog_skipped_when_no_file_configured(tmp_path: Path) -> None:
    conf = _conf(tmp_path, changelog=None)
    config = _config(tmp_path)
    client = _make_client()
    publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)
    client.find_page.assert_not_called()


def test_publish_changelog_warns_when_file_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "docs").mkdir()
    conf = _conf(tmp_path)
    config = _config(tmp_path)
    client = _make_client()
    publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=False)
    captured = capsys.readouterr()
    assert "not found" in captured.err
    client.create_page.assert_not_called()


def test_publish_changelog_skips_unchanged_content(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nSome change.\n", encoding="utf-8")
    conf = _conf(tmp_path)
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("compiled-xhtml", [], (), None, None)
        import hashlib
        expected_hash = hashlib.sha256(b"compiled-xhtml").hexdigest()
        client = _make_client(existing_id="42", stored_hash=expected_hash)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    client.create_page.assert_not_called()
    client.update_page.assert_not_called()


def test_publish_changelog_creates_new_page(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nNew content.\n", encoding="utf-8")
    conf = _conf(tmp_path)
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml-new", [], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    client.create_page.assert_called_once()
    call_kwargs = client.create_page.call_args
    assert call_kwargs.kwargs.get("parent_id") is None  # no parent_page_id set


def test_publish_changelog_updates_existing_page(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nUpdated.\n", encoding="utf-8")
    conf = _conf(tmp_path)
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml-updated", [], (), None, None)
        client = _make_client(existing_id="77", stored_hash="old-hash")
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    client.update_page.assert_called_once()
    args = client.update_page.call_args
    assert args.args[0] == "77"   # page_id
    assert args.args[3] == 4      # version + 1


def test_publish_changelog_uses_parent_page_id_when_set(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nContent.\n", encoding="utf-8")
    conf = ConfluenceConfig(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        token="tok",
        space_key="TECH",
        parent_page_id="ROOT-99",
        changelog_file="CHANGELOG.md",
    )
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml", [], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    call_kwargs = client.create_page.call_args
    assert call_kwargs.kwargs.get("parent_id") == "ROOT-99"


def test_publish_changelog_uses_title_from_front_matter(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text(
        "---\ntitle: Release Notes\n---\n\n## 2026-05-25\n\nContent.\n",
        encoding="utf-8",
    )
    conf = _conf(tmp_path)
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml", [], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    call_kwargs = client.create_page.call_args
    assert call_kwargs.args[1] == "Release Notes"


def test_publish_changelog_defaults_title_to_whats_new(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nContent.\n", encoding="utf-8")
    conf = _conf(tmp_path)
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml", [], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    call_kwargs = client.create_page.call_args
    assert call_kwargs.args[1] == "What's New"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_changelog_publish.py -v
```
Expected: FAIL — `publisher/changelog.py` does not exist.

- [ ] **Step 3: Create `publisher/changelog.py`**

```python
# src/mkdocs_to_confluence/publisher/changelog.py
"""Compile and publish the standalone changelog page."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.publisher.planner import compile_page

if TYPE_CHECKING:
    from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
    from mkdocs_to_confluence.publisher.client import ConfluenceClient

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n?)---\s*\n?", re.DOTALL)


def _extract_title(source_path: Path) -> str | None:
    """Return the ``title`` value from YAML front matter, or ``None`` if absent."""
    try:
        raw = source_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FRONT_MATTER_RE.match(raw)
    if not m:
        return None
    try:
        fm: object = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    val = fm.get("title")
    return str(val).strip() if val else None


def publish_changelog(
    config: MkDocsConfig,
    conf_config: ConfluenceConfig,
    client: ConfluenceClient,
    space_id: str,
    *,
    space_key: str | None = None,
    quiet: bool = False,
) -> None:
    """Compile and publish the changelog page if ``conf_config.changelog_file`` is set."""
    if not conf_config.changelog_file:
        return

    changelog_path = config.docs_dir / conf_config.changelog_file
    if not changelog_path.exists():
        print(
            f"  [warn] changelog: file not found: {changelog_path}",
            file=sys.stderr,
        )
        return

    title = _extract_title(changelog_path) or "What's New"

    node = NavNode(
        title=title,
        docs_path=str(changelog_path.relative_to(config.docs_dir)),
        source_path=changelog_path,
        level=0,
    )

    if not quiet:
        print(f"  compiling  '{title}'  (changelog)")

    xhtml, attachments, labels, confluence_status, version_message = compile_page(
        node, config, quiet=quiet
    )

    xhtml_hash = hashlib.sha256(xhtml.encode()).hexdigest()
    existing = client.find_page(space_id, title)

    if existing is not None and client.get_content_hash(str(existing["id"])) == xhtml_hash:
        if not quiet:
            print(f"  unchanged  '{title}'  (changelog)")
        return

    parent_id = conf_config.parent_page_id

    if existing is None:
        page = client.create_page(space_id, title, xhtml, parent_id=parent_id)
        page_id = str(page["id"])
        # Do NOT stamp as managed: _prune_orphans skips unmanaged pages, so
        # this ensures --prune never deletes the changelog page.
        if not quiet:
            print(f"  created    '{title}'  (changelog)")
    else:
        page_id = str(existing["id"])
        version: int = existing["version"]["number"]
        client.update_page(
            page_id, title, xhtml, version + 1,
            parent_id=parent_id,
            version_message=version_message,
        )
        if not quiet:
            print(f"  updated    '{title}'  (changelog)")

    try:
        client.set_content_hash(page_id, xhtml_hash)
    except Exception:
        pass

    if labels:
        try:
            client.set_page_labels(page_id, labels)
        except Exception:
            pass

    if conf_config.full_width:
        try:
            client.set_page_full_width(page_id)
        except Exception:
            pass

    if confluence_status:
        try:
            client.set_page_status(page_id, confluence_status, space_key=space_key)
        except Exception:
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_changelog_publish.py -v
```
Expected: All 8 tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
uv run pytest -q
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/publisher/changelog.py tests/test_changelog_publish.py
git commit -m "feat: add publisher/changelog.py — compile and publish standalone changelog page"
```

---

## Task 3: Wire `publish_changelog` into `_cmd_publish`

**Files:**
- Modify: `src/mkdocs_to_confluence/cli.py`

- [ ] **Step 1: Add changelog to the dry-run output**

In `_cmd_publish` in `src/mkdocs_to_confluence/cli.py`, find the dry-run block starting at `if args.dry_run:` (around line 502). After the existing dry-run print block and before the `return`, add:

```python
        if conf_config.changelog_file:
            changelog_path = config.docs_dir / conf_config.changelog_file
            exists = "✓" if changelog_path.exists() else "✗ (not found)"
            print(f"  {changelog_path.name} → 'What's New'  (changelog) {exists}")
```

- [ ] **Step 2: Call `publish_changelog` after `execute_publish`**

In `_cmd_publish`, inside the `with ConfluenceClient(conf_config) as client:` block, after the `execute_publish(...)` call (and after the `print(str(report))` line that follows it), add:

```python
            from mkdocs_to_confluence.publisher.changelog import publish_changelog
            publish_changelog(
                config, conf_config, client, space_id,
                space_key=conf_config.space_key,
                quiet=getattr(args, "quiet", False),
            )
```

- [ ] **Step 3: Verify manually with dry-run**

Run against the project's own mkdocs.yml (without a `changelog:` key to confirm it's silently skipped):

```bash
uv run mk2conf publish --dry-run
```
Expected: Output unchanged — no mention of changelog when key is absent.

- [ ] **Step 4: Run the full suite**

```bash
uv run pytest -q
```
Expected: All tests pass.

- [ ] **Step 5: Update README**

Add a row to the configuration table in `README.md` under the `## Configuration` section:

```markdown
| `changelog` | *(none)* | Path to a Markdown file (relative to `docs_dir`) that mk2conf publishes as a top-level "What's New" page in Confluence on every publish run. Optional. |
```

Also add `changelog: CHANGELOG.md` to the example `mkdocs.yml` snippet in `README.md`:

```yaml
confluence:
  base_url: https://yourorg.atlassian.net
  space_key: TECH
  email: user@example.com
  token: !ENV CONFLUENCE_API_TOKEN
  parent_page_id: "123456"           # optional root page
  mermaid_render: kroki              # "kroki" (default) | "kroki:https://your-kroki" | "none"
  full_width: true                   # default: true
  changelog: CHANGELOG.md           # optional "What's New" page
```

- [ ] **Step 6: Commit**

```bash
git add src/mkdocs_to_confluence/cli.py README.md
git commit -m "feat: wire publish_changelog into _cmd_publish; update README"
```

---

## Task 4: Bundle the `SKILL.md` as package data

**Files:**
- Create: `src/mkdocs_to_confluence/skills/mkdocs-changelog/SKILL.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the skills directory**

```bash
mkdir -p src/mkdocs_to_confluence/skills/mkdocs-changelog
```

- [ ] **Step 2: Write `SKILL.md`**

Create `src/mkdocs_to_confluence/skills/mkdocs-changelog/SKILL.md`:

```markdown
---
name: mkdocs-changelog
description: Analyse doc changes since the last CHANGELOG.md update and draft a major-change entry if the changes qualify.
version: "1.0.0"
tags: [documentation, git, changelog, mkdocs, confluence]
specificity: context-specific
tool_agnostic: true
authors: [Anders Hybertz]
tested_on: []
---

# MkDocs Changelog

Decide whether documentation changes since the last `CHANGELOG.md` update are MAJOR, and if so draft a dated changelog entry for review.

## When to use

- After making one or more documentation changes that might constitute a major update
- Before running `mk2conf publish` when you think significant content has been added, removed, or fundamentally changed

## Steps

1. Find the SHA of the last commit that touched `CHANGELOG.md`:

   ```bash
   git log --follow --format="%H" -1 -- <docs_dir>/CHANGELOG.md
   ```

   If the output is empty (file has never been committed), use the first commit SHA:

   ```bash
   git log --reverse --format="%H" | head -1
   ```

2. Get all doc changes since that baseline commit:

   ```bash
   git diff <baseline_sha>..HEAD -- <docs_dir>/
   ```

3. Read the existing `CHANGELOG.md` (if it exists) for context on what was previously recorded.

4. Analyse the diff and decide: does it contain a **MAJOR** change?

   **MAJOR** — warrants a new changelog entry:
   - A new top-level documentation area or section added
   - A significant area deleted or substantially restructured
   - A fundamental definition, concept, or policy changed in a way that affects how readers understand the subject

   **Not MAJOR** — skip silently:
   - Typo fixes, grammar corrections, spelling changes
   - Formatting adjustments, diagram tweaks, image swaps
   - Small additions (a paragraph, a note, a clarification) that don't change the substance
   - Rewordings that preserve the original meaning

5. **If not MAJOR**: Report what was found and explain briefly why it did not qualify. Stop — do not modify any file.

6. **If MAJOR**: Draft a new changelog entry using the format below and **prepend** it to `CHANGELOG.md` (newest entry first):

   ```markdown
   ## YYYY-MM-DD — Brief title describing the major change

   One or two sentences summarising what fundamentally changed and why it matters to readers.

   ### Added
   - …

   ### Changed
   - …

   ### Removed
   - …
   ```

   Rules:
   - Use today's date for `YYYY-MM-DD`.
   - Only include the `Added`, `Changed`, and `Removed` sections when non-empty.
   - Keep the title concise — it appears in the Confluence "What's New" page.

   Do **not** run `git commit` — leave the file modified for the user to review, adjust if needed, and commit before running `mk2conf publish`.

## Pitfalls

- Do not update `CHANGELOG.md` for minor changes — a noisy changelog loses its value quickly.
- Never commit automatically — the user must review the entry.
- If `CHANGELOG.md` does not exist yet, create it with just the new entry (no header, no prior content).

## Verification

- The diff clearly shows a MAJOR change (new section, deleted area, or changed fundamental definition).
- The drafted entry is concise and written for a documentation reader, not a developer.
- `CHANGELOG.md` has the new entry at the top (newest first).
- No `git commit` was run.
```

- [ ] **Step 3: Add package data to `pyproject.toml`**

Add a new section after `[tool.setuptools.packages.find]`:

```toml
[tool.setuptools.package-data]
"mkdocs_to_confluence" = ["skills/**/*"]
```

- [ ] **Step 4: Verify the file is discoverable at install time**

```bash
uv run python -c "
from importlib.resources import files
content = files('mkdocs_to_confluence').joinpath('skills/mkdocs-changelog/SKILL.md').read_text(encoding='utf-8')
assert 'mkdocs-changelog' in content
print('OK — skill content loaded,', len(content), 'bytes')
"
```
Expected: `OK — skill content loaded, <N> bytes`

- [ ] **Step 5: Commit**

```bash
git add src/mkdocs_to_confluence/skills/mkdocs-changelog/SKILL.md pyproject.toml
git commit -m "feat: bundle mkdocs-changelog SKILL.md as package data"
```

---

## Task 5: Create `skill_installer.py` and `install-skill` CLI command

**Files:**
- Create: `src/mkdocs_to_confluence/skill_installer.py`
- Modify: `src/mkdocs_to_confluence/cli.py`
- Create: `tests/test_skill_installer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_skill_installer.py
"""Tests for skill detection and installation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mkdocs_to_confluence.skill_installer import detect_targets, install_skill


def test_detect_no_tools_returns_empty(tmp_path: Path) -> None:
    with patch("mkdocs_to_confluence.skill_installer._hermes_dir", return_value=tmp_path / "nonexistent"):
        targets = detect_targets(tmp_path)
    assert targets == []


def test_detect_claude_when_dot_claude_present(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    with patch("mkdocs_to_confluence.skill_installer._hermes_dir", return_value=tmp_path / "nonexistent"):
        targets = detect_targets(tmp_path)
    assert "claude" in targets


def test_detect_superpowers_when_github_skills_present(tmp_path: Path) -> None:
    (tmp_path / ".github" / "skills").mkdir(parents=True)
    with patch("mkdocs_to_confluence.skill_installer._hermes_dir", return_value=tmp_path / "nonexistent"):
        targets = detect_targets(tmp_path)
    assert "superpowers" in targets


def test_detect_copilot_when_instructions_file_present(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text("", encoding="utf-8")
    with patch("mkdocs_to_confluence.skill_installer._hermes_dir", return_value=tmp_path / "nonexistent"):
        targets = detect_targets(tmp_path)
    assert "copilot" in targets


def test_detect_cursor_when_dot_cursor_present(tmp_path: Path) -> None:
    (tmp_path / ".cursor").mkdir()
    with patch("mkdocs_to_confluence.skill_installer._hermes_dir", return_value=tmp_path / "nonexistent"):
        targets = detect_targets(tmp_path)
    assert "cursor" in targets


def test_detect_hermes_when_hermes_dir_exists(tmp_path: Path) -> None:
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    with patch("mkdocs_to_confluence.skill_installer._hermes_dir", return_value=hermes):
        targets = detect_targets(tmp_path)
    assert "hermes" in targets


def test_detect_multiple_tools_at_once(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    with patch("mkdocs_to_confluence.skill_installer._hermes_dir", return_value=hermes):
        targets = detect_targets(tmp_path)
    assert "claude" in targets
    assert "cursor" in targets
    assert "hermes" in targets


def test_install_claude_writes_commands_file(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    install_skill("claude", tmp_path)
    dest = tmp_path / ".claude" / "commands" / "changelog.md"
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "CHANGELOG.md" in content
    assert "---\n" not in content  # frontmatter stripped


def test_install_superpowers_writes_skill_md(tmp_path: Path) -> None:
    (tmp_path / ".github" / "skills").mkdir(parents=True)
    install_skill("superpowers", tmp_path)
    dest = tmp_path / ".github" / "skills" / "tooling" / "mkdocs-changelog" / "SKILL.md"
    assert dest.exists()
    assert "mkdocs-changelog" in dest.read_text(encoding="utf-8")


def test_install_copilot_writes_instructions_file(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text("", encoding="utf-8")
    install_skill("copilot", tmp_path)
    dest = tmp_path / ".github" / "instructions" / "mk2conf-changelog.instructions.md"
    assert dest.exists()


def test_install_cursor_writes_rule_file(tmp_path: Path) -> None:
    (tmp_path / ".cursor").mkdir()
    install_skill("cursor", tmp_path)
    dest = tmp_path / ".cursor" / "rules" / "mk2conf-changelog.mdc"
    assert dest.exists()


def test_install_hermes_writes_to_hermes_dir(tmp_path: Path) -> None:
    hermes = tmp_path / ".hermes"
    (hermes / "skills" / "tooling").mkdir(parents=True)
    install_skill("hermes", tmp_path, hermes_dir=hermes)
    dest = hermes / "skills" / "tooling" / "mkdocs-changelog" / "SKILL.md"
    assert dest.exists()


def test_install_fallback_writes_to_mk2conf_dir(tmp_path: Path) -> None:
    install_skill("fallback", tmp_path)
    dest = tmp_path / ".mk2conf" / "changelog-skill.md"
    assert dest.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_skill_installer.py -v
```
Expected: FAIL — `skill_installer.py` does not exist.

- [ ] **Step 3: Create `skill_installer.py`**

```python
# src/mkdocs_to_confluence/skill_installer.py
"""Detect AI tools in a project and install the mkdocs-changelog skill."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from importlib.resources import files as _res_files


def _hermes_dir() -> Path:
    return Path.home() / ".hermes"


def _load_skill_content() -> str:
    return _res_files("mkdocs_to_confluence").joinpath(
        "skills/mkdocs-changelog/SKILL.md"
    ).read_text(encoding="utf-8")


def _strip_frontmatter(content: str) -> str:
    """Remove the YAML frontmatter block (--- ... ---) from skill content."""
    stripped = re.sub(r"\A---\s*\n.*?\n---\s*\n?", "", content, flags=re.DOTALL)
    return stripped.lstrip("\n")


def detect_targets(project_root: Path) -> list[str]:
    """Return all AI tool target names detected in the given project root."""
    targets: list[str] = []
    if _hermes_dir().is_dir():
        targets.append("hermes")
    if (project_root / ".github" / "skills").is_dir():
        targets.append("superpowers")
    if (project_root / ".claude").is_dir():
        targets.append("claude")
    if (project_root / ".github" / "copilot-instructions.md").is_file():
        targets.append("copilot")
    if (project_root / ".cursor").is_dir():
        targets.append("cursor")
    return targets


def install_skill(
    target: str,
    project_root: Path,
    *,
    hermes_dir: Path | None = None,
) -> Path:
    """Install the mkdocs-changelog skill for the given target.

    Returns the path where the skill was written.
    """
    content = _load_skill_content()
    dest: Path

    if target == "hermes":
        hd = hermes_dir or _hermes_dir()
        dest = hd / "skills" / "tooling" / "mkdocs-changelog" / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    elif target == "superpowers":
        dest = project_root / ".github" / "skills" / "tooling" / "mkdocs-changelog" / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    elif target == "claude":
        dest = project_root / ".claude" / "commands" / "changelog.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_strip_frontmatter(content), encoding="utf-8")

    elif target == "copilot":
        dest = project_root / ".github" / "instructions" / "mk2conf-changelog.instructions.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        header = "---\napplyTo: '**'\n---\n\n"
        dest.write_text(header + _strip_frontmatter(content), encoding="utf-8")

    elif target == "cursor":
        dest = project_root / ".cursor" / "rules" / "mk2conf-changelog.mdc"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    else:  # fallback
        dest = project_root / ".mk2conf" / "changelog-skill.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    return dest


def run_install(project_root: Path, tool: str | None = None, *, quiet: bool = False) -> None:
    """Detect all AI tools and install the skill into each one."""
    if tool is not None:
        targets = [tool]
    else:
        targets = detect_targets(project_root)

    if not targets:
        dest = install_skill("fallback", project_root)
        print(f"No AI tools detected. Skill written to: {dest}")
        print(
            "Reference it from your AI tool's instructions or copy it to the appropriate location."
        )
        return

    for t in targets:
        try:
            dest = install_skill(t, project_root)
            if not quiet:
                print(f"  [{t}]  →  {dest}")
        except Exception as exc:
            print(f"  [{t}]  ✗  {exc}", file=sys.stderr)
```

- [ ] **Step 4: Add `install-skill` subcommand to `cli.py`**

In `_build_parser()` in `src/mkdocs_to_confluence/cli.py`, add after the `sync-comments` parser block (before `return parser`):

```python
    # --- install-skill ---
    is_parser = sub.add_parser(
        "install-skill",
        help="Install the mkdocs-changelog AI skill into detected AI tools.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Detected tools: Hermes (~/.hermes/), superpowers (.github/skills/),\n"
            "  Claude Code (.claude/), Copilot (.github/copilot-instructions.md),\n"
            "  Cursor (.cursor/)\n"
            "\n"
            "Examples:\n"
            "  mk2conf install-skill                    # install into all detected tools\n"
            "  mk2conf install-skill --tool claude      # install for Claude Code only\n"
        ),
    )
    is_parser.add_argument(
        "--tool",
        metavar="TOOL",
        default=None,
        choices=["hermes", "superpowers", "claude", "copilot", "cursor"],
        help="Install for a specific tool only (default: all detected tools).",
    )
    is_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress output.",
    )
```

In `main()` in `cli.py`, add a branch in the `if args.command` block:

```python
        elif args.command == "install-skill":
            _cmd_install_skill(args)
```

Add the handler function after `_cmd_sync_comments`:

```python
def _cmd_install_skill(args: argparse.Namespace) -> None:
    from mkdocs_to_confluence.skill_installer import run_install
    run_install(
        Path(".").resolve(),
        tool=getattr(args, "tool", None),
        quiet=getattr(args, "quiet", False),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_skill_installer.py -v
```
Expected: All tests PASS.

- [ ] **Step 6: Smoke-test the CLI**

```bash
uv run mk2conf install-skill --help
```
Expected: Help text listing `--tool` and the supported tools.

- [ ] **Step 7: Run the full suite**

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```
Expected: All pass.

- [ ] **Step 8: Update README — add `install-skill` to Quick start**

Add to the Quick start section in `README.md`:

```markdown
# Install the changelog AI skill into your AI tool(s)
mk2conf install-skill
```

And add a new section to `docs/commands.md` documenting `install-skill`:

````markdown
## `mk2conf install-skill`

Install the `mkdocs-changelog` AI skill into all detected AI tools in the current project.

```
mk2conf install-skill [--tool TOOL] [--quiet]
```

| Flag | Default | Description |
|---|---|---|
| `--tool TOOL` | *(all detected)* | Install for a specific tool only. Supported: `hermes`, `superpowers`, `claude`, `copilot`, `cursor`. |
| `--quiet` | off | Suppress per-tool output. |

**Detected tools and install locations:**

| Tool | Detection marker | Installed to |
|---|---|---|
| Hermes | `~/.hermes/` | `~/.hermes/skills/tooling/mkdocs-changelog/SKILL.md` |
| Superpowers | `.github/skills/` | `.github/skills/tooling/mkdocs-changelog/SKILL.md` |
| Claude Code | `.claude/` | `.claude/commands/changelog.md` |
| GitHub Copilot | `.github/copilot-instructions.md` | `.github/instructions/mk2conf-changelog.instructions.md` |
| Cursor | `.cursor/` | `.cursor/rules/mk2conf-changelog.mdc` |
| *(none found)* | — | `.mk2conf/changelog-skill.md` + printed guidance |

All detected tools are installed in one run. Run after `pip install mkdocs2confluence` to set up the AI-assisted changelog workflow.
````

- [ ] **Step 9: Final full suite run**

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run vulture src --min-confidence 80
```
Expected: All pass, no unused code flagged.

- [ ] **Step 10: Commit**

```bash
git add \
  src/mkdocs_to_confluence/skill_installer.py \
  src/mkdocs_to_confluence/cli.py \
  tests/test_skill_installer.py \
  README.md \
  docs/commands.md
git commit -m "feat: add install-skill command with multi-tool AI skill installer"
```
