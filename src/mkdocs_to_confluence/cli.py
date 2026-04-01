"""mk2conf — CLI entrypoint for mkdocs-to-confluence."""

from __future__ import annotations

import argparse
import sys

from mkdocs_to_confluence import __version__


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
    raise NotImplementedError("preview command is not yet implemented (milestone 4).")


def _cmd_publish(args: argparse.Namespace) -> None:
    raise NotImplementedError("publish command is not yet implemented (milestone 5).")
