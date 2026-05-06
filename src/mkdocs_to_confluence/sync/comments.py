"""Fetch open Confluence comments and format them for GitHub review threads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mkdocs_to_confluence.publisher.client import ConfluenceClient


@dataclass
class ConfluenceComment:
    """A single open comment from a Confluence page."""

    id: str
    type: Literal["inline", "footer"]
    author_id: str
    text: str          # plain text of the comment body
    anchor_text: str   # inlineOriginalSelection; empty for footer comments
    webui_link: str    # absolute URL that opens Confluence focused on this comment
    created_at: str


def fetch_open_comments(
    client: ConfluenceClient,
    page_id: str,
    base_url: str,
) -> list[ConfluenceComment]:
    """Return all open inline and footer comments for *page_id*.

    *base_url* is the Confluence base without trailing slash or /wiki suffix
    (e.g. ``https://yourorg.atlassian.net``).  It is used to make the
    *webui_link* absolute.
    """
    comments: list[ConfluenceComment] = []
    for raw in client.get_page_inline_comments(page_id):
        comments.append(_parse_comment(raw, "inline", base_url))
    for raw in client.get_page_footer_comments(page_id):
        comments.append(_parse_comment(raw, "footer", base_url))
    return comments


def format_github_comment(comment: ConfluenceComment) -> str:
    """Format a Confluence comment as a GitHub review thread body."""
    lines: list[str] = [f"💬 **{comment.author_id}** · *{comment.created_at}*", ""]
    if comment.anchor_text:
        lines += [f"> {comment.anchor_text}", ""]
    lines += [comment.text, "", f"🔗 [View in Confluence]({comment.webui_link})"]
    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_comment(
    raw: dict[str, Any],
    ctype: Literal["inline", "footer"],
    base_url: str,
) -> ConfluenceComment:
    props = raw.get("properties", {})
    anchor_text = props.get("inlineOriginalSelection", "") if ctype == "inline" else ""

    body_value = raw.get("body", {}).get("storage", {}).get("value", "")
    text = _strip_tags(body_value)

    version = raw.get("version", {})
    author_id = version.get("authorId", "unknown")
    created_at = version.get("createdAt", "")

    webui = raw.get("_links", {}).get("webui", "")
    # webui is a root-relative path like "/wiki/spaces/.../pages/...?focusedCommentId=..."
    # base_url is e.g. "https://yourorg.atlassian.net" (no /wiki suffix stripped already)
    webui_link = base_url + webui if webui.startswith("/") else webui

    return ConfluenceComment(
        id=str(raw.get("id", "")),
        type=ctype,
        author_id=author_id,
        text=text,
        anchor_text=anchor_text,
        webui_link=webui_link,
        created_at=created_at,
    )
