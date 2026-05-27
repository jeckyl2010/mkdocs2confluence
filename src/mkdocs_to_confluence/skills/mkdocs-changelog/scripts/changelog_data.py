#!/usr/bin/env python3
"""Extract changelog-relevant git data and print it as JSON.

Usage (run from the project root):
    python .mk2conf/scripts/changelog_data.py [--docs-dir docs]

Output is a JSON object on stdout. Nothing is written to disk.
No external dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date


def _run(args: list[str]) -> str:
    """Run a git command and return stripped stdout. Returns '' on error."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        return ""


def _baseline_commit(changelog_path: str) -> str | None:
    """Return the SHA of the last commit that touched changelog_path, or None."""
    sha = _run(["git", "log", "--follow", "-1", "--format=%H", "--", changelog_path])
    return sha or None


def _commit_before_date(since_date: str) -> str | None:
    """Return the SHA of the last commit strictly before since_date (YYYY-MM-DD), or None."""
    sha = _run([
        "git", "log", "--format=%H",
        f"--before={since_date}",
        "-1",
    ])
    return sha or None


def _root_commit() -> str:
    """Return the SHA of the very first commit in the repo."""
    return _run(["git", "rev-list", "--max-parents=0", "HEAD"])


def _commits_since(baseline: str) -> list[dict[str, str]]:
    """Return commits reachable from HEAD but not from baseline (exclusive)."""
    sep = "\x1f"  # unit separator — safe delimiter
    fmt = f"%H{sep}%s{sep}%aN{sep}%as"  # sha, subject, author name, date
    raw = _run(["git", "log", f"{baseline}..HEAD", f"--format={fmt}"])
    if not raw:
        return []
    commits = []
    for line in raw.splitlines():
        parts = line.split(sep)
        if len(parts) != 4:  # noqa: PLR2004
            continue
        sha, subject, author, commit_date = parts
        commits.append({"sha": sha, "subject": subject, "author": author, "date": commit_date})
    return commits


def _changed_files(baseline: str, docs_dir: str) -> dict[str, list[str]]:
    """Return files changed in docs_dir since baseline, grouped by status."""
    raw = _run([
        "git", "diff", "--name-status", f"{baseline}..HEAD", "--", docs_dir,
    ])
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    if not raw:
        return {"added": added, "modified": modified, "deleted": deleted}
    for line in raw.splitlines():
        parts = line.split("\t", maxsplit=1)
        if len(parts) != 2:  # noqa: PLR2004
            continue
        status, path = parts[0].strip(), parts[1].strip()
        if status.startswith("A"):
            added.append(path)
        elif status.startswith("D"):
            deleted.append(path)
        elif status.startswith("M") or status.startswith("R") or status.startswith("C"):
            modified.append(path)
    return {"added": added, "modified": modified, "deleted": deleted}


def _contributors(commits: list[dict[str, str]]) -> list[str]:
    """Return unique contributor names from commits, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for c in commits:
        name = c["author"]
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract git changelog data as JSON.")
    parser.add_argument(
        "--docs-dir",
        default="docs",
        help="Path to the MkDocs docs directory, relative to project root (default: docs)",
    )
    parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help=(
            "Use the last commit before DATE (YYYY-MM-DD) as the baseline instead of the "
            "last commit that touched CHANGELOG.md. Useful for creating an initial changelog."
        ),
    )
    args = parser.parse_args()

    docs_dir: str = args.docs_dir
    changelog_rel = f"{docs_dir}/CHANGELOG.md"

    # Baseline resolution — --since takes priority
    if args.since:
        baseline = _commit_before_date(args.since)
        if not baseline:
            print(
                f"error: no commit found before {args.since}",
                file=sys.stderr,
            )
            sys.exit(1)
        mode = "since_date"
    else:
        baseline = _baseline_commit(changelog_rel) or _root_commit()
        if not baseline:
            print(
                "error: could not determine a baseline commit — is this a git repository?",
                file=sys.stderr,
            )
            sys.exit(1)
        mode = "changelog_commit"

    commits = _commits_since(baseline)
    changes = _changed_files(baseline, docs_dir)
    contributors = _contributors(commits)

    output = {
        "date": date.today().isoformat(),
        "mode": mode,
        "since": args.since,
        "baseline_commit": baseline,
        "commits": commits,
        "contributors": contributors,
        "changes": changes,
        "docs_dir": docs_dir,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
