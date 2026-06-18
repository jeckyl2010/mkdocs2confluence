"""Planning helpers for the nav-driven publish pipeline."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from mkdocs_to_confluence.compiler.page import compile_page
from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.loader.page import PageLoadError
from mkdocs_to_confluence.preprocess.frontmatter import _FRONT_MATTER_RE
from mkdocs_to_confluence.preprocess.icons import strip_icon_shortcodes
from mkdocs_to_confluence.publisher.models import PageAction
from mkdocs_to_confluence.transforms.internallinks import build_link_map

if TYPE_CHECKING:
    from mkdocs_to_confluence.publisher.client import ConfluenceClient


def _extract_ready_flag(raw: str) -> bool | None:
    """Return the ``ready`` value from front matter, or ``None`` if absent."""
    m = _FRONT_MATTER_RE.match(raw)
    if not m:
        return None
    try:
        fm: object = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    val = fm.get("ready")
    if val is None:
        return None
    return bool(val)


def _find_section_index(node: NavNode) -> NavNode | None:
    """Return the first direct child whose docs_path ends with 'index.md'."""
    for child in node.children:
        if child.docs_path and child.docs_path.lower().endswith("index.md"):
            return child
    return None


def _plan_compiled_page_action(
    node: NavNode,
    client: ConfluenceClient,
    *,
    space_id: str,
    title: str,
    parent_id: str | None,
    parent_is_folder: bool,
    xhtml: str,
    attachments: list[Path],
    labels: tuple[str, ...],
    confluence_status: str | None,
    version_message: str | None,
    quiet: bool = False,
) -> PageAction:
    """Build the PageAction for a compiled page or section index."""
    existing = client.find_page(space_id, title)
    xhtml_h = hashlib.sha256(xhtml.encode()).hexdigest()
    if existing is not None and client.get_content_hash(str(existing["id"])) == xhtml_h:
        if not quiet:
            print(f"  unchanged  '{title}'  (content unchanged)")
        return PageAction(
            node=node,
            title=title,
            action="skip",
            parent_id=parent_id,
            parent_is_folder=parent_is_folder,
            page_id=str(existing["id"]),
            confluence_status=confluence_status,
        )

    return PageAction(
        node=node,
        title=title,
        action="create" if existing is None else "update",
        parent_id=parent_id,
        parent_is_folder=parent_is_folder,
        xhtml=xhtml,
        attachments=attachments,
        labels=labels,
        confluence_status=confluence_status,
        version_message=version_message,
        page_id=str(existing["id"]) if existing is not None else None,
        version=(
            existing["version"]["number"] if existing is not None else None
        ),
        is_folder=False,
        content_hash=xhtml_h,
    )


def plan_publish(
    nav_nodes: list[NavNode],
    client: ConfluenceClient,
    config: MkDocsConfig,
    conf_config: ConfluenceConfig,
    *,
    space_id: str,
    quiet: bool = False,
    full_nav_nodes: list[NavNode] | None = None,
) -> tuple[list[PageAction], dict[str, str]]:
    """Build a publish plan for the entire nav tree.

    Section nodes become native Confluence folders so the hierarchy is
    preserved visually. The actual find-or-create for folders is deferred
    to execute time once parent folder IDs are known.

    ``full_nav_nodes``, when provided, is used to build the link map so that
    cross-section internal links resolve correctly even when publishing only a
    subset of the nav (e.g. ``--section``).
    """
    actions: list[PageAction] = []
    link_map = build_link_map(full_nav_nodes if full_nav_nodes is not None else nav_nodes)
    if not quiet:
        print("Planning...")
    _plan_nodes(nav_nodes, client, config, space_id, conf_config.parent_page_id, False, actions, link_map, quiet=quiet)
    return actions, link_map


def _plan_nodes(
    nodes: list[NavNode],
    client: ConfluenceClient,
    config: MkDocsConfig,
    space_id: str,
    parent_id: str | None,
    parent_is_folder: bool,
    actions: list[PageAction],
    link_map: dict[str, str] | None = None,
    *,
    quiet: bool = False,
) -> None:
    for node in nodes:
        # Strip icon shortcodes from titles — nav titles bypass the body
        # preprocessor and raw shortcodes render as ??? in Confluence.
        clean_title = strip_icon_shortcodes(node.title).strip()
        if node.is_section:
            index_child = _find_section_index(node)
            if index_child is not None:
                # Section has an index.md — compile it as the section landing page
                # (mirrors Material for MkDocs section index behaviour).
                ready: bool | None = None
                if index_child.source_path is not None:
                    try:
                        raw = index_child.source_path.read_text(encoding="utf-8")
                        ready = _extract_ready_flag(raw)
                    except OSError:
                        pass
                if ready is not False and index_child.source_path is not None:
                    if not quiet:
                        print(f"  compiling  '{clean_title}'  (section index)")
                    try:
                        result = compile_page(
                            index_child, config, link_map, is_section_index=True, quiet=quiet
                        )
                        page_action = _plan_compiled_page_action(
                            node,
                            client,
                            space_id=space_id,
                            title=clean_title,
                            parent_id=parent_id,
                            parent_is_folder=parent_is_folder,
                            xhtml=result.xhtml,
                            attachments=result.attachments,
                            labels=result.labels,
                            confluence_status=result.confluence_status,
                            version_message=result.version_message,
                            quiet=quiet,
                        )
                        actions.append(page_action)
                        # Recurse remaining children — index.md is already consumed.
                        non_index = [c for c in node.children if c is not index_child]
                        _plan_nodes(
                            non_index,
                            client,
                            config,
                            space_id,
                            page_action.page_id if page_action.action == "skip" else None,
                            False,
                            actions,
                            link_map,
                            quiet=quiet,
                        )
                        continue
                    except (PageLoadError, OSError) as exc:
                        print(
                            f"  [warn] '{clean_title}'  index.md load error ({exc}),"
                            " falling back to folder",
                            file=sys.stderr,
                        )

            if not quiet:
                print(f"  compiling  '{clean_title}'  (folder)")
            # Folder find-or-create is deferred to execute_publish once the
            # parent folder ID is known (nested folders don't have a parent ID
            # yet at plan time).
            page_action = PageAction(
                node=node,
                title=clean_title,
                action="create",
                parent_id=parent_id,
                parent_is_folder=parent_is_folder,
                xhtml=None,
                is_folder=True,
                page_id=None,
            )
            actions.append(page_action)
            # Children will be placed under this folder's ID (resolved at execute)
            _plan_nodes(
                list(node.children), client, config, space_id, None, True, actions, link_map, quiet=quiet
            )
        else:
            # Page node — read raw to check ready flag
            ready = None
            if node.source_path is not None:
                try:
                    raw = node.source_path.read_text(encoding="utf-8")
                    ready = _extract_ready_flag(raw)
                except OSError:
                    pass

            if ready is False:
                if not quiet:
                    print(f"  skipping   '{clean_title}'  (ready: false)")
                actions.append(
                    PageAction(
                        node=node,
                        title=clean_title,
                        action="skip",
                        parent_id=parent_id,
                    )
                )
                continue

            if not quiet:
                print(f"  compiling  '{clean_title}'")
            try:
                result = compile_page(node, config, link_map, quiet=quiet)
            except (PageLoadError, OSError) as exc:
                if not quiet:
                    print(f"  skipping   '{clean_title}'  (error: {exc})")
                actions.append(
                    PageAction(
                        node=node,
                        title=clean_title,
                        action="skip",
                        parent_id=parent_id,
                    )
                )
                continue

            page_action = _plan_compiled_page_action(
                node,
                client,
                space_id=space_id,
                title=clean_title,
                parent_id=parent_id,
                parent_is_folder=False,
                xhtml=result.xhtml,
                attachments=result.attachments,
                labels=result.labels,
                confluence_status=result.confluence_status,
                version_message=result.version_message,
                quiet=quiet,
            )
            actions.append(page_action)
