"""Orchestration for mk2conf sync-comments."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from mkdocs_to_confluence.sync.anchoring import find_anchor_line
from mkdocs_to_confluence.sync.comments import ConfluenceComment, fetch_open_comments, format_github_comment
from mkdocs_to_confluence.sync.state import PRRecord, SyncState

if TYPE_CHECKING:
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    from mkdocs_to_confluence.publisher.client import ConfluenceClient
    from mkdocs_to_confluence.sync.platform import ReviewPlatformClient

PAGE_MAP_FILE = ".mk2conf-pages.json"
STATE_FILE = ".mk2conf-sync-state.json"


def load_page_map(config_dir: Path) -> dict[str, str]:
    """Load ``{repo_relative_path → page_id}`` from *.mk2conf-pages.json*.

    Raises :class:`FileNotFoundError` when the file has not been generated yet.
    """
    path = config_dir / PAGE_MAP_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{PAGE_MAP_FILE} not found in {config_dir}. "
            "Run `mk2conf publish` first to generate it."
        )
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def run_sync_comments(
    *,
    config: MkDocsConfig,
    config_dir: Path,
    confluence_client: ConfluenceClient,
    review_client: ReviewPlatformClient,
    force: bool = False,
    dry_run: bool = False,
    quiet: bool = False,
) -> int:
    """Sync open Confluence comments to GitHub review PRs.

    For each page in the page map that has open Confluence comments and no
    existing review PR, this function:

    1. Creates a branch from the configured base branch.
    2. Opens a pull request.
    3. Posts each Confluence comment as a GitHub review thread, line-anchored
       when the highlighted text is found in the source file.
    4. Persists the PR record to the sync state file.

    Returns the number of new PRs created.
    """
    assert config.confluence is not None
    conf = config.confluence

    page_map = load_page_map(config_dir)
    state_path = config_dir / STATE_FILE
    state = SyncState.load(state_path)

    # Strip /wiki suffix so webui links are absolute and correct
    base_url = conf.base_url.rstrip("/")
    if base_url.endswith("/wiki"):
        base_url = base_url[: -len("/wiki")]

    new_prs = 0

    for source_path, page_id in page_map.items():
        if state.has_open_pr_for(page_id) and not force:
            if not quiet:
                print(f"  [skip] {source_path} — already has an open review PR")
            continue

        comments = fetch_open_comments(confluence_client, page_id, base_url)
        if not comments:
            continue

        if not quiet:
            print(f"  [sync] {source_path} — {len(comments)} comment(s)")

        if dry_run:
            for c in comments:
                prefix = f"[{c.type}]"
                anchor = f" on '{c.anchor_text[:40]}'" if c.anchor_text else ""
                print(f"    • {prefix}{anchor}: {c.text[:60]!r}")
            continue

        branch = _branch_name(source_path)
        pr_title = f"Documentation review: {source_path}"
        pr_body = _build_pr_body(source_path, comments)

        review_client.create_review_branch(conf.github_base_branch, branch)
        pr_number, pr_node_id = review_client.create_pull_request(
            branch, conf.github_base_branch, pr_title, pr_body
        )

        abs_source = config_dir / source_path
        inline_ids: list[str] = []
        footer_ids: list[str] = []

        for comment in comments:
            line: int | None = None
            if comment.anchor_text and abs_source.exists():
                line = find_anchor_line(abs_source, comment.anchor_text)
            body = format_github_comment(comment)
            try:
                review_client.post_review_comment(pr_node_id, source_path, body, line)
            except Exception as exc:
                print(f"  [warn] could not post comment {comment.id}: {exc}")

            if comment.type == "inline":
                inline_ids.append(comment.id)
            else:
                footer_ids.append(comment.id)

        state.prs[str(pr_number)] = PRRecord(
            page_id=page_id,
            page_title=pr_title,
            source_path=source_path,
            branch=branch,
            pr_number=pr_number,
            pr_node_id=pr_node_id,
            inline_comment_ids=inline_ids,
            footer_comment_ids=footer_ids,
        )
        state.save(state_path)
        new_prs += 1

        if not quiet:
            print(f"    → PR #{pr_number} ({branch})")

    if not quiet:
        if new_prs:
            print(f"\nCreated {new_prs} review PR(s).")
        elif not dry_run:
            print("No new comments to sync.")

    return new_prs


def check_and_resolve_merges(
    *,
    config_dir: Path,
    confluence_client: ConfluenceClient,
    review_client: ReviewPlatformClient,
    quiet: bool = False,
) -> int:
    """Check tracked PRs for merges and resolve Confluence comments on merge.

    For each unmerged tracked PR that is now merged, this function:

    1. Adds a resolution reply to each Confluence comment.
    2. Marks the comment as resolved.
    3. Updates the sync state.

    Returns the number of PRs resolved.
    """
    state_path = config_dir / STATE_FILE
    state = SyncState.load(state_path)

    resolved = 0

    for pr_num, record in state.prs.items():
        if record.merged:
            continue

        merged, commit_sha = review_client.get_pr_merge_info(int(pr_num))
        if not merged:
            continue

        if not quiet:
            sha_short = commit_sha[:7] if commit_sha else "unknown"
            print(f"  [merged] PR #{pr_num} ({record.source_path}) commit {sha_short}")

        reply = (
            f"[Resolved via PR #{pr_num} — {commit_sha}]"
            if commit_sha
            else f"[Resolved via PR #{pr_num}]"
        )

        for comment_id in record.inline_comment_ids:
            try:
                confluence_client.add_comment_reply(comment_id, reply)
                confluence_client.resolve_inline_comment(comment_id)
            except Exception as exc:
                print(f"  [warn] could not resolve inline comment {comment_id}: {exc}")

        for comment_id in record.footer_comment_ids:
            try:
                confluence_client.add_comment_reply(comment_id, reply)
                confluence_client.resolve_footer_comment(comment_id)
            except Exception as exc:
                print(f"  [warn] could not resolve footer comment {comment_id}: {exc}")

        record.merged = True
        state.save(state_path)
        resolved += 1

    if not quiet:
        if resolved:
            print(f"Resolved {resolved} PR(s) in Confluence.")
        else:
            print("No merged PRs found.")

    return resolved


# ── Internal helpers ──────────────────────────────────────────────────────────


def _branch_name(source_path: str) -> str:
    slug = source_path.lower().removesuffix(".md")
    slug = re.sub(r"[^a-z0-9/]+", "-", slug).strip("-/")
    return f"mk2conf/review/{slug}"


def _build_pr_body(source_path: str, comments: list[ConfluenceComment]) -> str:
    n = len(comments)
    return "\n".join([
        f"## Documentation review: `{source_path}`",
        "",
        f"{n} open Confluence comment(s) require attention (see review threads below).",
        "",
        "---",
        "",
        "**Workflow:**",
        "1. Address each review thread comment on this branch.",
        "2. Push your changes.",
        "3. Merge this PR — the Confluence comments will be auto-resolved.",
    ])
