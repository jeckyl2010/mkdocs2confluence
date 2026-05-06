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
            "pr_title": "Overview",
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
            "pr_title": "Overview",
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
            "pr_title": "Overview",
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


# ── verbose output paths (quiet=False) ───────────────────────────────────────


def test_run_sync_verbose_skip_message(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md")

    existing = {
        "10": {
            "page_id": "111",
            "pr_title": "Overview",
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

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=MagicMock(),
        review_client=MagicMock(),
        force=False,
        dry_run=False,
        quiet=False,
    )

    out = capsys.readouterr().out
    assert "[skip]" in out


def test_run_sync_verbose_pr_line_and_summary(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md", "# Title\n\nSome text here.\n")

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = [
        {
            "id": "c1",
            "version": {"authorId": "alice", "createdAt": "2026-05-01T00:00:00Z"},
            "body": {"storage": {"value": "<p>Fix this.</p>"}},
            "properties": {"inlineOriginalSelection": "Some text"},
            "_links": {"webui": "/wiki/spaces/X/pages/111?focusedCommentId=c1"},
        }
    ]
    confluence_client.get_page_footer_comments.return_value = []

    review_client = MagicMock()
    review_client.create_pull_request.return_value = (5, "PR_kwTEST")

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        force=False,
        dry_run=False,
        quiet=False,
    )

    out = capsys.readouterr().out
    assert "[sync]" in out
    assert "PR #5" in out
    assert "Created 1 review PR" in out


def test_run_sync_verbose_no_new_comments(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md")

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = []
    confluence_client.get_page_footer_comments.return_value = []

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=MagicMock(),
        force=False,
        dry_run=False,
        quiet=False,
    )

    out = capsys.readouterr().out
    assert "No new comments" in out


def test_run_sync_verbose_base_url_wiki_stripped(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md")

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net/wiki"

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = []
    confluence_client.get_page_footer_comments.return_value = []

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=MagicMock(),
        force=False,
        dry_run=False,
        quiet=True,
    )


def test_run_sync_footer_comment_tracked_separately(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md", "# Title\n\nBody.\n")

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = []
    confluence_client.get_page_footer_comments.return_value = [
        {
            "id": "f1",
            "version": {"authorId": "bob", "createdAt": "2026-05-01T00:00:00Z"},
            "body": {"storage": {"value": "<p>Page-level comment.</p>"}},
            "properties": {},
            "_links": {"webui": "/wiki/spaces/X/pages/111?focusedCommentId=f1"},
        }
    ]

    review_client = MagicMock()
    review_client.create_pull_request.return_value = (20, "PR_kwFOOT")

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        force=False,
        dry_run=False,
        quiet=True,
    )

    state = SyncState.load(tmp_path / ".mk2conf-sync-state.json")
    rec = state.prs["20"]
    assert rec.footer_comment_ids == ["f1"]
    assert rec.inline_comment_ids == []


def test_run_sync_post_comment_failure_warns(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from mkdocs_to_confluence.sync.command import run_sync_comments

    _make_page_map(tmp_path, {"docs/overview.md": "111"})
    _make_source_file(tmp_path, "docs/overview.md", "# Title\n\nSome text.\n")

    config = MagicMock()
    config.confluence.github_base_branch = "main"
    config.confluence.base_url = "https://example.atlassian.net"

    confluence_client = MagicMock()
    confluence_client.get_page_inline_comments.return_value = [
        {
            "id": "c1",
            "version": {"authorId": "alice", "createdAt": "2026-05-01T00:00:00Z"},
            "body": {"storage": {"value": "<p>Comment.</p>"}},
            "properties": {"inlineOriginalSelection": "Some text"},
            "_links": {"webui": "/wiki/spaces/X/pages/111?focusedCommentId=c1"},
        }
    ]
    confluence_client.get_page_footer_comments.return_value = []

    review_client = MagicMock()
    review_client.create_pull_request.return_value = (99, "PR_kwFAIL")
    review_client.post_review_comment.side_effect = RuntimeError("network error")

    run_sync_comments(
        config=config,
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        force=False,
        dry_run=False,
        quiet=True,
    )

    state = SyncState.load(tmp_path / ".mk2conf-sync-state.json")
    assert "99" in state.prs
    out = capsys.readouterr().out
    assert "[warn]" in out


def test_check_merges_verbose_output(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges

    existing = {
        "5": {
            "page_id": "AAA",
            "pr_title": "Overview",
            "source_path": "docs/overview.md",
            "branch": "mk2conf/review/overview",
            "pr_number": 5,
            "pr_node_id": "PR_kwXX",
            "merged": False,
            "inline_comment_ids": ["c1"],
            "footer_comment_ids": [],
        }
    }
    _make_state(tmp_path, existing)

    review_client = MagicMock()
    review_client.get_pr_merge_info.return_value = (True, "abc1234")
    confluence_client = MagicMock()

    check_and_resolve_merges(
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        quiet=False,
    )

    out = capsys.readouterr().out
    assert "[merged]" in out
    assert "Resolved 1 PR" in out


def test_check_merges_verbose_no_merges(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges

    existing = {
        "5": {
            "page_id": "AAA",
            "pr_title": "Overview",
            "source_path": "docs/overview.md",
            "branch": "mk2conf/review/overview",
            "pr_number": 5,
            "pr_node_id": "PR_kwXX",
            "merged": False,
            "inline_comment_ids": [],
            "footer_comment_ids": [],
        }
    }
    _make_state(tmp_path, existing)

    review_client = MagicMock()
    review_client.get_pr_merge_info.return_value = (False, None)

    check_and_resolve_merges(
        config_dir=tmp_path,
        confluence_client=MagicMock(),
        review_client=review_client,
        quiet=False,
    )

    out = capsys.readouterr().out
    assert "No merged PRs" in out


def test_check_merges_resolve_failure_warns(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges

    existing = {
        "6": {
            "page_id": "BBB",
            "pr_title": "Guide",
            "source_path": "docs/guide.md",
            "branch": "mk2conf/review/guide",
            "pr_number": 6,
            "pr_node_id": "PR_kwGG",
            "merged": False,
            "inline_comment_ids": ["c1"],
            "footer_comment_ids": ["f1"],
        }
    }
    _make_state(tmp_path, existing)

    review_client = MagicMock()
    review_client.get_pr_merge_info.return_value = (True, "deadbeef")
    confluence_client = MagicMock()
    confluence_client.resolve_inline_comment.side_effect = RuntimeError("API down")
    confluence_client.resolve_footer_comment.side_effect = RuntimeError("API down")

    check_and_resolve_merges(
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        quiet=True,
    )

    out = capsys.readouterr().out
    assert out.count("[warn]") == 2


def test_check_merges_no_commit_sha(tmp_path: Path) -> None:
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges

    existing = {
        "7": {
            "page_id": "CCC",
            "pr_title": "Ops",
            "source_path": "docs/ops.md",
            "branch": "mk2conf/review/ops",
            "pr_number": 7,
            "pr_node_id": "PR_kwOP",
            "merged": False,
            "inline_comment_ids": ["c1"],
            "footer_comment_ids": [],
        }
    }
    _make_state(tmp_path, existing)

    review_client = MagicMock()
    review_client.get_pr_merge_info.return_value = (True, None)
    confluence_client = MagicMock()

    check_and_resolve_merges(
        config_dir=tmp_path,
        confluence_client=confluence_client,
        review_client=review_client,
        quiet=True,
    )

    reply_arg = confluence_client.add_comment_reply.call_args.args[1]
    assert "PR #7" in reply_arg
    assert "None" not in reply_arg
