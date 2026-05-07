"""Tests for transforms/footer.py and the SourceFooter emitter."""

from __future__ import annotations

from unittest.mock import patch

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import SourceFooter
from mkdocs_to_confluence.transforms.footer import _derive_history_url, _last_commit, build_source_footer

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


# ── _last_commit ──────────────────────────────────────────────────────────────


def test_last_commit_returns_output(tmp_path):
    fake_file = str(tmp_path / "docs" / "page.md")
    with patch("mkdocs_to_confluence.transforms.footer.subprocess.run") as mock_run:
        mock_run.return_value.stdout = "abc1234 · Fix typo · Jane · 2 days ago\n"
        result = _last_commit(fake_file)
    assert result == "abc1234 · Fix typo · Jane · 2 days ago"


def test_last_commit_returns_none_when_empty(tmp_path):
    fake_file = str(tmp_path / "docs" / "untracked.md")
    with patch("mkdocs_to_confluence.transforms.footer.subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        result = _last_commit(fake_file)
    assert result is None


def test_last_commit_returns_none_on_exception(tmp_path):
    fake_file = str(tmp_path / "docs" / "page.md")
    with patch("mkdocs_to_confluence.transforms.footer.subprocess.run", side_effect=FileNotFoundError):
        result = _last_commit(fake_file)
    assert result is None


# ── build_source_footer ───────────────────────────────────────────────────────


def test_build_source_footer_full(tmp_path):
    edit_url = "https://github.com/org/repo/edit/main/docs/guide.md"
    abs_path = str(tmp_path / "docs" / "guide.md")
    with patch("mkdocs_to_confluence.transforms.footer._last_commit", return_value="abc · msg · Jane · 1 day ago"):
        footer = build_source_footer(edit_url, abs_path)
    assert footer.edit_url == edit_url
    assert footer.history_url == "https://github.com/org/repo/commits/main/docs/guide.md"
    assert footer.last_commit == "abc · msg · Jane · 1 day ago"


def test_build_source_footer_no_commit(tmp_path):
    edit_url = "https://github.com/org/repo/edit/main/docs/guide.md"
    abs_path = str(tmp_path / "docs" / "guide.md")
    with patch("mkdocs_to_confluence.transforms.footer._last_commit", return_value=None):
        footer = build_source_footer(edit_url, abs_path)
    assert footer.last_commit is None
    assert footer.history_url is not None


# ── _emit_source_footer ───────────────────────────────────────────────────────


def test_emit_footer_contains_edit_link():
    footer = SourceFooter(
        edit_url="https://github.com/org/repo/edit/main/docs/page.md",
        history_url="https://github.com/org/repo/commits/main/docs/page.md",
        last_commit="abc1234 · Fix typo · Jane · 2 days ago",
    )
    out = emit((footer,))
    assert "Edit this page" in out
    assert "View history" in out
    assert "abc1234" in out
    assert "Fix typo" in out
    assert 'ac:name="panel"' in out


def test_emit_footer_no_history_url():
    footer = SourceFooter(
        edit_url="https://example.com/edit/docs/page.md",
        history_url=None,
        last_commit=None,
    )
    out = emit((footer,))
    assert "Edit this page" in out
    assert "View history" not in out
    assert "Last commit" not in out


def test_emit_footer_escapes_html():
    footer = SourceFooter(
        edit_url='https://example.com/edit/path?a=1&b=2',
        history_url=None,
        last_commit='abc · <script>alert(1)</script> · Jane · today',
    )
    out = emit((footer,))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "a=1&amp;b=2" in out
