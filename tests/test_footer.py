"""Tests for transforms/footer.py and the SourceFooter emitter."""

from __future__ import annotations

from unittest.mock import patch

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import SourceFooter
from mkdocs_to_confluence.transforms.footer import (
    _derive_commit_url,
    _derive_history_url,
    _last_commit_info,
    build_source_footer,
)

# ── _derive_history_url ───────────────────────────────────────────────────────


def test_derive_history_url_github():
    url = "https://github.com/org/repo/edit/main/docs/guide/setup.md"
    assert _derive_history_url(url) == "https://github.com/org/repo/commits/main/docs/guide/setup.md"


def test_derive_history_url_gitlab():
    url = "https://gitlab.com/org/repo/-/edit/main/docs/guide/setup.md"
    assert _derive_history_url(url) == "https://gitlab.com/org/repo/-/commits/main/docs/guide/setup.md"


def test_derive_history_url_unknown_returns_none():
    url = "https://bitbucket.org/org/repo/src/main/docs/guide/setup.md"
    assert _derive_history_url(url) is None


def test_derive_history_url_empty_string():
    assert _derive_history_url("") is None


# ── _derive_commit_url ────────────────────────────────────────────────────────


def test_derive_commit_url_github():
    url = "https://github.com/org/repo/edit/main/docs/page.md"
    assert _derive_commit_url(url, "abc1234") == "https://github.com/org/repo/commit/abc1234"


def test_derive_commit_url_gitlab():
    url = "https://gitlab.com/org/repo/-/edit/main/docs/page.md"
    assert _derive_commit_url(url, "abc1234") == "https://gitlab.com/org/repo/-/commit/abc1234"


def test_derive_commit_url_unknown_returns_none():
    url = "https://bitbucket.org/org/repo/src/main/docs/page.md"
    assert _derive_commit_url(url, "abc1234") is None


# ── _last_commit_info ─────────────────────────────────────────────────────────


def test_last_commit_info_returns_sha_and_summary(tmp_path):
    fake_file = str(tmp_path / "docs" / "page.md")
    sep = "\x1f"
    with patch("mkdocs_to_confluence.transforms.footer.subprocess.run") as mock_run:
        mock_run.return_value.stdout = f"abc1234{sep}Fix typo{sep}Jane{sep}2 days ago\n"
        result = _last_commit_info(fake_file)
    assert result is not None
    sha, summary = result
    assert sha == "abc1234"
    assert "Fix typo" in summary
    assert "Jane" in summary
    assert "2 days ago" in summary


