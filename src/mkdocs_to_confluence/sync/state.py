"""Sync state — tracks which Confluence pages have open review PRs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PRRecord:
    """Everything we need to know about one open or merged review PR."""

    page_id: str
    pr_title: str                   # PR title, e.g. "Documentation review: docs/foo.md"
    source_path: str            # repo-relative, e.g. "docs/architecture/overview.md"
    branch: str
    pr_number: int
    pr_node_id: str             # GitHub GraphQL node ID (PR_kwDO...)
    merged: bool = False
    inline_comment_ids: list[str] = field(default_factory=list)
    footer_comment_ids: list[str] = field(default_factory=list)


@dataclass
class SyncState:
    """Persisted sync state loaded from / saved to *.mk2conf-sync-state.json*."""

    prs: dict[str, PRRecord] = field(default_factory=dict)  # key: str(pr_number)

    @classmethod
    def load(cls, path: Path) -> SyncState:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        prs = {k: PRRecord(**v) for k, v in data.get("prs", {}).items()}
        return cls(prs=prs)

    def save(self, path: Path) -> None:
        data = {"prs": {k: asdict(v) for k, v in self.prs.items()}}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def has_open_pr_for(self, page_id: str) -> bool:
        """Return True when *page_id* already has a tracked, unmerged PR."""
        return any(r.page_id == page_id and not r.merged for r in self.prs.values())
