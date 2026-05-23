"""Execution helpers for the nav-driven publish pipeline."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from mkdocs_to_confluence.publisher.client import ConfluenceError
from mkdocs_to_confluence.publisher.models import PageAction, PublishReport
from mkdocs_to_confluence.transforms.assets import _make_attachment_name

if TYPE_CHECKING:
    from mkdocs_to_confluence.publisher.client import ConfluenceClient


def _upload_assets(
    page_id: str,
    attachments: list[Path],
    docs_dir: Path,
    client: ConfluenceClient,
    *,
    quiet: bool = False,
) -> tuple[int, int, list[tuple[str, str]]]:
    """Upload attachments for one page sequentially."""
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
                version_message=action.version_message,
            )
            report.updated += 1
        except ConfluenceError as upd_exc:
            err = str(upd_exc)
            # 404 = page deleted; 400 "another space" = stale page_id
            # from a different Confluence space. Both mean the existing
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


def _apply_page_presentation(
    action: PageAction,
    client: ConfluenceClient,
    *,
    full_width: bool,
    space_key: str | None = None,
    suppress_full_width_errors: bool = False,
) -> None:
    """Apply page status and full-width presentation updates."""
    if action.page_id and action.confluence_status and not action.is_folder:
        try:
            print(f"  [status] setting '{action.confluence_status}' on page {action.page_id!r}...")
            client.set_page_status(action.page_id, action.confluence_status, space_key=space_key)
            print("  [status] ok")
        except Exception as exc:
            # Always print status errors — user configured status explicitly
            print(f"  [warn] could not set page status '{action.confluence_status}': {exc}")

    # Set full-width LAST — Confluence's state/label PUTs can reset the appearance property.
    if full_width and action.page_id and not action.is_folder:
        try:
            client.set_page_full_width(action.page_id)
        except Exception as exc:
            if not suppress_full_width_errors:
                print(f"  [warn] could not set full-width on page {action.page_id!r}: {exc}")


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

    # Apply labels (tags) from front matter — non-fatal on failure.
    if action.page_id and action.labels and not action.is_folder:
        try:
            client.set_page_labels(action.page_id, action.labels)
        except Exception:
            pass

    _apply_page_presentation(
        action,
        client,
        full_width=full_width,
        space_key=space_key,
        suppress_full_width_errors=True,
    )

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
    """Execute the publish plan."""
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
            _apply_page_presentation(action, client, full_width=full_width, space_key=space_key)
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
    """Delete managed descendant pages that are no longer in the publish plan."""
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
