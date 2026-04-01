# MkDocs to Confluence

A Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML/macros and publishes to Confluence.

## Core idea
This tool is a compiler/transpiler:
- source: MkDocs-flavoured Markdown
- target: native Confluence storage XHTML/macros

It must:
- use raw Markdown as source of truth
- support MkDocs `nav`
- support include/snippet preprocessing
- map features semantically to native Confluence constructs
- degrade unsupported features gracefully

## MVP scope
- load `mkdocs.yml`
- resolve `nav`
- load one page
- preprocess includes/snippets
- parse into an internal IR
- emit Confluence-compatible output locally
- later publish to Confluence

## Non-goals
- no generated HTML import
- no attempt to reproduce Material for MkDocs styling
- no full-site publish in v1