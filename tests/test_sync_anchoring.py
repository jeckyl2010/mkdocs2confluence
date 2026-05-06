"""Tests for sync/anchoring.py — find_anchor_line."""

from __future__ import annotations

from pathlib import Path

from mkdocs_to_confluence.sync.anchoring import find_anchor_line


def test_finds_exact_match(tmp_path: Path) -> None:
    f = tmp_path / "page.md"
    f.write_text("# Title\n\nSome prose here.\n\nAnother paragraph.\n", encoding="utf-8")
    assert find_anchor_line(f, "Some prose here.") == 3


def test_finds_partial_match(tmp_path: Path) -> None:
    f = tmp_path / "page.md"
    f.write_text("Line one\nThe deployment procedure for production environments\nLine three\n")
    assert find_anchor_line(f, "deployment procedure") == 2


def test_returns_first_match_when_ambiguous(tmp_path: Path) -> None:
    f = tmp_path / "page.md"
    f.write_text("same text\nother stuff\nsame text\n")
    assert find_anchor_line(f, "same text") == 1


def test_returns_none_when_not_found(tmp_path: Path) -> None:
    f = tmp_path / "page.md"
    f.write_text("Hello world\n")
    assert find_anchor_line(f, "this is not in the file") is None


def test_returns_none_for_empty_selection(tmp_path: Path) -> None:
    f = tmp_path / "page.md"
    f.write_text("Hello world\n")
    assert find_anchor_line(f, "") is None


def test_returns_none_for_missing_file(tmp_path: Path) -> None:
    f = tmp_path / "nonexistent.md"
    assert find_anchor_line(f, "anything") is None


def test_finds_match_in_admonition(tmp_path: Path) -> None:
    content = "# Heading\n\n!!! warning\n    This is outdated — we switched to ArgoCD.\n\nParagraph.\n"
    f = tmp_path / "page.md"
    f.write_text(content)
    assert find_anchor_line(f, "we switched to ArgoCD") == 4


def test_finds_match_in_table_cell(tmp_path: Path) -> None:
    content = "| Name | Value |\n|------|-------|\n| production | high-risk |\n"
    f = tmp_path / "page.md"
    f.write_text(content)
    assert find_anchor_line(f, "high-risk") == 3
