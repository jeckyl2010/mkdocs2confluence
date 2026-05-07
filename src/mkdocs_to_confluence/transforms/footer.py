"""Source-footer transform.

Builds a :class:`~ir.nodes.SourceFooter` node from a VCS edit URL and the
absolute path of the source file.  The node is appended to the IR node list
by the publish pipeline so it renders as a footer panel on each Confluence page.
"""

from __future__ import annotations

import subprocess

from mkdocs_to_confluence.ir.nodes import SourceFooter

# separator used in git --format to allow reliable splitting
_GIT_SEP = "\x1f"  # ASCII unit separator — never appears in commit messages


def _derive_history_url(edit_url: str) -> str | None:
    """Derive a commit-history URL from a VCS edit URL.

    Supports GitHub (``/edit/``) and GitLab (``/-/edit/``).
    Returns ``None`` for any other URL shape.
    """
    if "/-/edit/" in edit_url:
        return edit_url.replace("/-/edit/", "/-/commits/", 1)
    if "/edit/" in edit_url:
        return edit_url.replace("/edit/", "/commits/", 1)
    return None


def _derive_commit_url(edit_url: str, sha: str) -> str | None:
    """Derive a direct commit URL from a VCS edit URL and a commit SHA.

    Supports GitHub (``/edit/``) and GitLab (``/-/edit/``).
    Returns ``None`` for any other URL shape.
    """
    if "/-/edit/" in edit_url:
        base = edit_url.split("/-/edit/")[0]
        return f"{base}/-/commit/{sha}"
    if "/edit/" in edit_url:
        base = edit_url.split("/edit/")[0]
        return f"{base}/commit/{sha}"
    return None


def _last_commit_info(abs_path: str) -> tuple[str, str] | None:
    """Return ``(short_sha, summary)`` for the last commit touching *abs_path*.

    *summary* is ``"message · author · relative_date"``.
    Returns ``None`` when git is unavailable, the path is untracked, or the
    command fails for any reason.
    """
    sep = _GIT_SEP
    try:
        result = subprocess.run(
            [
                "git", "log", "-1",
                f"--format=%h{sep}%s{sep}%an{sep}%ad",
                "--date=relative",
                "--",
                abs_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout.strip()
        if not output:
            return None
        parts = output.split(sep, 3)
        if len(parts) < 4:
            return None
        sha, message, author, date = parts
        return sha, f"{message} \u00b7 {author} \u00b7 {date}"
    except Exception:  # noqa: BLE001
        return None


def build_source_footer(edit_url: str, abs_path: str) -> SourceFooter:
    """Build a :class:`SourceFooter` for the given *edit_url* and source file.

    Parameters
    ----------
    edit_url:
        Full URL to edit the source file (e.g. GitHub edit link).
    abs_path:
        Absolute filesystem path to the source Markdown file.  Used to
        query ``git log`` for the last-commit summary.
    """
    commit_info = _last_commit_info(abs_path)
    if commit_info is not None:
        sha, summary = commit_info
        commit_url = _derive_commit_url(edit_url, sha)
    else:
        sha = None
        summary = None
        commit_url = None

    return SourceFooter(
        edit_url=edit_url,
        history_url=_derive_history_url(edit_url),
        commit_sha=sha,
        commit_url=commit_url,
        commit_summary=summary,
    )
