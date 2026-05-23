from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from mkdocs_to_confluence.loader.nav import NavNode

_Action = Literal["create", "update", "skip", "section"]


@dataclass
class PageAction:
    """Represents one page or folder in the publish plan."""

    node: NavNode
    title: str
    action: _Action
    parent_id: str | None
    xhtml: str | None = None
    attachments: list[Path] = field(default_factory=list)
    labels: tuple[str, ...] = field(default_factory=tuple)
    confluence_status: str | None = None
    version_message: str | None = None  # git commit message for Confluence version history
    is_folder: bool = False        # True when this action creates a Confluence folder
    parent_is_folder: bool = False  # True when the parent content is a folder
    # Set after execution:
    page_id: str | None = None
    version: int | None = None  # current remote version (for update)
    content_hash: str | None = None  # sha256 of emitted xhtml (for smart-skip)


@dataclass
class PublishReport:
    """Summary of a completed publish run."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    assets_uploaded: int = 0
    assets_skipped: int = 0
    pruned: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return self.created + self.updated + self.skipped

    def __str__(self) -> str:
        lines = [
            f"Published:  {self.created} created, {self.updated} updated, {self.skipped} skipped",
            f"Assets:     {self.assets_uploaded} uploaded, {self.assets_skipped} skipped",
        ]
        if self.pruned:
            lines.append(f"Pruned:     {self.pruned} orphaned page(s) deleted")
        if self.errors:
            lines.append(f"Errors:     {len(self.errors)}")
            for title, msg in self.errors:
                lines.append(f"  ✗ {title}: {msg}")
        return "\n".join(lines)
