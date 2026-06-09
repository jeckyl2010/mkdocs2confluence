"""Markdown parser: convert preprocessed markdown text into IR nodes."""

from mkdocs_to_confluence.parser.markdown import parse, parse_inline

__all__ = ["parse", "parse_inline"]
