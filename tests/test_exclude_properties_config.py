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
