"""Compile and publish the standalone changelog page."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.publisher.executor import _upload_assets
from mkdocs_to_confluence.publisher.planner import _xhtml_hash, compile_page

if TYPE_CHECKING:
    from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
    from mkdocs_to_confluence.publisher.client import ConfluenceClient

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n?)---\s*\n?", re.DOTALL)


def _extract_title(source_path: Path) -> str | None:
    """Return the ``title`` value from YAML front matter, or ``None`` if absent."""
    try:
        raw = source_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FRONT_MATTER_RE.match(raw)
    if not m:
        return None
    try:
        fm: object = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    val = fm.get("title")
    return str(val).strip() if val else None


def publish_changelog(
    config: MkDocsConfig,
    conf_config: ConfluenceConfig,
    client: ConfluenceClient,
    space_id: str,
    *,
    link_map: dict[str, str] | None = None,
    space_key: str | None = None,
    quiet: bool = False,
) -> None:
    """Compile and publish the changelog page if ``conf_config.changelog_file`` is set."""
    if not conf_config.changelog_file:
        return

    changelog_path = config.docs_dir / conf_config.changelog_file
    if not changelog_path.exists():
        print(
            f"  [warn] changelog: file not found: {changelog_path}",
            file=sys.stderr,
        )
        return

    title = _extract_title(changelog_path) or "What's New"

    node = NavNode(
        title=title,
        docs_path=str(changelog_path.relative_to(config.docs_dir)),
        source_path=changelog_path,
        level=0,
    )

    if not quiet:
        print(f"  compiling  '{title}'  (changelog)")

    xhtml, attachments, labels, confluence_status, version_message = compile_page(
        node, config, link_map or {}, quiet=quiet
    )

    xhtml_hash = _xhtml_hash(xhtml)
    existing = client.find_page(space_id, title)

    if existing is not None and client.get_content_hash(str(existing["id"])) == xhtml_hash:
        if not quiet:
            print(f"  unchanged  '{title}'  (changelog)")
        return

    parent_id = conf_config.parent_page_id

    if existing is None:
        page = client.create_page(space_id, title, xhtml, parent_id=parent_id)
        page_id = str(page["id"])
        # Do NOT stamp as managed: _prune_orphans skips unmanaged pages, so
        # this ensures --prune never deletes the changelog page.
        if not quiet:
            print(f"  created    '{title}'  (changelog)")
    else:
        page_id = str(existing["id"])
        version: int = existing["version"]["number"]
        client.update_page(
            page_id, title, xhtml, version + 1,
            parent_id=parent_id,
            version_message=version_message,
        )
        if not quiet:
            print(f"  updated    '{title}'  (changelog)")

    if attachments:
        _upload_assets(page_id, attachments, config.docs_dir, client, quiet=quiet)

    try:
        client.set_content_hash(page_id, xhtml_hash)
    except Exception:
        pass

    if labels:
        try:
            client.set_page_labels(page_id, labels)
        except Exception:
            pass

    if conf_config.full_width:
        try:
            client.set_page_full_width(page_id)
        except Exception:
            pass

    if confluence_status:
        try:
            client.set_page_status(page_id, confluence_status, space_key=space_key)
        except Exception:
            pass
