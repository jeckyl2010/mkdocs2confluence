"""Tests for sync/command.py — run_sync_comments and check_and_resolve_merges."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mkdocs_to_confluence.sync.state import SyncState


def _make_state(tmp_path: Path, prs: dict | None = None) -> Path:
    state_file = tmp_path / ".mk2conf-sync-state.json"
    if prs is not None:
        state_file.write_text(json.dumps({"prs": prs}), encoding="utf-8")
    return state_file


def _make_page_map(tmp_path: Path, mapping: dict) -> Path:
    page_map = tmp_path / ".mk2conf-pages.json"
    page_map.write_text(json.dumps(mapping), encoding="utf-8")
    return page_map


def _make_source_file(tmp_path: Path, rel: str, content: str = "# Title\n\nSome text.\n") -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── run_sync_comments ─────────────────────────────────────────────────────────


def test_run_sync_comments_creates_branch_and_pr(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md", "# Overview\n\nThis is outdated.\n")

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = [
        {
            "id": "c1",
            "version": {"authorId": "alice", "createdAt": "2026-05-01T00:00:00Z"},
            "body": {"storage": {"value": "<p>Needs updating.</p>"}},
            "properties": {"inlineOriginalSelection": "This is outdated"},
            "_links": {"webui": "/wiki/spaces/X/pages/111?focusedCommentId=c1"},
        }
    ]
    confluence_client.get_page_footer_comments.return_value = []

    review_client = MagicMock()
    review_client.create_pull_request.return_value = (10, "PR_kwTEST")

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        force=False,
        dry_run=False,
        quiet=True,
    )

    review_client.create_review_branch.assert_called_once()
    review_client.create_pull_request.assert_called_once()
    review_client.post_review_comment.assert_called_once()

    state_file = tmp_path / ".mk2conf-sync-state.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert "10" in data["prs"] or 10 in data["prs"]


def test_run_sync_comments_skips_page_with_open_pr(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md")

    existing = {
        "10": {
            "page_id": "111",
            "page_title": "Overview",
            "source_path": "docs/overview.md",
            "branch": "mk2conf/review/overview",
            "pr_number": 10,
            "pr_node_id": "PR_kwXX",
            "merged": False,
            "inline_comment_ids": [],
            "footer_comment_ids": [],
        }
    }
    _make_state(tmp_path, existing)

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = [
        {
            "id": "c1",
            "version": {"authorId": "alice", "createdAt": "2026-05-01T00:00:00Z"},
            "body": {"storage": {"value": "<p>Comment.</p>"}},
            "properties": {"inlineOriginalSelection": "some text"},
            "_links": {"webui": "/wiki/spaces/X/pages/111?focusedCommentId=c1"},
        }
    ]
    confluence_client.get_page_footer_comments.return_value = []

    review_client = MagicMock()

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        force=False,
        dry_run=False,
        quiet=True,
    )

    review_client.create_review_branch.assert_not_called()


def test_run_sync_comments_dry_run_makes_no_api_calls(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md", "# Title\n\nSome content here.\n")

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = [
        {
            "id": "c1",
            "version": {"authorId": "alice", "createdAt": "2026-05-01T00:00:00Z"},
            "body": {"storage": {"value": "<p>Comment.</p>"}},
            "properties": {"inlineOriginalSelection": "Some content"},
            "_links": {"webui": "/wiki/spaces/X/pages/111?focusedCommentId=c1"},
        }
    ]
    confluence_client.get_page_footer_comments.return_value = []

    review_client = MagicMock()

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        force=False,
        dry_run=True,
        quiet=True,
    )

    review_client.create_review_branch.assert_not_called()
    review_client.create_pull_request.assert_not_called()
    state_file = tmp_path / ".mk2conf-sync-state.json"
    assert not state_file.exists()


def test_run_sync_comments_raises_when_page_map_missing(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    with pytest.raises(FileNotFoundError):
        run_sync_comments(
            config=config,
            config_dir=tmp_path,
            confluence_client=MagicMock(),
            review_client=MagicMock(),
            force=False,
            dry_run=False,
            quiet=True,
        )


# ── check_and_resolve_merges ──────────────────────────────────────────────────


def test_check_and_resolve_merges_resolves_merged_pr(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges

    existing = {
        "10": {
            "page_id": "111",
            "page_title": "Overview",
            "source_path": "docs/overview.md",
            "branch": "mk2conf/review/overview",
            "pr_number": 10,
            "pr_node_id": "PR_kwXX",
            "merged": False,
            "inline_comment_ids": ["c1"],
            "footer_comment_ids": ["f1"],
        }
    }
    _make_state(tmp_path, existing)

    review_client = MagicMock()
    review_client.get_pr_merge_info.return_value = (True, "abc123")

    confluence_client = MagicMock()
    confluence_client.add_comment_reply.return_value = None
    confluence_client.resolve_inline_comment.return_value = None
    confluence_client.resolve_footer_comment.return_value = None

    check_and_resolve_merges(
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        quiet=True,
    )

    confluence_client.add_comment_reply.assert_called()
    confluence_client.resolve_inline_comment.assert_called_once_with("c1")
    confluence_client.resolve_footer_comment.assert_called_once_with("f1")

    state = SyncState.load(tmp_path / ".mk2conf-sync-state.json")
    assert state.prs["10"].merged is True


def test_check_and_resolve_merges_skips_already_merged(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges

    existing = {
        "10": {
            "page_id": "111",
            "page_title": "Overview",
            "source_path": "docs/overview.md",
            "branch": "mk2conf/review/overview",
            "pr_number": 10,
            "pr_node_id": "PR_kwXX",
            "merged": True,
            "inline_comment_ids": ["c1"],
            "footer_comment_ids": [],
        }
    }
    _make_state(tmp_path, existing)

    review_client = MagicMock()
    confluence_client = MagicMock()

    check_and_resolve_merges(
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        quiet=True,
    )

    review_client.get_pr_merge_info.assert_not_called()
    confluence_client.resolve_inline_comment.assert_not_called()


def test_check_and_resolve_merges_no_state_file(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges

    review_client = MagicMock()
    confluence_client = MagicMock()

    # should not raise
    check_and_resolve_merges(
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        quiet=True,
    )

    review_client.get_pr_merge_info.assert_not_called()
