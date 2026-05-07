"""Source-footer transform.

Builds a :class:`~ir.nodes.SourceFooter` node from a VCS edit URL and the
absolute path of the source file.  The node is appended to the IR node list
by the publish pipeline so it renders as a footer panel on each Confluence page.
"""

from __future__ import annotations

import subprocess

from mkdocs_to_confluence.ir.nodes import SourceFooter


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


def _last_commit(abs_path: str) -> str | None:
    """Return a human-readable last-commit summary for *abs_path*.

    Runs ``git log -1 --format=... --date=relative`` on the file.
    Returns ``None`` when git is unavailable, the path is untracked, or the
    command fails for any reason.
    """
    try:
        result = subprocess.run(
            [
                "git", "log", "-1",
                "--format=%h \u00b7 %s \u00b7 %an \u00b7 %ad",
                "--date=relative",
                "--",
                abs_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout.strip()
        return output if output else None
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
    return SourceFooter(
        edit_url=edit_url,
        history_url=_derive_history_url(edit_url),
        last_commit=_last_commit(abs_path),
    )
