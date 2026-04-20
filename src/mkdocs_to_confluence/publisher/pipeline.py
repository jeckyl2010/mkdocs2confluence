"""Nav-driven publish pipeline.

The pipeline has two phases:

1. **plan** — walk the nav tree, compile each page, and decide whether to
   ``create``, ``update``, or ``skip`` it in Confluence.
2. **execute** — carry out the plan, creating/updating pages and uploading
   attachments in nav order so parent pages always exist before their children.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.loader.page import PageLoadError, load_page
from mkdocs_to_confluence.parser.markdown import parse
from mkdocs_to_confluence.preprocess.abbrevs import (
    extract_abbreviations,
    strip_abbreviation_defs,
)
from mkdocs_to_confluence.preprocess.frontmatter import extract_front_matter
from mkdocs_to_confluence.preprocess.icons import strip_icon_shortcodes
from mkdocs_to_confluence.preprocess.includes import (
    preprocess_includes,
    strip_html_comments,
    strip_unsupported_html,
)
from mkdocs_to_confluence.transforms.abbrevs import apply_abbreviations
from mkdocs_to_confluence.transforms.assets import _make_attachment_name, resolve_local_assets
from mkdocs_to_confluence.transforms.editlink import attach_source_url
from mkdocs_to_confluence.transforms.internallinks import build_link_map, resolve_internal_links

if TYPE_CHECKING:
    from mkdocs_to_confluence.publisher.client import ConfluenceClient

# ── Data structures ───────────────────────────────────────────────────────────

_Action = Literal["create", "update", "skip", "section"]

_FRONT_MATTER_RE = __import__("re").compile(r"\A---\s*\n(.*?\n?)---\s*\n?", __import__("re").DOTALL)


@dataclass
class PageAction:
    """Represents one page in the publish plan."""

    node: NavNode
    title: str
    action: _Action
    parent_id: str | None
    xhtml: str | None = None
    attachments: list[Path] = field(default_factory=list)
    # Set after execution:
    page_id: str | None = None
    version: int | None = None  # current remote version (for update)


# ── Compilation ───────────────────────────────────────────────────────────────


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


def compile_page(
    node: NavNode,
    config: MkDocsConfig,
    link_map: dict[str, str] | None = None,
) -> tuple[str, list[Path]]:
    """Run the full compile pipeline for one page.

    Returns
    -------
    tuple[str, list[Path]]
        ``(xhtml_string, attachment_paths)``
    """
    if node.source_path is None:
        return "", []

    raw = load_page(node)

    preprocessed = preprocess_includes(
        raw,
        source_path=node.source_path,
        docs_dir=config.docs_dir,
    )
    preprocessed = strip_unsupported_html(preprocessed)
    preprocessed = strip_html_comments(preprocessed)
    preprocessed = strip_icon_shortcodes(preprocessed)
    front_matter, preprocessed = extract_front_matter(preprocessed)
    abbrevs = extract_abbreviations(preprocessed)
    preprocessed = strip_abbreviation_defs(preprocessed)
    ir_nodes = parse(preprocessed)
    ir_nodes = apply_abbreviations(ir_nodes, abbrevs, page_text=preprocessed)
    ir_nodes, attachments = resolve_local_assets(
        ir_nodes,
        page_path=node.source_path,
        docs_dir=config.docs_dir,
    )
    effective_link_map = link_map if link_map is not None else {}
    if node.docs_path:
        ir_nodes = resolve_internal_links(ir_nodes, effective_link_map, node.docs_path)
    if front_matter is not None:
        ir_nodes = (front_matter,) + ir_nodes
    edit_url = config.page_edit_url(node.docs_path or "")
    if edit_url:
        ir_nodes = attach_source_url(ir_nodes, edit_url)

    xhtml = emit(ir_nodes)
    return xhtml, attachments


# ── Planning ──────────────────────────────────────────────────────────────────


def plan_publish(
    nav_nodes: list[NavNode],
    client: ConfluenceClient,
    config: MkDocsConfig,
    conf_config: ConfluenceConfig,
    *,
    space_id: str,
) -> list[PageAction]:
    """Build a publish plan for the entire nav tree.

    Section nodes become empty parent pages so their children can be nested
    under them.  The parent_id chain is resolved top-down.
    """
    actions: list[PageAction] = []
    link_map = build_link_map(nav_nodes)
    _plan_nodes(nav_nodes, client, config, space_id, conf_config.parent_page_id, actions, link_map)
    return actions


def _plan_nodes(
    nodes: list[NavNode],
    client: ConfluenceClient,
    config: MkDocsConfig,
    space_id: str,
    parent_id: str | None,
    actions: list[PageAction],
    link_map: dict[str, str] | None = None,
) -> None:
    for node in nodes:
        if node.is_section:
            existing = client.find_page(space_id, node.title)
            action_kind: _Action = "create" if existing is None else "update"
            page_action = PageAction(
                node=node,
                title=node.title,
                action=action_kind,
                parent_id=parent_id,
                xhtml="",  # section pages are empty
                page_id=str(existing["id"]) if existing is not None else None,
                version=(
                    existing["version"]["number"] if existing is not None else None
                ),
            )
            actions.append(page_action)
            # Children will be placed under this section's page_id (resolved at execute)
            _plan_nodes(
                list(node.children), client, config, space_id, None, actions, link_map
            )
        else:
            # Page node — read raw to check ready flag
            ready: bool | None = None
            if node.source_path is not None:
                try:
                    raw = node.source_path.read_text(encoding="utf-8")
                    ready = _extract_ready_flag(raw)
                except OSError:
                    pass

            if ready is False:
                actions.append(
                    PageAction(
                        node=node,
                        title=node.title,
                        action="skip",
                        parent_id=parent_id,
                    )
                )
                continue

            try:
                xhtml, attachments = compile_page(node, config, link_map)
            except (PageLoadError, OSError):
                actions.append(
                    PageAction(
                        node=node,
                        title=node.title,
                        action="skip",
                        parent_id=parent_id,
                    )
                )
                continue

            existing = client.find_page(space_id, node.title)
            page_action = PageAction(
                node=node,
                title=node.title,
                action="create" if existing is None else "update",
                parent_id=parent_id,
                xhtml=xhtml,
                attachments=attachments,
                page_id=str(existing["id"]) if existing is not None else None,
                version=(
                    existing["version"]["number"] if existing is not None else None
                ),
            )
            actions.append(page_action)


# ── Execution ─────────────────────────────────────────────────────────────────


def execute_publish(
    plan: list[PageAction],
    client: ConfluenceClient,
    *,
    dry_run: bool = False,
    space_id: str,
    docs_dir: Path,
) -> list[PageAction]:
    """Execute the publish plan.

    Pages are processed in nav order so parent sections are always created
    before their children.  Once a section's ``page_id`` is known (after
    create/update), all direct children in the plan have their ``parent_id``
    updated immediately — avoiding the pre-pass approach that broke for
    newly-created sections.

    Returns the updated plan with ``page_id`` filled in for executed actions.
    """
    if dry_run:
        return plan

    # Index: nav node id → PageAction, used to wire child parent_ids after
    # each section is created/updated.
    action_by_node: dict[int, PageAction] = {id(a.node): a for a in plan}

    for action in plan:
        if action.action == "skip":
            continue

        if action.action == "create":
            page = client.create_page(
                space_id,
                action.title,
                action.xhtml or "",
                parent_id=action.parent_id,
            )
            action.page_id = str(page["id"])
        elif action.action == "update":
            assert action.page_id is not None
            assert action.version is not None
            client.update_page(
                action.page_id,
                action.title,
                action.xhtml or "",
                action.version + 1,
            )

        # Once a section's page_id is known, wire it into all direct children
        # so that children created later in the loop use the correct parent_id.
        if action.node.is_section and action.page_id:
            for child_node in action.node.children:
                child_action = action_by_node.get(id(child_node))
                if child_action is not None:
                    child_action.parent_id = action.page_id

        # Upload attachments using collision-safe names derived from docs_dir.
        if action.page_id and action.attachments:
            existing_attachments = client.list_attachments(action.page_id)
            for attachment_path in action.attachments:
                att_name = _make_attachment_name(attachment_path, docs_dir)
                if att_name not in existing_attachments:
                    client.upload_attachment(action.page_id, attachment_path, att_name)

    return plan
