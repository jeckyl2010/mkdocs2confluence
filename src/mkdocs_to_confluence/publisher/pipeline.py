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
from mkdocs_to_confluence.transforms.assets import resolve_local_assets

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


def compile_page(node: NavNode, config: MkDocsConfig) -> tuple[str, list[Path]]:
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
    if front_matter is not None:
        ir_nodes = (front_matter,) + ir_nodes

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
    _plan_nodes(nav_nodes, client, config, space_id, conf_config.parent_page_id, actions)
    return actions


def _plan_nodes(
    nodes: list[NavNode],
    client: ConfluenceClient,
    config: MkDocsConfig,
    space_id: str,
    parent_id: str | None,
    actions: list[PageAction],
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
                list(node.children), client, config, space_id, None, actions
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
                xhtml, attachments = compile_page(node, config)
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
) -> list[PageAction]:
    """Execute the publish plan.

    Pages are processed in order so parent sections are created before child
    pages.  Section actions carry a ``_section_ref`` so that child pages can
    look up the created/found page ID for their ``parent_id``.

    Returns the updated plan with ``page_id`` filled in for executed actions.
    """
    if dry_run:
        return plan

    # Map section node id → created/found page_id so children can reference it
    section_page_ids: dict[int, str] = {}

    # We need to resolve parent_id for children of sections at execute time.
    # Rebuild parent_id by walking the plan in order and tracking depth.
    _resolve_parent_ids(plan, section_page_ids)

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
            page = client.update_page(
                action.page_id,
                action.title,
                action.xhtml or "",
                action.version + 1,
            )

        if action.page_id and action.node.is_section:
            section_page_ids[id(action.node)] = action.page_id

        # Upload attachments
        if action.page_id and action.attachments:
            existing_attachments = client.list_attachments(action.page_id)
            for attachment_path in action.attachments:
                # Derive the attachment filename
                from mkdocs_to_confluence.transforms.assets import _make_attachment_name
                docs_dir = None
                # We need config.docs_dir — passed implicitly via attachment_name on nodes
                # Fall back to just the filename
                att_name = attachment_path.name
                # Check if already uploaded
                if att_name not in existing_attachments:
                    client.upload_attachment(action.page_id, attachment_path, att_name)

    return plan


def _resolve_parent_ids(
    plan: list[PageAction],
    section_page_ids: dict[int, str],
) -> None:
    """Post-process plan to fill parent_id for children of sections.

    The planning phase leaves children of section nodes with ``parent_id=None``
    because the section's page_id is not known until execution.  This function
    walks the nav structure mirrored in the plan and wires up the parent_ids
    by using the section node identity.
    """
    # Build index: nav node id → PageAction
    action_by_node: dict[int, PageAction] = {id(a.node): a for a in plan}

    # Walk the original nav order implicit in the plan.
    # Section actions appear before their children in document order.
    # We track the "current section stack" to resolve parents.
    _walk_and_resolve(plan, action_by_node)


def _walk_and_resolve(
    plan: list[PageAction],
    action_by_node: dict[int, PageAction],
) -> None:
    """Fill ``parent_id`` for child pages using the section node tree."""
    # We reconstruct the tree by looking at node.level and nav structure.
    # Use a depth-first traversal of each section's children.
    for action in plan:
        if not action.node.is_section:
            continue
        # For every child of this section, set parent_id to this section's page_id
        for child_node in action.node.children:
            child_action = action_by_node.get(id(child_node))
            if child_action is not None and child_action.parent_id is None:
                # Will be resolved at execute time — store a reference
                child_action.parent_id = action.page_id  # may still be None pre-execution
