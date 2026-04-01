"""Document envelope: PageMeta and Document."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from mkdocs_to_confluence.ir.nodes import IRNode


def compute_sha(content: str) -> str:
    """Return the SHA-256 hex digest of *content* encoded as UTF-8.

    Used to detect whether a page has changed since the last publish, allowing
    the publisher to skip unchanged pages.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PageMeta:
    """Immutable metadata about a single source page.

    Attributes:
        source_path:   Path of the source ``.md`` file relative to the repo
                       root (e.g. ``"docs/guide/installation.md"``).
        title:         Page title as it appears in the MkDocs nav.
        sha:           SHA-256 of the raw source markdown (before preprocessing).
                       Used by the publisher to skip unchanged pages.
        repo_url:      URL of the source repository, or ``None`` if not configured.
        tool_version:  Version of mkdocs-to-confluence that compiled this page.
        confluence_id: Confluence page ID populated by the publisher after the page
                       is created or looked up.  ``None`` before publishing.
    """

    source_path: str
    title: str
    sha: str
    repo_url: str | None = None
    tool_version: str = ""
    confluence_id: int | None = None


@dataclass
class Document:
    """The compiled representation of a single MkDocs page.

    ``Document`` is intentionally *not* frozen because transform passes mutate
    ``attachments`` and ``nav_context`` after the parser creates the initial
    instance.  The ``body`` nodes themselves are frozen and never mutated.

    Attributes:
        meta:         Immutable page metadata.
        body:         Top-level IR nodes produced by the parser.  Sections may
                      nest further nodes within their ``children``.
        attachments:  Local file paths of images and other assets collected by
                      the images transform.  Populated after parsing.
        nav_context:  Mapping from source path to Confluence page title, used
                      by the link-resolution transform.  Populated from the nav
                      before the transform pass runs.
    """

    meta: PageMeta
    body: tuple[IRNode, ...]
    attachments: list[str] = field(default_factory=list)
    nav_context: dict[str, str] = field(default_factory=dict)
