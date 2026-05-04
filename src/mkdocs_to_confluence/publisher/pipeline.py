"""Nav-driven publish pipeline.

The pipeline has two phases:

1. **plan** — walk the nav tree, compile each page, and decide whether to
   ``create``, ``update``, or ``skip`` it in Confluence.
2. **execute** — carry out the plan, creating/updating pages and uploading
   attachments in nav order so parent pages always exist before their children.
   Attachments for each page are uploaded sequentially — Confluence holds a
   page-level lock during each attachment write, so concurrent POSTs to the
   same page cause transaction rollbacks.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import FrontMatter
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
from mkdocs_to_confluence.preprocess.linkdefs import (
    collect_link_defs,
    expand_link_refs,
    strip_link_defs,
)
from mkdocs_to_confluence.publisher.client import ConfluenceError
from mkdocs_to_confluence.transforms.abbrevs import apply_abbreviations
from mkdocs_to_confluence.transforms.assets import _make_attachment_name, resolve_local_assets
from mkdocs_to_confluence.transforms.editlink import attach_source_url
from mkdocs_to_confluence.transforms.internallinks import build_link_map, resolve_internal_links
from mkdocs_to_confluence.transforms.mermaid import DEFAULT_KROKI_URL, render_mermaid_diagrams

if TYPE_CHECKING:
    from mkdocs_to_confluence.publisher.client import ConfluenceClient

# ── Data structures ───────────────────────────────────────────────────────────

_Action = Literal["create", "update", "skip", "section"]

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n?)---\s*\n?", re.DOTALL)


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
    *,
    quiet: bool = False,
) -> tuple[str, list[Path], tuple[str, ...], str | None]:
    """Run the full compile pipeline for one page.

    Returns
    -------
    tuple[str, list[Path], tuple[str, ...], str | None]
        ``(xhtml_string, attachment_paths, labels, confluence_status)``
    """
    if node.source_path is None:
        return "", [], (), None

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
    link_defs = collect_link_defs(preprocessed)
    preprocessed = expand_link_refs(preprocessed, link_defs)
    preprocessed = strip_link_defs(preprocessed)
    ir_nodes = parse(preprocessed)
    ir_nodes = apply_abbreviations(ir_nodes, abbrevs, page_text=preprocessed)
    ir_nodes, attachments = resolve_local_assets(
        ir_nodes,
        page_path=node.source_path,
        docs_dir=config.docs_dir,
    )
    mermaid_render = (config.confluence.mermaid_render if config.confluence else "kroki")
    if mermaid_render != "none":
        kroki_url = (
            mermaid_render[len("kroki:"):] if mermaid_render.startswith("kroki:")
            else DEFAULT_KROKI_URL
        )
        ir_nodes, mermaid_attachments = render_mermaid_diagrams(ir_nodes, kroki_url, quiet=quiet)
        attachments = attachments + mermaid_attachments
    effective_link_map = link_map if link_map is not None else {}
    if node.docs_path:
        ir_nodes = resolve_internal_links(ir_nodes, effective_link_map, node.docs_path)
    if front_matter is not None:
        ir_nodes = (front_matter,) + ir_nodes
    edit_url = config.page_edit_url(node.docs_path or "")
    site_url = config.page_site_url(node.docs_path or "")
    if edit_url or site_url:
        ir_nodes = attach_source_url(ir_nodes, edit_url or "", site_url)

    # Extract labels and confluence_status from FrontMatter node.
    labels: tuple[str, ...] = ()
    confluence_status: str | None = None
    for node_item in ir_nodes:
        if isinstance(node_item, FrontMatter):
            labels = node_item.labels
            confluence_status = node_item.confluence_status
            break

    xhtml = emit(ir_nodes)
    return xhtml, attachments, labels, confluence_status


def _xhtml_hash(xhtml: str) -> str:
    """Return a stable sha256 hex digest of the emitted XHTML string."""
    return hashlib.sha256(xhtml.encode()).hexdigest()


# ── Planning ──────────────────────────────────────────────────────────────────


def _find_section_index(node: NavNode) -> NavNode | None:
    """Return the first direct child whose docs_path ends with 'index.md'."""
    for child in node.children:
        if child.docs_path and child.docs_path.lower().endswith("index.md"):
            return child
    return None


def plan_publish(
    nav_nodes: list[NavNode],
    client: ConfluenceClient,
    config: MkDocsConfig,
    conf_config: ConfluenceConfig,
    *,
    space_id: str,
    quiet: bool = False,
) -> list[PageAction]:
    """Build a publish plan for the entire nav tree.

    Section nodes become native Confluence folders so the hierarchy is
    preserved visually.  The actual find-or-create for folders is deferred
    to execute time once parent folder IDs are known.
    """
    actions: list[PageAction] = []
    link_map = build_link_map(nav_nodes)
    if not quiet:
        print("Planning...")
    _plan_nodes(nav_nodes, client, config, space_id, conf_config.parent_page_id, False, actions, link_map, quiet=quiet)
    return actions


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
                        xhtml, attachments, labels, confluence_status = compile_page(
                            index_child, config, link_map, quiet=quiet
                        )
                        existing = client.find_page(space_id, clean_title)
                        xhtml_h = _xhtml_hash(xhtml)
                        if existing is not None and client.get_content_hash(str(existing["id"])) == xhtml_h:
                            if not quiet:
                                print(f"  unchanged  '{clean_title}'  (content unchanged)")
                            actions.append(PageAction(
                                node=node,
                                title=clean_title,
                                action="skip",
                                parent_id=parent_id,
                                parent_is_folder=parent_is_folder,
                                page_id=str(existing["id"]),
                                confluence_status=confluence_status,
                            ))
                            non_index = [c for c in node.children if c is not index_child]
                            _plan_nodes(
                                non_index, client, config, space_id,
                                str(existing["id"]), False, actions, link_map, quiet=quiet
                            )
                            continue
                        page_action = PageAction(
                            node=node,
                            title=clean_title,
                            action="create" if existing is None else "update",
                            parent_id=parent_id,
                            parent_is_folder=parent_is_folder,
                            xhtml=xhtml,
                            attachments=attachments,
                            labels=labels,
                            confluence_status=confluence_status,
                            page_id=str(existing["id"]) if existing is not None else None,
                            version=(
                                existing["version"]["number"] if existing is not None else None
                            ),
                            is_folder=False,
                            content_hash=xhtml_h,
                        )
                        actions.append(page_action)
                        # Recurse remaining children — index.md is already consumed.
                        non_index = [c for c in node.children if c is not index_child]
                        _plan_nodes(
                            non_index, client, config, space_id, None, False, actions, link_map, quiet=quiet
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
                xhtml, attachments, labels, confluence_status = compile_page(node, config, link_map, quiet=quiet)
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

            existing = client.find_page(space_id, clean_title)
            xhtml_h = _xhtml_hash(xhtml)
            if existing is not None and client.get_content_hash(str(existing["id"])) == xhtml_h:
                if not quiet:
                    print(f"  unchanged  '{clean_title}'  (content unchanged)")
                actions.append(
                    PageAction(
                        node=node,
                        title=clean_title,
                        action="skip",
                        parent_id=parent_id,
                        page_id=str(existing["id"]),
                        confluence_status=confluence_status,
                    )
                )
                continue

            page_action = PageAction(
                node=node,
                title=clean_title,
                action="create" if existing is None else "update",
                parent_id=parent_id,
                xhtml=xhtml,
                attachments=attachments,
                labels=labels,
                confluence_status=confluence_status,
                page_id=str(existing["id"]) if existing is not None else None,
                version=(
                    existing["version"]["number"] if existing is not None else None
                ),
                content_hash=xhtml_h,
            )
            actions.append(page_action)


# ── Execution ─────────────────────────────────────────────────────────────────


def _upload_assets(
    page_id: str,
    attachments: list[Path],
    docs_dir: Path,
    client: ConfluenceClient,
    *,
    quiet: bool = False,
) -> tuple[int, int, list[tuple[str, str]]]:
    """Upload attachments for one page **sequentially**.

    Confluence holds a page-level write lock while processing each attachment
    POST.  Submitting concurrent requests to the same page causes the second
    (and any later) transaction to be rolled back with HTTP 500 "transaction
    marked as rollback-only".

    Fetching the existing attachment listing once before the loop avoids
    redundant API calls and correctly determines create vs. update for each
    file.  Attachments whose local mtime is not newer than the Confluence
    ``version.createdAt`` timestamp are skipped — no re-upload needed.

    Returns ``(uploaded_count, skipped_count, errors)`` where errors is a list
    of ``(attachment_name, error_message)`` pairs.
    """
    pairs = [(_make_attachment_name(p, docs_dir), p) for p in attachments]
    uploaded = 0
    skipped = 0
    errors: list[tuple[str, str]] = []

    # Fetch once; reuse across all uploads (read-only).
    existing = client.list_attachments(page_id)

    for name, path in pairs:
        # Skip upload if local file is not newer than what Confluence already has.
        if name in existing:
            try:
                created_at = existing[name]["version"]["createdAt"]
                confluence_ts = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
                local_mtime = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                )
                if local_mtime <= confluence_ts:
                    if not quiet:
                        print(f"        skipping   {name} (unchanged)")
                    skipped += 1
                    continue
            except (KeyError, ValueError, OSError):
                pass  # can't compare — fall through to upload

        if not quiet:
            print(f"        uploading  {name}")
        try:
            client.upload_attachment(page_id, path, name, existing)
            uploaded += 1
        except Exception as exc:
            errors.append((name, str(exc)))

    return uploaded, skipped, errors


def _execute_folder_action(
    action: PageAction,
    client: ConfluenceClient,
    space_id: str,
    root_page_id: str | None,
    report: PublishReport,
    *,
    quiet: bool = False,
) -> None:
    """Handle folder create/find for a single folder action."""
    if action.page_id is not None:
        # Already found at plan time — reuse.
        report.updated += 1
    elif action.parent_is_folder or action.parent_id == root_page_id:
        # Parent is a Confluence folder, or this is a top-level section
        # directly under the configured root page — use native folder API.
        existing_folder = None
        if action.parent_id is not None:
            try:
                existing_folder = client.find_folder_under(
                    action.parent_id,
                    action.title,
                    parent_is_folder=action.parent_is_folder,
                )
            except Exception as find_exc:
                print(
                    f"  [warn] find_folder_under failed "
                    f"(parent_id={action.parent_id}): {find_exc}",
                    file=sys.stderr,
                )
        if existing_folder is not None:
            action.page_id = str(existing_folder["id"])
            report.updated += 1
        else:
            folder_parent = (
                action.parent_id if action.parent_is_folder else None
            )
            folder = client.create_folder(
                space_id, action.title, parent_id=folder_parent
            )
            action.page_id = str(folder["id"])
            report.created += 1
            if not quiet:
                print(
                    f"         folder id={action.page_id}"
                    f"  parent_id={action.parent_id}"
                    f"  parent_is_folder={action.parent_is_folder}"
                )
    else:
        # Parent is a dynamically-created page (e.g. a section-index page).
        # Confluence folders cannot be nested under pages — use a stub page.
        action.is_folder = False
        existing = client.find_page(space_id, action.title)
        if existing is not None:
            action.page_id = str(existing["id"])
            report.updated += 1
        else:
            stub = client.create_page(
                space_id, action.title, "", parent_id=action.parent_id,
            )
            action.page_id = str(stub["id"])
            report.created += 1


def _execute_page_action(
    action: PageAction,
    client: ConfluenceClient,
    space_id: str,
    report: PublishReport,
) -> None:
    """Handle create/update (with stale fallback) for a single page action."""
    if action.action == "create":
        page = client.create_page(
            space_id,
            action.title,
            action.xhtml or "",
            parent_id=action.parent_id,
        )
        action.page_id = str(page["id"])
        report.created += 1
        try:
            client.stamp_managed(action.page_id)
        except Exception:
            pass  # non-fatal
    elif action.action == "update":
        if action.page_id is None or action.version is None:
            raise RuntimeError(
                f"Update action for '{action.title}' is missing page_id or version"
            )
        try:
            client.update_page(
                action.page_id,
                action.title,
                action.xhtml or "",
                action.version + 1,
                parent_id=action.parent_id,
            )
            report.updated += 1
        except ConfluenceError as upd_exc:
            err = str(upd_exc)
            # 404 = page deleted; 400 "another space" = stale page_id
            # from a different Confluence space.  Both mean the existing
            # page can't be updated — fall back to create a fresh one.
            is_stale = "HTTP 404" in err or (
                "HTTP 400" in err and "another space" in err.lower()
            )
            if not is_stale:
                raise
            print(
                f"  [warn] update failed ({err[:80].strip()}) —"
                " stale page_id; falling back to create",
                file=sys.stderr,
            )
            action.page_id = None
            page = client.create_page(
                space_id,
                action.title,
                action.xhtml or "",
                parent_id=action.parent_id,
            )
            action.page_id = str(page["id"])
            report.created += 1
            try:
                client.stamp_managed(action.page_id)
            except Exception:
                pass  # non-fatal


def _wire_children(
    action: PageAction,
    action_by_node: dict[int, PageAction],
) -> None:
    """Propagate a section's resolved page_id to all its direct children."""
    if action.page_id is None:
        return
    for child_node in action.node.children:
        child_action = action_by_node.get(id(child_node))
        if child_action is not None:
            child_action.parent_id = action.page_id
            child_action.parent_is_folder = action.is_folder


