"""Tests for sync/comments.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from mkdocs_to_confluence.sync.comments import (
    ConfluenceComment,
    _parse_comment,
    _strip_tags,
    fetch_open_comments,
    format_github_comment,
)

BASE_URL = "https://example.atlassian.net"


# ── _strip_tags ───────────────────────────────────────────────────────────────


def test_strip_tags_basic() -> None:
    assert _strip_tags("<p>Hello world</p>") == "Hello world"


def test_strip_tags_nested() -> None:
    assert _strip_tags("<p>This is <strong>bold</strong> text.</p>") == "This is bold text."


def test_strip_tags_empty() -> None:
    assert _strip_tags("") == ""


def test_strip_tags_no_tags() -> None:
    assert _strip_tags("plain text") == "plain text"


# ── _parse_comment ────────────────────────────────────────────────────────────

_INLINE_RAW = {
    "id": "123",
    "version": {"authorId": "abc456", "createdAt": "2026-05-01T09:00:00.000Z"},
    "body": {"storage": {"value": "<p>This section is outdated.</p>"}},
    "properties": {"inlineOriginalSelection": "the deployment procedure"},
    "_links": {"webui": "/wiki/spaces/ARCH/pages/999?focusedCommentId=123"},
}

_FOOTER_RAW = {
    "id": "456",
    "version": {"authorId": "def789", "createdAt": "2026-05-02T10:00:00.000Z"},
    "body": {"storage": {"value": "<p>General page comment.</p>"}},
    "properties": {},
    "_links": {"webui": "/wiki/spaces/ARCH/pages/999?focusedCommentId=456"},
}


def test_parse_inline_comment() -> None:
    c = _parse_comment(_INLINE_RAW, "inline", BASE_URL)
    assert c.id == "123"
    assert c.type == "inline"
    assert c.author_id == "abc456"
    assert c.text == "This section is outdated."
    assert c.anchor_text == "the deployment procedure"
    assert c.webui_link == f"{BASE_URL}/wiki/spaces/ARCH/pages/999?focusedCommentId=123"
    assert c.created_at == "2026-05-01T09:00:00.000Z"


def test_parse_footer_comment() -> None:
    c = _parse_comment(_FOOTER_RAW, "footer", BASE_URL)
    assert c.id == "456"
    assert c.type == "footer"
    assert c.anchor_text == ""   # footer comments have no anchor
    assert c.text == "General page comment."


def test_parse_comment_absolute_webui_link() -> None:
    raw = {**_FOOTER_RAW, "_links": {"webui": "https://other.atlassian.net/wiki/already-absolute"}}
    c = _parse_comment(raw, "footer", BASE_URL)
    assert c.webui_link == "https://other.atlassian.net/wiki/already-absolute"


def test_parse_comment_missing_fields() -> None:
    c = _parse_comment({}, "footer", BASE_URL)
    assert c.id == ""
    assert c.text == ""
    assert c.author_id == "unknown"


# ── fetch_open_comments ───────────────────────────────────────────────────────


def test_fetch_open_comments_combines_inline_and_footer() -> None:
    client = MagicMock()
    client.get_page_inline_comments.return_value = [_INLINE_RAW]
    client.get_page_footer_comments.return_value = [_FOOTER_RAW]

    comments = fetch_open_comments(client, "999", BASE_URL)

    assert len(comments) == 2
    assert comments[0].type == "inline"
    assert comments[1].type == "footer"
    client.get_page_inline_comments.assert_called_once_with("999")
    client.get_page_footer_comments.assert_called_once_with("999")


def test_fetch_open_comments_empty() -> None:
    client = MagicMock()
    client.get_page_inline_comments.return_value = []
    client.get_page_footer_comments.return_value = []
    assert fetch_open_comments(client, "999", BASE_URL) == []


# ── format_github_comment ─────────────────────────────────────────────────────


def test_format_inline_comment_includes_anchor() -> None:
    c = ConfluenceComment(
        id="1", type="inline", author_id="alice", text="This is wrong.",
        anchor_text="the old procedure", webui_link="https://example.atlassian.net/wiki/...",
        created_at="2026-05-01",
    )
    body = format_github_comment(c)
    assert "> the old procedure" in body
    assert "This is wrong." in body
    assert "View in Confluence" in body
    assert "alice" in body


def test_format_footer_comment_no_anchor() -> None:
    c = ConfluenceComment(
        id="2", type="footer", author_id="bob", text="Overall good doc.",
        anchor_text="", webui_link="https://example.atlassian.net/wiki/...",
        created_at="2026-05-02",
    )
    body = format_github_comment(c)
    assert ">" not in body.split("\n")[2]  # no blockquote line
    assert "Overall good doc." in body
    assert "View in Confluence" in body
