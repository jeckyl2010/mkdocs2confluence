"""Compiler entry points for MkDocs-to-Confluence page compilation."""

from mkdocs_to_confluence.compiler.models import CompileResult
from mkdocs_to_confluence.compiler.page import compile_page

__all__ = ["CompileResult", "compile_page"]