def _post_process_action(
    action: PageAction,
    client: ConfluenceClient,
    *,
    full_width: bool,
    docs_dir: Path,
    report: PublishReport,
    space_key: str | None = None,
    quiet: bool = False,
) -> None:
    """Run all non-fatal post-create/update work for a single action."""
    # Store content hash after create/update so the next run can skip unchanged pages.
    if action.page_id and action.content_hash and action.action in ("create", "update"):
        try:
            client.set_content_hash(action.page_id, action.content_hash)
        except Exception:
            pass  # non-fatal

    # Set full-width layout on newly created or updated pages (not folders).
    if full_width and action.page_id and not action.is_folder:
        try:
            client.set_page_full_width(action.page_id)
        except Exception:
            pass  # non-fatal — page is published, layout is cosmetic

    # Apply labels (tags) from front matter — non-fatal on failure.
    if action.page_id and action.labels and not action.is_folder:
        try:
            client.set_page_labels(action.page_id, action.labels)
        except Exception:
            pass

    # Set Confluence page status (rough-draft / in-progress / etc.) — non-fatal.
    if action.page_id and action.confluence_status and not action.is_folder:
        try:
            client.set_page_status(action.page_id, action.confluence_status, space_key=space_key)
        except Exception as exc:
            # Always print status errors — user configured status explicitly
            print(f"  [warn] could not set page status '{action.confluence_status}': {exc}", file=sys.stderr)

    # Upload assets — skip files whose mtime is not newer than Confluence.
    if action.page_id and action.attachments:
        uploaded, asset_skipped, asset_errors = _upload_assets(
            action.page_id, action.attachments, docs_dir, client, quiet=quiet
        )
        report.assets_uploaded += uploaded
        report.assets_skipped += asset_skipped
        for name, msg in asset_errors:
            report.errors.append((f"{action.title} / {name}", msg))


