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
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "CHANGELOG.md").write_text("# Log\n", encoding="utf-8")
    cfg = load_config(_write_mkdocs(tmp_path, _BASE + "  changelog: CHANGELOG.md\n"))
    assert cfg.confluence is not None
    assert cfg.confluence.changelog_file == "CHANGELOG.md"


def test_changelog_path_escaping_docs_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="escapes docs_dir"):
        load_config(_write_mkdocs(tmp_path, _BASE + "  changelog: ../secret.md\n"))
