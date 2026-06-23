"""Compile and publish the standalone changelog page."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from mkdocs_to_confluence.compiler.page import compile_page
from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.preprocess.frontmatter import _FRONT_MATTER_RE
from mkdocs_to_confluence.publisher.executor import upload_assets

if TYPE_CHECKING:
    from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
    from mkdocs_to_confluence.publisher.client import ConfluenceClient


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

    result = compile_page(node, config, link_map or {}, quiet=quiet)

    xhtml_hash = hashlib.sha256(result.xhtml.encode()).hexdigest()
    existing = client.find_page(space_id, title)

    if existing is not None and client.get_content_hash(str(existing["id"])) == xhtml_hash:
        if not quiet:
            print(f"  unchanged  '{title}'  (changelog)")
        return

    parent_id = conf_config.parent_page_id

    if existing is None:
        page = client.create_page(space_id, title, result.xhtml, parent_id=parent_id)
        page_id = str(page["id"])
        # Do NOT stamp as managed: _prune_orphans skips unmanaged pages, so
        # this ensures --prune never deletes the changelog page.
        if not quiet:
            print(f"  created    '{title}'  (changelog)")
    else:
        page_id = str(existing["id"])
        version: int = existing["version"]["number"]
        client.update_page(
            page_id, title, result.xhtml, version + 1,
            parent_id=parent_id,
            version_message=result.version_message,
        )
        if not quiet:
            print(f"  updated    '{title}'  (changelog)")

    if result.attachments:
        upload_assets(page_id, result.attachments, config.docs_dir, client, quiet=quiet)

    # content hash is an internal optimization; if it fails the next run just
    # re-publishes, so a failure is self-healing and stays silent.
    try:
        client.set_content_hash(page_id, xhtml_hash)
    except Exception:
        pass  # non-fatal

    # labels / full-width / status are user-configured presentation. They must
    # never fail an already-saved page (catch broadly so a transient network
    # error can't abort the publish), but failures are warned so they aren't
    # invisible — mirroring publisher/executor.py.
    if result.labels:
        try:
            client.set_page_labels(page_id, result.labels)
        except Exception as exc:
            print(f"  [warn] changelog: could not set labels: {exc}", file=sys.stderr)

    if conf_config.full_width:
        try:
            client.set_page_full_width(page_id)
        except Exception as exc:
            print(f"  [warn] changelog: could not set full-width: {exc}", file=sys.stderr)

    if result.confluence_status:
        try:
            client.set_page_status(page_id, result.confluence_status, space_key=space_key)
        except Exception as exc:
            print(
                f"  [warn] changelog: could not set page status "
                f"{result.confluence_status!r}: {exc}",
                file=sys.stderr,
            )
