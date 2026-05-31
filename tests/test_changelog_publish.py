"""Unit tests for publisher/changelog.py."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
from mkdocs_to_confluence.publisher.changelog import _extract_title, publish_changelog


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


def test_publish_changelog_update_path_applies_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Update path with labels + full_width + status; verifies every post-publish
    metadata call fires and the non-quiet progress lines print."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nUpdated.\n", encoding="utf-8")
    conf = _conf()  # full_width defaults to True
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml-updated", [], ("release-notes",), "current", "v1.2.3")
        client = _make_client(existing_id="77", stored_hash="old-hash")
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=False)

    client.update_page.assert_called_once()
    assert client.update_page.call_args.kwargs.get("version_message") == "v1.2.3"
    client.set_content_hash.assert_called_once_with("77", client.set_content_hash.call_args.args[1])
    client.set_page_labels.assert_called_once_with("77", ("release-notes",))
    client.set_page_full_width.assert_called_once_with("77")
    client.set_page_status.assert_called_once_with("77", "current", space_key="TECH")

    out = capsys.readouterr().out
    assert "compiling" in out
    assert "updated" in out


def test_publish_changelog_created_prints_when_not_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nNew.\n", encoding="utf-8")
    conf = _conf()
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml-new", [], (), None, None)
        client = _make_client(existing_id=None)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=False)

    assert "created" in capsys.readouterr().out


def test_publish_changelog_unchanged_prints_when_not_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nSame.\n", encoding="utf-8")
    conf = _conf()
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("compiled-xhtml", [], (), None, None)
        expected_hash = hashlib.sha256(b"compiled-xhtml").hexdigest()
        client = _make_client(existing_id="42", stored_hash=expected_hash)
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=False)

    assert "unchanged" in capsys.readouterr().out


def test_publish_changelog_swallows_metadata_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Best-effort post-publish steps must never propagate; the page is already
    saved. content_hash failure stays silent (self-healing); labels/full_width/
    status failures warn so they aren't invisible."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text("## 2026-05-25\n\nContent.\n", encoding="utf-8")
    conf = _conf()  # full_width defaults to True
    config = _config(tmp_path)

    with patch("mkdocs_to_confluence.publisher.changelog.compile_page") as mock_compile:
        mock_compile.return_value = ("xhtml", [], ("lbl",), "current", None)
        client = _make_client(existing_id=None)
        client.set_content_hash.side_effect = RuntimeError("hash boom")
        client.set_page_labels.side_effect = RuntimeError("labels boom")
        client.set_page_full_width.side_effect = RuntimeError("width boom")
        client.set_page_status.side_effect = RuntimeError("status boom")

        # Must not raise despite every metadata call failing.
        publish_changelog(config, conf, client, "space-1", space_key="TECH", quiet=True)

    client.create_page.assert_called_once()

    err = capsys.readouterr().err
    assert "could not set labels" in err
    assert "could not set full-width" in err
    assert "could not set page status" in err
    # content_hash failure is self-healing and must stay silent.
    assert "hash boom" not in err


def test_extract_title_returns_none_on_unreadable_file(tmp_path: Path) -> None:
    assert _extract_title(tmp_path / "does-not-exist.md") is None


def test_extract_title_returns_none_on_malformed_yaml(tmp_path: Path) -> None:
    p = tmp_path / "c.md"
    p.write_text("---\nfoo: [unclosed\n---\n\nbody\n", encoding="utf-8")
    assert _extract_title(p) is None


def test_extract_title_returns_none_when_front_matter_not_mapping(tmp_path: Path) -> None:
    p = tmp_path / "c.md"
    p.write_text("---\njust a scalar\n---\n\nbody\n", encoding="utf-8")
    assert _extract_title(p) is None
