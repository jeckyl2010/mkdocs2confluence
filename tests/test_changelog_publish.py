"""Unit tests for publisher/changelog.py."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
from mkdocs_to_confluence.publisher.changelog import publish_changelog


def _conf(changelog: str | None = "CHANGELOG.md") -> ConfluenceConfig:
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
    conf = _conf(changelog=None)
    config = _config(tmp_path)
    client = _make_client()
    publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)
    client.find_page.assert_not_called()


def test_publish_changelog_warns_when_file_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "docs").mkdir()
    conf = _conf()
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
    conf = _conf()
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("compiled-xhtml", [], (), None, None)
        expected_hash = hashlib.sha256(b"compiled-xhtml").hexdigest()
        client = _make_client(existing_id="42", stored_hash=expected_hash)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    client.create_page.assert_not_called()
    client.update_page.assert_not_called()


def test_publish_changelog_creates_new_page(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nNew content.\n", encoding="utf-8")
    conf = _conf()
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml-new", [], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    client.create_page.assert_called_once()
    call_kwargs = client.create_page.call_args
    assert call_kwargs.kwargs.get("parent_id") is None  # no parent_page_id set
    client.stamp_managed.assert_not_called()  # must never be stamped — prune must not touch it


def test_publish_changelog_updates_existing_page(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nUpdated.\n", encoding="utf-8")
    conf = _conf()
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml-updated", [], (), None, None)
        client = _make_client(existing_id="77", stored_hash="old-hash")
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    client.update_page.assert_called_once()
    args = client.update_page.call_args
    assert args.args[0] == "77"   # page_id
    assert args.args[3] == 4      # version + 1
    client.stamp_managed.assert_not_called()  # must never be stamped — prune must not touch it


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
    conf = _conf()
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
    conf = _conf()
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml", [], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    call_kwargs = client.create_page.call_args
    assert call_kwargs.args[1] == "What's New"


def test_publish_changelog_uploads_attachments(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nContent.\n", encoding="utf-8")
    attachment = docs / "img.png"
    attachment.write_bytes(b"\x89PNG")
    conf = _conf()
    config = _config(tmp_path)

    with (
        patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile,
        patch("mkdocs_to_confluence.publisher.changelog._upload_assets") as mock_upload,
    ):
        mock_compile.return_value = ("xhtml", [attachment], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    mock_upload.assert_called_once_with("999", [attachment], docs, client, quiet=True)
