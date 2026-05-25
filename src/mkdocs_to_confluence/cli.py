"""mk2conf — CLI entrypoint for mkdocs-to-confluence."""

from __future__ import annotations

import argparse
import sys
import tempfile
import webbrowser
from pathlib import Path

from mkdocs_to_confluence import __version__
from mkdocs_to_confluence.emitter.xhtml import configure_styles
from mkdocs_to_confluence.loader.config import load_config
from mkdocs_to_confluence.loader.nav import find_section, find_section_by_folder, flat_pages, resolve_nav
from mkdocs_to_confluence.loader.page import PageLoadError, find_page
from mkdocs_to_confluence.preview.render import inject_livereload, render_index, render_page
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

    preview.add_argument(
        "--watch",
        action="store_true",
        help=(
            "Start a local server on http://localhost:8765, open the browser, "
            "and automatically rebuild when any .md file changes. Implies --html."
        ),
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

    # --- pdf ---
    pdf = sub.add_parser(
        "pdf",
        help="Export a nav section (or single page) to a PDF document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Requires WeasyPrint:  pip install mkdocs-to-confluence[pdf]\n"
            "System packages also required (pango, cairo):\n"
            "  macOS:   brew install pango\n"
            "  Ubuntu:  apt install libpango-1.0-0 libpangoft2-1.0-0\n"
            "  Windows: choco install gtk-runtime\n"
            "\n"
            "Examples:\n"
            "  mk2conf pdf --config mkdocs.yml --section Guide\n"
            "  mk2conf pdf --config mkdocs.yml --section Guide --out release.pdf\n"
            "  mk2conf pdf --config mkdocs.yml --page index.md --out index.pdf\n"
        ),
    )
    pdf.add_argument(
        "--config",
        metavar="PATH",
        default="mkdocs.yml",
        help="Path to mkdocs.yml (default: ./mkdocs.yml).",
    )
    pdf.add_argument(
        "--section",
        metavar="SECTION",
        default=None,
        help="Nav section to export (slash-separated path, e.g. 'Guide' or 'Guide/Setup').",
    )
    pdf.add_argument(
        "--page",
        metavar="PATH",
        default=None,
        help="Relative path to a single markdown file to export.",
    )
    pdf.add_argument(
        "--out",
        metavar="FILE",
        default=None,
        help="Output PDF path (default: <section-or-page>.pdf in the current directory).",
    )
    pdf.add_argument(
        "--author",
        metavar="NAME",
        default="",
        help="Author name shown on the cover page.",
    )
    pdf.add_argument(
        "--doc-version",
        metavar="VERSION",
        default="",
        help="Version string shown on the cover page (e.g. 'v1.2').",
    )
    pdf.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress per-item progress output.",
    )

    # --- sync-comments ---
    sc = sub.add_parser(
        "sync-comments",
        help="Sync open Confluence comments to GitHub review PRs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Requires github_repo and github_token (or GITHUB_TOKEN env var) in mkdocs.yml.\n"
            "\n"
            "Examples:\n"
            "  mk2conf sync-comments                     # sync new comments → PRs\n"
            "  mk2conf sync-comments --check-merges      # resolve merged PRs in Confluence\n"
            "  mk2conf sync-comments --dry-run           # preview without making changes\n"
        ),
    )
    sc.add_argument(
        "--config",
        metavar="PATH",
        default="mkdocs.yml",
        help="Path to mkdocs.yml (default: ./mkdocs.yml).",
    )
    sc.add_argument(
        "--check-merges",
        action="store_true",
        help="Check tracked PRs for merges and resolve their Confluence comments.",
    )
    sc.add_argument(
        "--force",
        action="store_true",
        help="Re-sync pages that already have an open review PR.",
    )
    sc.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be synced without creating branches, PRs, or review threads.",
    )
    sc.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output.",
    )

    # --- install-skill ---
    is_ = sub.add_parser(
        "install-skill",
        help="Install the mkdocs-changelog AI skill into detected tool directories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Detected targets (all installed when no --tool given):\n"
            "  hermes        ~/.hermes/skills/tooling/mkdocs-changelog/SKILL.md\n"
            "  github-skills .github/skills/tooling/mkdocs-changelog/SKILL.md\n"
            "  claude        .claude/commands/changelog.md  (frontmatter stripped)\n"
            "  copilot       .github/instructions/mk2conf-changelog.instructions.md\n"
            "  cursor        .cursor/rules/mk2conf-changelog.mdc\n"
            "\n"
            "Examples:\n"
            "  mk2conf install-skill\n"
            "  mk2conf install-skill --tool claude\n"
            "  mk2conf install-skill --tool hermes\n"
        ),
    )
    is_.add_argument(
        "--tool",
        metavar="NAME",
        default=None,
        choices=["hermes", "github-skills", "claude", "copilot", "cursor"],
        help="Install only to a specific tool (hermes, github-skills, claude, copilot, cursor).",
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
        elif args.command == "pdf":
            _cmd_pdf(args)
        elif args.command == "sync-comments":
            _cmd_sync_comments(args)
        elif args.command == "install-skill":
            _cmd_install_skill(args)
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

    all_nodes = resolve_nav(config)

    section_given = bool(getattr(args, "section", None))
    page_given = bool(args.page)
    watch = getattr(args, "watch", False)

    if watch:
        args.html = True  # --watch always implies --html

    if not section_given and not page_given:
        print("error: --page is required when --section is not given.", file=sys.stderr)
        sys.exit(1)

    # Resolve section subtree (both single-page and section-mode use this)
    nodes = all_nodes
    if section_given:
        section_node = find_section(all_nodes, args.section) or find_section_by_folder(all_nodes, args.section)
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

        if watch and args.out is None:
            out_dir = Path(tempfile.mkdtemp(prefix="mk2conf-preview-"))
            index_name = "index.html"
        else:
            out_dir, index_name = _parse_out_path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        link_map = build_link_map(all_nodes)
        page_link_map = {
            node.title: f"{Path(node.docs_path).stem}.html"
            for node in pages
            if node.docs_path is not None
        }

        def _build_section_pages(*, livereload: bool = False) -> list[tuple[str, str]]:
            result: list[tuple[str, str]] = []
            for node in pages:
                html_name = page_link_map.get(node.title, f"{Path(node.docs_path or node.title).stem}.html")
                try:
                    xhtml, _a, _l, _s, _vm = compile_page(node, config, link_map, quiet=args.quiet)
                except PageLoadError as exc:
                    print(f"  warning: skipping '{node.title}': {exc}", file=sys.stderr)
                    continue
                html = render_page(xhtml, page=node.title, page_link_map=page_link_map)
                if livereload:
                    html = inject_livereload(html)
                (out_dir / html_name).write_text(html, encoding="utf-8")
                result.append((node.title, html_name))
            return result

        rendered = _build_section_pages(livereload=watch)
        index_html = render_index(args.section, rendered)
        index_path = out_dir / index_name
        index_path.write_text(index_html, encoding="utf-8")

        if watch:
            from mkdocs_to_confluence.preview.server import bump_version, start_server, watch_and_rebuild

            start_server(out_dir, port=8765)
            url = "http://localhost:8765"
            print(f"Watching for changes. Press Ctrl+C to stop.\n{url}")
            webbrowser.open(url)

            def _rebuild() -> None:
                new_rendered = _build_section_pages(livereload=True)
                new_index = render_index(args.section, new_rendered)
                index_path.write_text(new_index, encoding="utf-8")
                bump_version()

            try:
                watch_and_rebuild(config.docs_dir, _rebuild)
            except KeyboardInterrupt:
                print("\nStopped.")
            return

        url = f"file://{index_path}"
        print(f"Section preview ({len(rendered)} pages): {url}")
        webbrowser.open(url)
        return

    # ── Single-page mode ─────────────────────────────────────────────────────
    page_node = find_page(nodes, args.page)
    if page_node is None:
        print(f"error: page '{args.page}' not found in nav.", file=sys.stderr)
        sys.exit(1)

    link_map = build_link_map(nodes)

    if watch:
        from mkdocs_to_confluence.preview.server import bump_version, start_server, watch_and_rebuild

        out_dir = Path(args.out).resolve() if args.out else Path(tempfile.mkdtemp(prefix="mk2conf-preview-"))
        html_name = "preview.html"
        out_path = out_dir / html_name

        def _build_page() -> None:
            try:
                xhtml, _a, _l, _s, _vm = compile_page(page_node, config, link_map, quiet=True)
            except PageLoadError as exc:
                print(f"  warning: {exc}", file=sys.stderr)
                return
            html = inject_livereload(render_page(xhtml, page=args.page))
            out_path.write_text(html, encoding="utf-8")

        _build_page()
        start_server(out_dir, port=8765)
        url = "http://localhost:8765"
        print(f"Watching for changes. Press Ctrl+C to stop.\n{url}")
        webbrowser.open(url)

        def _rebuild_page() -> None:
            _build_page()
            bump_version()

        try:
            watch_and_rebuild(config.docs_dir, _rebuild_page)
        except KeyboardInterrupt:
            print("\nStopped.")
        return

    try:
        xhtml, _attachments, _labels, _status, _vm = compile_page(page_node, config, link_map, quiet=args.quiet)
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

    all_nav_nodes = resolve_nav(config)
    nav_nodes = all_nav_nodes

    # Section filter (--section takes precedence; --page is a secondary filter)
    if getattr(args, "section", None):
        section_node = find_section(all_nav_nodes, args.section) or find_section_by_folder(all_nav_nodes, args.section)
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

    partial = bool(getattr(args, "page", None) or getattr(args, "section", None))

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
        if conf_config.changelog_file and not partial:
            from mkdocs_to_confluence.publisher.changelog import _extract_title
            cl_path = config.docs_dir / conf_config.changelog_file
            cl_title = _extract_title(cl_path) or "What's New"
            print(f"  {conf_config.changelog_file} → '{cl_title}'  (changelog, top-level)")
        return

    from mkdocs_to_confluence.publisher.changelog import publish_changelog
    from mkdocs_to_confluence.publisher.client import ConfluenceClient, ConfluenceError
    from mkdocs_to_confluence.publisher.pipeline import execute_publish, plan_publish

    try:
        with ConfluenceClient(conf_config) as client:
            if conf_config.parent_page_id:
                # parent_page_id is the authoritative anchor — derive space from it.
                space_id = client.get_space_id_from_page(conf_config.parent_page_id)
            elif conf_config.space_key:
                space_id = client.get_space_id(conf_config.space_key)
            else:
                print(
                    "error: cannot determine space — set 'space_key' or 'parent_page_id' in mkdocs.yml",
                    file=sys.stderr,
                )
                sys.exit(1)
            plan = plan_publish(
                nav_nodes, client, config, conf_config,
                space_id=space_id, quiet=args.quiet, full_nav_nodes=all_nav_nodes,
            )
            report = execute_publish(
                plan, client, dry_run=False, space_id=space_id,
                space_key=conf_config.space_key,
                docs_dir=config.docs_dir, full_width=conf_config.full_width,
                root_page_id=conf_config.parent_page_id,
                prune=getattr(args, "prune", False) and not partial,
                quiet=args.quiet,
            )
            # Changelog is a pinned top-level page — always publish on full runs,
            # skip on partial runs (--page / --section) like all other publish behaviour.
            if not partial:
                publish_changelog(
                    config, conf_config, client, space_id,
                    space_key=conf_config.space_key, quiet=args.quiet,
                )
    except ConfluenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(str(report))

    # Write page map so sync-comments can match source files to Confluence pages.
    # Always merge into the existing map so partial runs (--page/--section) and
    # multiple configs pointing to the same repo root all accumulate correctly.
    import json as _json_pm
    try:
        repo_root = config_path.parent
        try:
            docs_rel = config.docs_dir.relative_to(repo_root)
        except ValueError:
            docs_rel = Path("docs")
        new_entries = {
            str(docs_rel / action.node.docs_path): action.page_id
            for action in plan
            if action.node.docs_path and action.page_id and not action.is_folder
        }
        pm_path = repo_root / ".mk2conf-pages.json"
        existing: dict[str, str] = {}
        if pm_path.exists():
            try:
                existing = _json_pm.loads(pm_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.update(new_entries)
        pm_path.write_text(_json_pm.dumps(existing, indent=2), encoding="utf-8")
        if not getattr(args, "quiet", False):
            print(f"Page map: {len(existing)} page(s) → {pm_path.name}")
    except Exception as exc:
        print(f"  [warn] could not write page map: {exc}", file=sys.stderr)

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


def _cmd_install_skill(args: argparse.Namespace) -> None:
    from mkdocs_to_confluence.skill_installer import install_skill

    installed = install_skill(tool=getattr(args, "tool", None))

    if not installed:
        print(
            "No AI tool directories detected and no --tool specified.\n"
            "Run with --tool to install to a specific tool, e.g.:\n"
            "  mk2conf install-skill --tool claude",
            file=sys.stderr,
        )
        sys.exit(1)

    for tool_name, dest in installed:
        print(f"  installed  [{tool_name}]  {dest}")

    if any(name == "fallback" for name, _ in installed):
        print(
            "\nNo AI tool directories were detected. Skill written to .mk2conf/changelog-skill.md.\n"
            "Copy its contents to your AI tool's custom instructions or skill directory.",
        )


def _cmd_pdf(args: argparse.Namespace) -> None:
    # On macOS with uv/non-system Python, Homebrew libs are not on the dyld search
    # path.  Re-exec once with DYLD_LIBRARY_PATH set — the sentinel prevents loops.
    import os
    if sys.platform == "darwin" and not os.environ.get("_MK2CONF_DYLD_SET"):
        brew_lib = "/opt/homebrew/lib"
        if os.path.isdir(brew_lib):
            current = os.environ.get("DYLD_LIBRARY_PATH", "")
            if brew_lib not in current:
                new_path = f"{brew_lib}:{current}" if current else brew_lib
                os.execve(
                    sys.argv[0],
                    sys.argv,
                    {**os.environ, "DYLD_LIBRARY_PATH": new_path, "_MK2CONF_DYLD_SET": "1"},
                )

    from mkdocs_to_confluence.pdf.generator import write_pdf
    from mkdocs_to_confluence.pdf.render import build_pdf_html

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    configure_styles(config.extra_styles)

    nodes = resolve_nav(config)

    section_given = bool(getattr(args, "section", None))
    page_given = bool(getattr(args, "page", None))

    if not section_given and not page_given:
        print("error: --section or --page is required.", file=sys.stderr)
        sys.exit(1)

    if section_given and page_given:
        print("error: --section and --page cannot be combined.", file=sys.stderr)
        sys.exit(1)

    if section_given:
        section_node = find_section(nodes, args.section) or find_section_by_folder(nodes, args.section)
        if section_node is None:
            print(f"error: section '{args.section}' not found in nav.", file=sys.stderr)
            sys.exit(1)
        nodes = [section_node]
        pages = flat_pages(nodes)
        title = args.section
        default_out = f"{args.section.replace('/', '-')}.pdf"
    else:
        page_node = find_page(nodes, args.page)
        if page_node is None:
            print(f"error: page '{args.page}' not found in nav.", file=sys.stderr)
            sys.exit(1)
        pages = [page_node]
        title = page_node.title
        default_out = f"{Path(args.page).stem}.pdf"

    if not pages:
        print("error: no pages found.", file=sys.stderr)
        sys.exit(1)

    link_map = build_link_map(nodes)
    chapters: list[tuple[str, str]] = []
    for node in pages:
        try:
            xhtml, _a, _l, _s, _vm = compile_page(node, config, link_map, quiet=args.quiet)
        except PageLoadError as exc:
            print(f"  warning: skipping '{node.title}': {exc}", file=sys.stderr)
            continue
        chapters.append((node.title, xhtml))

    if not chapters:
        print("error: no pages compiled successfully.", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"  building PDF  {len(chapters)} page(s)…")

    combined_html = build_pdf_html(
        title,
        chapters,
        author=getattr(args, "author", ""),
        version=getattr(args, "doc_version", ""),
    )

    out_path = Path(args.out).resolve() if args.out else Path(default_out).resolve()

    try:
        write_pdf(combined_html, out_path)
    except (ImportError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"PDF written to {out_path}")


def _cmd_sync_comments(args: argparse.Namespace) -> None:
    from mkdocs_to_confluence.publisher.client import ConfluenceClient, ConfluenceError
    from mkdocs_to_confluence.sync.command import check_and_resolve_merges, run_sync_comments
    from mkdocs_to_confluence.sync.github import GitHubReviewClient

    config_path = Path(args.config).resolve()
    config = load_config(config_path)

    conf = config.confluence
    if conf is None:
        print("error: no 'confluence:' section in mkdocs.yml", file=sys.stderr)
        sys.exit(1)

    if not conf.token:
        print("error: Confluence API token not set. Set CONFLUENCE_API_TOKEN env var.", file=sys.stderr)
        sys.exit(1)

    if not conf.github_repo:
        print(
            "error: 'confluence.github_repo' is required for sync-comments (e.g. 'owner/repo').",
            file=sys.stderr,
        )
        sys.exit(1)

    if not conf.github_token:
        print(
            "error: GitHub token not set. Set GITHUB_TOKEN env var or 'confluence.github_token' in mkdocs.yml.",
            file=sys.stderr,
        )
        sys.exit(1)

    review_client = GitHubReviewClient(conf.github_repo, conf.github_token)
    config_dir = config_path.parent

    try:
        with ConfluenceClient(conf) as confluence_client:
            if args.check_merges:
                check_and_resolve_merges(
                    config_dir=config_dir,
                    confluence_client=confluence_client,
                    review_client=review_client,
                    quiet=args.quiet,
                )
            else:
                run_sync_comments(
                    config=config,
                    config_dir=config_dir,
                    confluence_client=confluence_client,
                    review_client=review_client,
                    force=args.force,
                    dry_run=args.dry_run,
                    quiet=args.quiet,
                )
    except ConfluenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
