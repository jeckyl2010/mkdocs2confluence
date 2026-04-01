# Project instructions

You are building a Python CLI tool that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML/macros.

## Architecture rules
- Treat this as a compiler/transpiler, not an HTML converter
- Keep stages separate:
  - loader
  - preprocess
  - IR
  - transforms
  - emitter
  - publisher
- Prefer semantic mapping over visual approximation
- Target native Confluence constructs and styling
- Gracefully degrade unsupported MkDocs/Material features
- Start with one page at a time

## Coding rules
- Always propose a short plan before editing
- Keep modules small and testable
- Prefer typed models and small pure functions
- Do not refactor unrelated code
- Add tests with each milestone
- Run tests after changes
- Stop after the requested milestone

## Initial feature priorities
1. mkdocs config loader
2. nav resolver
3. single page loading
4. include/snippet preprocessing
5. IR/document model
6. headings and paragraphs
7. code blocks
8. admonitions
9. images
10. internal links
11. mermaid
12. local Confluence XHTML preview
13. publish/update to Confluence

## External inspiration
The GitHub project `Workable/confluence-docs-as-code` may be used as feature inspiration only.

Use it to extract:
- useful features
- practical publishing ideas
- limitations to avoid

Do not copy its architecture blindly.
Do not treat it as the foundation of this project.