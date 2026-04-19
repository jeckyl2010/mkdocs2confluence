"""mk2conf — CLI entrypoint for mkdocs-to-confluence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mkdocs_to_confluence import __version__
from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.loader.config import load_config
from mkdocs_to_confluence.loader.nav import resolve_nav
from mkdocs_to_confluence.loader.page import PageLoadError, find_page, load_page
from mkdocs_to_confluence.parser.markdown import parse
from mkdocs_to_confluence.preview.render import render_page
from mkdocs_to_confluence.preprocess.abbrevs import extract_abbreviations, strip_abbreviation_defs
from mkdocs_to_confluence.preprocess.frontmatter import extract_front_matter
from mkdocs_to_confluence.preprocess.includes import preprocess_includes, strip_html_comments, strip_unsupported_html
from mkdocs_to_confluence.transforms.abbrevs import apply_abbreviations


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

    # --- publish ---
    publish = sub.add_parser(
        "publish",
        help="Compile all pages and publish to Confluence.",
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

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "preview":
        _cmd_preview(args)
    elif args.command == "publish":
        _cmd_publish(args)


def _cmd_preview(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    config = load_config(config_path)

    nodes = resolve_nav(config)
    node = find_page(nodes, args.page)
    if node is None:
        print(f"error: page '{args.page}' not found in nav.", file=sys.stderr)
        sys.exit(1)

    try:
        raw = load_page(node)
    except PageLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    preprocessed = preprocess_includes(
        raw,
        source_path=node.source_path,  # type: ignore[arg-type]
        docs_dir=config.docs_dir,
    )
    preprocessed = strip_unsupported_html(preprocessed)
    preprocessed = strip_html_comments(preprocessed)
    front_matter, preprocessed = extract_front_matter(preprocessed)
    abbrevs = extract_abbreviations(preprocessed)
    preprocessed = strip_abbreviation_defs(preprocessed)
    ir_nodes = parse(preprocessed)
    ir_nodes = apply_abbreviations(ir_nodes, abbrevs, page_text=preprocessed)
    if front_matter is not None:
        ir_nodes = (front_matter,) + ir_nodes
    xhtml = emit(ir_nodes)

    output = render_page(xhtml, page=args.page) if args.html else xhtml

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Written to {args.out}")
    else:
        print(output)


def _cmd_publish(args: argparse.Namespace) -> None:
    raise NotImplementedError("publish command is not yet implemented (milestone 5).")
