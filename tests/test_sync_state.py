"""Tests for sync/state.py — SyncState / PRRecord round-trip and helpers."""

from __future__ import annotations

from pathlib import Path

from mkdocs_to_confluence.sync.state import PRRecord, SyncState


def _make_record(**kwargs: object) -> PRRecord:
    defaults: dict = {
        "page_id": "111",
        "pr_title": "My Page",
        "source_path": "docs/my-page.md",
        "branch": "mk2conf/review/my-page",
        "pr_number": 42,
        "pr_node_id": "PR_kwXXX",
        "merged": False,
        "inline_comment_ids": ["c1", "c2"],
        "footer_comment_ids": ["f1"],
    }
    defaults.update(kwargs)
    return PRRecord(**defaults)  # type: ignore[arg-type]


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    state_file = tmp_path / ".mk2conf-sync-state.json"
    state = SyncState()
    state.prs["42"] = _make_record()
    state.save(state_file)

    loaded = SyncState.load(state_file)
    assert "42" in loaded.prs
    rec = loaded.prs["42"]
    assert rec.page_id == "111"
    assert rec.source_path == "docs/my-page.md"
    assert rec.inline_comment_ids == ["c1", "c2"]
    assert rec.footer_comment_ids == ["f1"]
    assert rec.merged is False
    assert rec.pr_node_id == "PR_kwXXX"


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    state_file = tmp_path / "nonexistent.json"
    state = SyncState.load(state_file)
    assert state.prs == {}


def test_has_open_pr_for_returns_true(tmp_path: Path) -> None:
    state = SyncState()
    state.prs["7"] = _make_record(page_id="AAA", merged=False)
    assert state.has_open_pr_for("AAA") is True


def test_has_open_pr_for_merged_returns_false(tmp_path: Path) -> None:
    state = SyncState()
    state.prs["7"] = _make_record(page_id="AAA", merged=True)
    assert state.has_open_pr_for("AAA") is False


def test_has_open_pr_for_unknown_page(tmp_path: Path) -> None:
    state = SyncState()
    assert state.has_open_pr_for("UNKNOWN") is False


def test_multiple_records_survive_round_trip(tmp_path: Path) -> None:
    state_file = tmp_path / ".mk2conf-sync-state.json"
    state = SyncState()
    state.prs["1"] = _make_record(page_id="P1", pr_number=1)
    state.prs["2"] = _make_record(page_id="P2", pr_number=2, merged=True)
    state.save(state_file)

    loaded = SyncState.load(state_file)
    assert len(loaded.prs) == 2
    assert loaded.prs["2"].merged is True
