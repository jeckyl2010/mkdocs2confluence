"""mk2conf — CLI entrypoint for mkdocs-to-confluence."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from mkdocs_to_confluence import __version__
from mkdocs_to_confluence.emitter.xhtml import configure_styles
from mkdocs_to_confluence.loader.config import load_config
from mkdocs_to_confluence.loader.nav import find_section, find_section_by_folder, flat_pages, resolve_nav
from mkdocs_to_confluence.loader.page import PageLoadError, find_page
from mkdocs_to_confluence.preview.render import render_index, render_page
from mkdocs_to_confluence.publisher.pipeline import compile_page
from mkdocs_to_confluence.transforms.internallinks import build_link_map


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mk2conf",
        description="Compile MkDocs markdown to native Confluence storage format.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mk2conf {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # --- preview ---
    preview = sub.add_parser(
        "preview",
        help="Compile a page (or whole section) and inspect the output — no Confluence API calls.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mk2conf preview --page index.md\n"
            "  mk2conf preview --page guide/setup.md --html --out /tmp/setup.html\n"
            "  mk2conf preview --section Guide\n"
            "\n"
            "  Either --page or --section is required.\n"
            "  Mermaid diagrams are rendered via Kroki unless 'mermaid_render: none' is set.\n"
        ),
    )
    preview.add_argument(
        "--config",
        metavar="PATH",
        default="mkdocs.yml",
        help="Path to mkdocs.yml (default: ./mkdocs.yml).",
    )
    preview.add_argument(
        "--page",
        metavar="PATH",
        default=None,
        help=(
            "Relative path to the markdown file to compile. "
            "Required unless --section is given."
        ),
    )
    preview.add_argument(
        "--out",
        metavar="FILE",
        default=None,
        help="Write output to FILE instead of stdout.",
    )
    preview.add_argument(
        "--html",
        action="store_true",
        help="Render macros as browser-viewable HTML instead of raw Confluence XHTML.",
    )
    preview.add_argument(
        "--section",
        metavar="NAME",
        default=None,
        help=(
            "Nav section to preview (slash-separated path, e.g. 'Guide' or 'Guide/Setup'). "
            "Without --page, renders all pages in the section as a browseable HTML index."
        ),
    )

    preview.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress per-item progress output; only the final summary and warnings are shown.",
    )

    # --- publish ---
    publish = sub.add_parser(
        "publish",
        help="Compile all pages and publish to Confluence.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Authentication (required):\n"
            "  Set one of these environment variables before running:\n"
            "    CONFLUENCE_API_TOKEN=<token>   (primary)\n"
            "    MK2CONF_TOKEN=<token>           (alias)\n"
            "\n"
            "  The token, email, base_url, space_key/parent_page_id must also be\n"
            "  configured in the 'confluence:' block of mkdocs.yml.\n"
        ),
    )
    publish.add_argument(
        "--config",
        metavar="PATH",
        default="mkdocs.yml",
        help="Path to mkdocs.yml (default: ./mkdocs.yml).",
    )
    publish.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the sync plan and print it without touching Confluence.",
    )
    publish.add_argument(
        "--page",
        metavar="PATH",
        default=None,
        help="Relative path to a single markdown file to publish (optional).",
    )
    publish.add_argument(
        "--section",
        metavar="NAME",
        default=None,
        help=(
            "Publish only a nav section subtree (slash-separated path, e.g. 'Guide' or "
            "'Guide/Setup'). Cannot be combined with --page."
        ),
    )
    publish.add_argument(
        "--report",
        metavar="FILE",
        default=None,
        help="Write a JSON publish report to FILE after the run.",
    )
    publish.add_argument(
        "--prune",
        action="store_true",
        help=(
            "Delete managed Confluence pages that are no longer in the MkDocs nav. "
            "Only pages stamped by mk2conf are eligible — manually-created pages are never deleted. "
            "Ignored when --page or --section is used."
        ),
    )

    publish.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress per-item progress output; only the final summary and warnings are shown.",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if sys.stdout.isatty():
        print(f"mk2conf {__version__}")

    try:
        if args.command == "preview":
            _cmd_preview(args)
        elif args.command == "publish":
            _cmd_publish(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


def _parse_out_path(out_arg: str | None) -> tuple[Path, str]:
    """Derive (output_dir, index_filename) from an --out value.

    Examples
    --------
    ``None``            → ``(cwd, "preview.html")``
    ``"/tmp/test.html"`` → ``(Path("/tmp"), "test.html")``
    """
    if out_arg is None:
        return Path(".").resolve(), "preview.html"
    p = Path(out_arg).resolve()
    return p.parent, p.name


def _cmd_preview(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    configure_styles(config.extra_styles)

    nodes = resolve_nav(config)

    section_given = bool(getattr(args, "section", None))
    page_given = bool(args.page)

    if not section_given and not page_given:
        print("error: --page is required when --section is not given.", file=sys.stderr)
        sys.exit(1)

    # Resolve section subtree (both single-page and section-mode use this)
    if section_given:
        section_node = find_section(nodes, args.section) or find_section_by_folder(nodes, args.section)
        if section_node is None:
            print(f"error: section '{args.section}' not found in nav.", file=sys.stderr)
            sys.exit(1)
        nodes = [section_node]

    # ── Section mode: render every page in the section ───────────────────────
    if section_given and not page_given:
        pages = flat_pages(nodes)
        if not pages:
            print("error: section contains no pages.", file=sys.stderr)
            sys.exit(1)

        out_dir, index_name = _parse_out_path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        link_map = build_link_map(nodes)
        # Map page title → html filename for cross-page link rewriting
        page_link_map = {
            node.title: f"{Path(node.docs_path).stem}.html"
            for node in pages
            if node.docs_path is not None
        }

        rendered: list[tuple[str, str]] = []  # (title, html_filename)
        for node in pages:
            html_name = page_link_map.get(node.title, f"{Path(node.docs_path or node.title).stem}.html")
            try:
                xhtml, _attachments, _labels = compile_page(node, config, link_map, quiet=args.quiet)
            except PageLoadError as exc:
                print(f"  warning: skipping '{node.title}': {exc}", file=sys.stderr)
                continue
            html = render_page(xhtml, page=node.title, page_link_map=page_link_map)
            (out_dir / html_name).write_text(html, encoding="utf-8")
            rendered.append((node.title, html_name))

        index_html = render_index(args.section, rendered)
        index_path = out_dir / index_name
        index_path.write_text(index_html, encoding="utf-8")

        url = f"file://{index_path}"
        print(f"Section preview ({len(rendered)} pages): {url}")
        webbrowser.open(url)
        return

    # ── Single-page mode ─────────────────────────────────────────────────────
    page_node = find_page(nodes, args.page)
    if page_node is None:
        print(f"error: page '{args.page}' not found in nav.", file=sys.stderr)
        sys.exit(1)

    try:
        link_map = build_link_map(nodes)
        xhtml, _attachments, _labels = compile_page(page_node, config, link_map, quiet=args.quiet)
    except PageLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    output = render_page(xhtml, page=args.page) if args.html else xhtml

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.write_text(output, encoding="utf-8")
        if args.html:
            url = f"file://{out_path}"
            print(url)
            webbrowser.open(url)
        else:
            print(f"Written to {out_path}")
    else:
        print(output)


def _cmd_publish(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    configure_styles(config.extra_styles)

    conf_config = config.confluence
    if conf_config is None:
        print("error: no 'confluence:' section in mkdocs.yml", file=sys.stderr)
        sys.exit(1)

    token = conf_config.token
    if not token:
        print(
            "error: Confluence API token not set. Set CONFLUENCE_API_TOKEN env var.",
            file=sys.stderr,
        )
        sys.exit(1)

    nav_nodes = resolve_nav(config)

    # Section filter (--section takes precedence; --page is a secondary filter)
    if getattr(args, "section", None):
        section_node = find_section(nav_nodes, args.section) or find_section_by_folder(nav_nodes, args.section)
        if section_node is None:
            print(f"error: section '{args.section}' not found in nav.", file=sys.stderr)
            sys.exit(1)
        nav_nodes = [section_node]

    # Single-page filter
    if getattr(args, "page", None):
        node = find_page(nav_nodes, args.page)
        if node is None:
            print(f"error: page '{args.page}' not found in nav.", file=sys.stderr)
            sys.exit(1)
        nav_nodes = [node]

    if args.dry_run:
        # When a section is given, show what node was matched so the user can
        # verify the section resolved correctly (section vs. leaf page).
        if getattr(args, "section", None) and nav_nodes:
            matched = nav_nodes[0]
            node_kind = "section" if matched.is_section else "page"
            child_count = len(matched.children) if matched.is_section else 0
            detail = f"{child_count} direct children" if matched.is_section else "leaf page"
            print(f"Section matched: '{matched.title}' ({node_kind}, {detail})")

        pages = flat_pages(nav_nodes)
        print(f"Dry run: would publish {len(pages)} page(s) to {conf_config.base_url}")
        for page in pages:
            print(f"  {page.docs_path} → '{page.title}'")
        return

    from mkdocs_to_confluence.publisher.client import ConfluenceClient, ConfluenceError
    from mkdocs_to_confluence.publisher.pipeline import execute_publish, plan_publish

    try:
        with ConfluenceClient(conf_config) as client:
            if conf_config.parent_page_id:
                # parent_page_id is the authoritative anchor — derive space from it.
                # space_key is only used when no parent_page_id is configured.
                space_id = client.get_space_id_from_page(conf_config.parent_page_id)
            elif conf_config.space_key:
                space_id = client.get_space_id(conf_config.space_key)
            else:
                print(
                    "error: cannot determine space — set 'space_key' or 'parent_page_id' in mkdocs.yml",
                    file=sys.stderr,
                )
                sys.exit(1)
            plan = plan_publish(nav_nodes, client, config, conf_config, space_id=space_id, quiet=args.quiet)
            # --prune is silently disabled for partial publishes (--page / --section)
            # because published_ids would only cover the subset, not the full nav.
            partial = bool(getattr(args, "page", None) or getattr(args, "section", None))
            report = execute_publish(
                plan, client, dry_run=False, space_id=space_id,
                docs_dir=config.docs_dir, full_width=conf_config.full_width,
                root_page_id=conf_config.parent_page_id,
                prune=getattr(args, "prune", False) and not partial,
                quiet=args.quiet,
            )
    except ConfluenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(str(report))

    if getattr(args, "report", None):
        import json as _json

        report_data = {
            "created": report.created,
            "updated": report.updated,
            "skipped": report.skipped,
            "assets_uploaded": report.assets_uploaded,
            "assets_skipped": report.assets_skipped,
            "errors": [{"page": t, "error": m} for t, m in report.errors],
        }
        Path(args.report).write_text(_json.dumps(report_data, indent=2), encoding="utf-8")
        print(f"Report written to {args.report}")

    if report.errors:
        sys.exit(1)
