"""Typed models for compiler outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CompileResult:
    """Result of compiling a single MkDocs page to Confluence storage XHTML."""

    xhtml: str
    attachments: list[Path] = field(default_factory=list)
    labels: tuple[str, ...] = ()
    confluence_status: str | None = None
    version_message: str | None = None
