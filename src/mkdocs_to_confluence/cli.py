"""mk2conf — CLI entrypoint for mkdocs-to-confluence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mkdocs_to_confluence import __version__
from mkdocs_to_confluence.loader.config import load_config
from mkdocs_to_confluence.emitter.xhtml import configure_styles
from mkdocs_to_confluence.loader.nav import find_section, find_section_by_folder, flat_pages, resolve_nav
from mkdocs_to_confluence.loader.page import PageLoadError, find_page
from mkdocs_to_confluence.preview.render import render_page
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
        help="Compile a single page and print Confluence XHTML to stdout (no network).",
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
        required=True,
        help="Relative path to the markdown file to compile.",
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
        help="Restrict link map to a nav section (slash-separated path, e.g. 'Guide/Setup').",
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

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    print(f"mk2conf {__version__}")

    if args.command == "preview":
        _cmd_preview(args)
    elif args.command == "publish":
        _cmd_publish(args)


def _cmd_preview(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    configure_styles(config.extra_styles)

    nodes = resolve_nav(config)

    # Optionally scope link resolution to a section subtree
    if getattr(args, "section", None):
        section_node = find_section(nodes, args.section) or find_section_by_folder(nodes, args.section)
        if section_node is None:
            print(f"error: section '{args.section}' not found in nav.", file=sys.stderr)
            sys.exit(1)
        nodes = [section_node]

    node = find_page(nodes, args.page)
    if node is None:
        print(f"error: page '{args.page}' not found in nav.", file=sys.stderr)
        sys.exit(1)

    try:
        link_map = build_link_map(nodes)
        xhtml, _attachments = compile_page(node, config, link_map)
    except PageLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    output = render_page(xhtml, page=args.page) if args.html else xhtml

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Written to {args.out}")
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

    from mkdocs_to_confluence.publisher.client import ConfluenceClient
    from mkdocs_to_confluence.publisher.pipeline import execute_publish, plan_publish

    with ConfluenceClient(conf_config) as client:
        if conf_config.space_key:
            space_id = client.get_space_id(conf_config.space_key)
        elif conf_config.parent_page_id:
            space_id = client.get_space_id_from_page(conf_config.parent_page_id)
        else:
            print("error: cannot determine space — set 'space_key' or 'parent_page_id' in mkdocs.yml", file=sys.stderr)
            sys.exit(1)
        plan = plan_publish(nav_nodes, client, config, conf_config, space_id=space_id)
        report = execute_publish(plan, client, dry_run=False, space_id=space_id, docs_dir=config.docs_dir, full_width=conf_config.full_width)

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
