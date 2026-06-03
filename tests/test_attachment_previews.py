"""Tests for attachment inline previews (config, IR node, transform, emitter)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import ConfigError, load_config


def _write_mkdocs(tmp_path: Path, extra: str = "") -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "mkdocs.yml").write_text(
        f"site_name: Test Site\n{extra}", encoding="utf-8"
    )
    return tmp_path / "mkdocs.yml"


_CONF = (
    "confluence:\n"
    "  base_url: https://x.atlassian.net/wiki\n"
    "  email: a@b.test\n"
    "  space_key: TECH\n"
)


def test_attachment_preview_true(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _CONF + "  attachment_preview: true\n"))
    assert cfg.confluence.attachment_preview is True


def test_attachment_preview_default_false(tmp_path: Path) -> None:
    cfg = load_config(_write_mkdocs(tmp_path, _CONF))
    assert cfg.confluence.attachment_preview is False


def test_attachment_preview_non_bool_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="attachment_preview"):
        load_config(_write_mkdocs(tmp_path, _CONF + "  attachment_preview: maybe\n"))
