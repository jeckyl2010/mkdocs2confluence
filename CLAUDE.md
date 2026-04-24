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

## Working principles (Karpathy's 4 rules)

These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

Every changed line should trace directly to the user's request.

### 3b. Incremental Refactoring
**Refactor when earned, not speculatively.**

As the application grows and evolves, incremental refactoring is a key skill.
Refactor when:
- A concept has stabilised and the right abstraction is clear.
- A second or third similar case appears (duplication is now provable).
- A change becomes hard to make safely without first clarifying the model.

Apply the Boy Scout rule: leave the code slightly cleaner than you found it — but only when motivated by real friction, not anticipation. Flag refactor opportunities during review; act on them when the task makes them necessary.

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Add feature X" → "Write tests for X, then make them pass"
- "Refactor Y" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

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

## Developer tooling

### Graphify (Copilot CLI skill)
Installed via `uvx --from graphifyy graphify copilot install` into `~/.copilot/skills/graphify/`.
Use `/graphify .` from within the Copilot CLI after significant milestones to build a queryable knowledge graph of the codebase (`graphify-out/graph.html`, `GRAPH_REPORT.md`, `graph.json`).
The `graphify-out/` directory is git-ignored — regenerate as needed.

### Context7 (MCP server)
Configured in `~/.copilot/mcp-config.json`. Available automatically in all Copilot CLI sessions via `/mcp`.
Provides live, version-accurate documentation for external libraries (MkDocs, Confluence REST API, Python-Markdown) — prevents hallucinated or outdated API details.

## External inspiration
The GitHub project `Workable/confluence-docs-as-code` may be used as feature inspiration only.

Use it to extract:
- useful features
- practical publishing ideas
- limitations to avoid

Do not copy its architecture blindly.
Do not treat it as the foundation of this project.