def execute_publish(
    plan: list[PageAction],
    client: ConfluenceClient,
    *,
    dry_run: bool = False,
    space_id: str,
    space_key: str | None = None,
    docs_dir: Path,
    full_width: bool = True,
    root_page_id: str | None = None,
    prune: bool = False,
    quiet: bool = False,
) -> PublishReport:
    """Execute the publish plan.

    Pages are processed in nav order so parent sections are always created
    before their children.  Once a section's ``page_id`` is known (after
    create/update), all direct children in the plan have their ``parent_id``
    updated immediately.

    Attachments for each page are uploaded sequentially to avoid Confluence
    transaction rollbacks caused by concurrent writes to the same page.

    Returns a :class:`PublishReport` summarising what was created, updated,
    skipped, and how many assets were uploaded.
    """
    report = PublishReport()

    if dry_run:
        report.skipped = sum(1 for a in plan if a.action == "skip")
        report.created = sum(1 for a in plan if a.action == "create")
        report.updated = sum(1 for a in plan if a.action == "update")
        return report

    # Index: nav node id → PageAction, used to wire child parent_ids after
    # each section is created/updated.
    action_by_node: dict[int, PageAction] = {id(a.node): a for a in plan}

    active = [a for a in plan if a.action != "skip"]
    total = len(active)
    if not quiet:
        print(f"\nPublishing {total} page(s)...")
    counter = 0

    for action in plan:
        if action.action == "skip":
            report.skipped += 1
            # Still apply status even for unchanged pages.
            if action.page_id and action.confluence_status and not action.is_folder:
                try:
                    client.set_page_status(action.page_id, action.confluence_status, space_key=space_key)
                except Exception as exc:
                    if not quiet:
                        print(
                            f"  [warn] could not set page status '{action.confluence_status}': {exc}",
                            file=sys.stderr,
                        )
            continue

        counter += 1
        if not quiet:
            print(f"  [{counter}/{total}] {action.action:<6}  '{action.title}'")

        try:
            if action.is_folder:
                _execute_folder_action(action, client, space_id, root_page_id, report, quiet=quiet)
            else:
                _execute_page_action(action, client, space_id, report)
        except Exception as exc:
            report.errors.append((action.title, str(exc)))
            # Do NOT `continue` — all post-execute blocks below are guarded by
            # action.page_id checks, so they are safely skipped on failure.
            # Critically, child parent_id wiring must still run for section
            # pages whose children were planned with parent_id=None.

        if action.node.is_section and action.page_id:
            _wire_children(action, action_by_node)

        _post_process_action(
            action, client,
            full_width=full_width, docs_dir=docs_dir, space_key=space_key, report=report, quiet=quiet,
        )

    if prune and root_page_id:
        published_ids = {a.page_id for a in plan if a.page_id}
        _prune_orphans(client, root_page_id, published_ids, report, quiet=quiet)

    return report


def _prune_orphans(
    client: ConfluenceClient,
    root_page_id: str,
    published_ids: set[str],
    report: PublishReport,
    *,
    quiet: bool = False,
) -> None:
    """Delete managed descendant pages that are no longer in the publish plan.

    Only pages that carry the ``mk2conf-managed`` property are eligible for
    deletion — manually-created Confluence pages are left untouched.
    """
    try:
        all_descendants = client.get_descendant_ids(root_page_id)
    except Exception as exc:
        print(f"  [warn] prune: could not fetch descendants — {exc}", file=sys.stderr)
        return

    orphan_candidates = [pid for pid in all_descendants if pid not in published_ids]
    if not orphan_candidates:
        return

    if not quiet:
        print(f"\nPruning: checking {len(orphan_candidates)} orphan candidate(s)...")
    for page_id in orphan_candidates:
        try:
            if not client.is_managed(page_id):
                continue
            client.delete_page(page_id)
            report.pruned += 1
            if not quiet:
                print(f"  deleted orphan page {page_id}")
        except Exception as exc:
            print(f"  [warn] prune: failed to delete page {page_id} — {exc}", file=sys.stderr)
