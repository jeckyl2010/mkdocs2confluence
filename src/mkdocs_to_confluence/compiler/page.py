"""Page compilation pipeline for MkDocs-to-Confluence."""

from __future__ import annotations

from mkdocs_to_confluence.compiler.models import CompileResult
from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import ChildrenMacro, FrontMatter, SourceFooter
from mkdocs_to_confluence.loader.config import MkDocsConfig
from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.loader.page import load_page
from mkdocs_to_confluence.parser.markdown import parse, parse_inline
from mkdocs_to_confluence.preprocess.abbrevs import (
    extract_abbreviations,
    strip_abbreviation_defs,
)
from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions
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
from mkdocs_to_confluence.transforms._kroki import DEFAULT_KROKI_URL
from mkdocs_to_confluence.transforms.abbrevs import apply_abbreviations
from mkdocs_to_confluence.transforms.admonition_titles import (
    strip_links_in_admonition_titles,
)
from mkdocs_to_confluence.transforms.assets import resolve_local_assets
from mkdocs_to_confluence.transforms.attachment_previews import (
    resolve_attachment_previews,
)
from mkdocs_to_confluence.transforms.captions import resolve_captions
from mkdocs_to_confluence.transforms.editlink import attach_source_url
from mkdocs_to_confluence.transforms.footer import build_source_footer
from mkdocs_to_confluence.transforms.internallinks import resolve_internal_links
from mkdocs_to_confluence.transforms.mermaid import render_mermaid_diagrams
from mkdocs_to_confluence.transforms.plantuml import render_plantuml_diagrams


def compile_page(
    node: NavNode,
    config: MkDocsConfig,
    link_map: dict[str, str] | None = None,
    *,
    is_section_index: bool = False,
    quiet: bool = False,
) -> CompileResult:
    """Run the full compile pipeline for one page and return a typed result."""
    if node.source_path is None:
        return CompileResult(xhtml="")

    raw = load_page(node)

    preprocessed = preprocess_includes(
        raw,
        source_path=node.source_path,
        docs_dir=config.docs_dir,
    )
    preprocessed = strip_unsupported_html(preprocessed)
    preprocessed = rewrite_figure_captions(preprocessed)
    preprocessed = strip_html_comments(preprocessed)
    preprocessed = strip_icon_shortcodes(preprocessed)
    exclude_properties = (
        config.confluence.exclude_properties if config.confluence else ()
    )
    front_matter, preprocessed = extract_front_matter(
        preprocessed, exclude_properties=exclude_properties
    )
    abbrevs = extract_abbreviations(preprocessed)
    preprocessed = strip_abbreviation_defs(preprocessed)
    link_defs = collect_link_defs(preprocessed)
    preprocessed = expand_link_refs(preprocessed, link_defs)
    preprocessed = strip_link_defs(preprocessed)
    ir_nodes = parse(preprocessed)
    ir_nodes = strip_links_in_admonition_titles(ir_nodes, node.docs_path or "")
    if is_section_index:
        ir_nodes = ir_nodes + (ChildrenMacro(),)
    # Parse definitions as inline markdown so links etc. survive into the glossary.
    parsed_abbrevs = {abbr: parse_inline(defn) for abbr, defn in abbrevs.items()}
    ir_nodes = apply_abbreviations(ir_nodes, parsed_abbrevs, page_text=preprocessed)
    ir_nodes, attachments = resolve_local_assets(
        ir_nodes,
        page_path=node.source_path,
        docs_dir=config.docs_dir,
    )
    ir_nodes = resolve_captions(ir_nodes)
    attachment_preview = (
        config.confluence.attachment_preview if config.confluence else False
    )
    ir_nodes = resolve_attachment_previews(ir_nodes, enabled=attachment_preview)
    mermaid_render = config.confluence.mermaid_render if config.confluence else "kroki"
    if mermaid_render != "none":
        kroki_url = (
            mermaid_render[len("kroki:"):] if mermaid_render.startswith("kroki:") else DEFAULT_KROKI_URL
        )
        ir_nodes, mermaid_attachments = render_mermaid_diagrams(ir_nodes, kroki_url, quiet=quiet)
        attachments = attachments + mermaid_attachments
        ir_nodes, plantuml_attachments = render_plantuml_diagrams(ir_nodes, kroki_url, quiet=quiet)
        attachments = attachments + plantuml_attachments
    effective_link_map = link_map if link_map is not None else {}
    if node.docs_path:
        ir_nodes = resolve_internal_links(ir_nodes, effective_link_map, node.docs_path)
    if front_matter is not None:
        ir_nodes = (front_matter,) + ir_nodes
    edit_url = config.page_edit_url(node.docs_path or "")
    site_url = config.page_site_url(node.docs_path or "")
    if site_url:
        ir_nodes = attach_source_url(ir_nodes, "", site_url)
    if edit_url:
        abs_path = str(config.docs_dir / (node.docs_path or ""))
        footer = build_source_footer(edit_url, abs_path)
        ir_nodes = ir_nodes + (footer,)

    labels: tuple[str, ...] = ()
    confluence_status: str | None = None
    version_message: str | None = None
    for node_item in ir_nodes:
        if isinstance(node_item, FrontMatter):
            labels = node_item.labels
            confluence_status = node_item.confluence_status
        if isinstance(node_item, SourceFooter) and node_item.commit_sha and node_item.commit_summary:
            version_message = f"{node_item.commit_sha}: {node_item.commit_summary}"

    return CompileResult(
        xhtml=emit(ir_nodes),
        attachments=attachments,
        labels=labels,
        confluence_status=confluence_status,
        version_message=version_message,
    )