def test_last_commit_info_returns_none_when_empty(tmp_path):
    fake_file = str(tmp_path / "docs" / "untracked.md")
    with patch("mkdocs_to_confluence.transforms.footer.subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        result = _last_commit_info(fake_file)
    assert result is None


def test_last_commit_info_returns_none_on_exception(tmp_path):
    fake_file = str(tmp_path / "docs" / "page.md")
    with patch("mkdocs_to_confluence.transforms.footer.subprocess.run", side_effect=FileNotFoundError):
        result = _last_commit_info(fake_file)
    assert result is None


# ── build_source_footer ───────────────────────────────────────────────────────


def test_build_source_footer_full(tmp_path):
    edit_url = "https://github.com/org/repo/edit/main/docs/guide.md"
    abs_path = str(tmp_path / "docs" / "guide.md")
    with patch("mkdocs_to_confluence.transforms.footer._last_commit_info",
               return_value=("abc1234", "Fix typo · Jane · 1 day ago")):
        footer = build_source_footer(edit_url, abs_path)
    assert footer.edit_url == edit_url
    assert footer.history_url == "https://github.com/org/repo/commits/main/docs/guide.md"
    assert footer.commit_sha == "abc1234"
    assert footer.commit_url == "https://github.com/org/repo/commit/abc1234"
    assert footer.commit_summary == "Fix typo · Jane · 1 day ago"


def test_build_source_footer_no_commit(tmp_path):
    edit_url = "https://github.com/org/repo/edit/main/docs/guide.md"
    abs_path = str(tmp_path / "docs" / "guide.md")
    with patch("mkdocs_to_confluence.transforms.footer._last_commit_info", return_value=None):
        footer = build_source_footer(edit_url, abs_path)
    assert footer.commit_sha is None
    assert footer.commit_url is None
    assert footer.commit_summary is None
    assert footer.history_url is not None


# ── _emit_source_footer ───────────────────────────────────────────────────────


def test_emit_footer_contains_edit_link():
    footer = SourceFooter(
        edit_url="https://github.com/org/repo/edit/main/docs/page.md",
        history_url="https://github.com/org/repo/commits/main/docs/page.md",
        commit_sha="abc1234",
        commit_url="https://github.com/org/repo/commit/abc1234",
        commit_summary="Fix typo · Jane · 2 days ago",
    )
    out = emit((footer,))
    assert "Edit this page" in out
    assert "View history" in out
    assert "abc1234" in out
    assert "Fix typo" in out
    assert 'ac:name="panel"' in out


def test_emit_footer_sha_is_hyperlink():
    footer = SourceFooter(
        edit_url="https://github.com/org/repo/edit/main/docs/page.md",
        history_url=None,
        commit_sha="abc1234",
        commit_url="https://github.com/org/repo/commit/abc1234",
        commit_summary="Fix typo · Jane · today",
    )
    out = emit((footer,))
    assert 'href="https://github.com/org/repo/commit/abc1234"' in out
    assert ">abc1234<" in out


def test_emit_footer_last_commit_bold():
    footer = SourceFooter(
        edit_url="https://github.com/org/repo/edit/main/docs/page.md",
        history_url=None,
        commit_sha="abc1234",
        commit_url="https://github.com/org/repo/commit/abc1234",
        commit_summary="Fix typo · Jane · today",
    )
    out = emit((footer,))
    assert "<strong>Last commit:</strong>" in out


def test_emit_footer_no_panel_title():
    footer = SourceFooter(
        edit_url="https://github.com/org/repo/edit/main/docs/page.md",
    )
    out = emit((footer,))
    assert 'ac:name="title"' not in out


def test_emit_footer_no_history_url():
    footer = SourceFooter(
        edit_url="https://example.com/edit/docs/page.md",
        history_url=None,
        commit_sha=None,
        commit_url=None,
        commit_summary=None,
    )
    out = emit((footer,))
    assert "Edit this page" in out
    assert "View history" not in out
    assert "Last commit" not in out


def test_emit_footer_escapes_html():
    footer = SourceFooter(
        edit_url='https://example.com/edit/path?a=1&b=2',
        history_url=None,
        commit_sha=None,
        commit_url=None,
        commit_summary='<script>alert(1)</script> · Jane · today',
    )
    out = emit((footer,))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "a=1&amp;b=2" in out


def test_emit_footer_non_ascii_encoded_as_entity():
    """Non-ASCII characters in commit_summary are encoded as XML numeric entities."""
    footer = SourceFooter(
        edit_url="https://github.com/org/repo/edit/main/docs/page.md",
        history_url=None,
        commit_sha=None,
        commit_url=None,
        commit_summary="Fix caf\u00e9 · \u00c5ngstr\u00f6m · 2 days ago",
    )
    out = emit((footer,))
    assert "caf\u00e9" not in out
    assert "&#233;" in out or "&#xe9;" in out.lower()


def test_emit_footer_separator_is_entity():
    """The · separator between Edit/View history links is an XML entity, not raw UTF-8."""
    footer = SourceFooter(
        edit_url="https://github.com/org/repo/edit/main/docs/page.md",
        history_url="https://github.com/org/repo/commits/main/docs/page.md",
    )
    out = emit((footer,))
    assert "&#xB7;" in out
    assert "\u00b7" not in out
