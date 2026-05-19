# Project instructions

You are building a Python CLI tool (`mk2conf`) that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML/macros.

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
- Unsupported MkDocs/Material features: strip to plain text and emit a transpiler warning to stdout — no content is ever silently lost

## Coding rules

- Propose a short plan before editing for any multi-file or multi-step task
- Follow Python best practices for module design (single responsibility, no global state, side effects isolated at the edges)
- Prefer typed models and pure functions (follow Python best practices for function design)
- Do not refactor unrelated code
- Add tests for any new behaviour or bug fix — bug fixes always get a regression test
- Run tests after changes: `uv run pytest -q`
- Stop after the requested milestone
- Only implement features that are actually needed and used — no speculative work

## Security rules

- Never commit secrets or API tokens into source code
- API tokens are always via `!ENV VAR_NAME` in `mkdocs.yml` or environment variables
- Run `gitleaks` (via pre-commit) before every push — it is configured in `.pre-commit-config.yaml`

## API usage

- Always check official API documentation (via Context7 MCP or web) before implementing any external API call
- Never guess parameter formats, encoding schemes, or endpoint behaviour
- **Confluence REST API:** Prefer the v2 API (`/wiki/api/v2/`) for any given task. Fall back to v1 (`/wiki/rest/api/`) only if the v2 API does not support what you need
- Use `GET /spaces/{id}/pages?title=` to look up a page by title — `spaceId` is not a valid query param on `/pages`
- **Kroki:** Use `POST /mermaid/png` with `Content-Type: text/plain` — never GET (URL length limits are easily exceeded and corporate proxies block Python urllib GET requests)

## Documentation rules

- Every feature addition or removal **must** include a README update
- Check `README.md` before closing any task that changes user-facing functionality (flags, commands, supported features, known limitations)
- `.github/copilot-instructions.md` is the single source of truth — `CLAUDE.md` is a pointer to it

## Commit messages

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `perf:`
- Subject line under 72 characters, imperative mood, no trailing period

## Release

Use the `/release` skill (`.github/skills/release/SKILL.md`). It contains the full pre-release checklist and release order. The key invariant: **always push main and confirm before tagging.**

## Working principles (Karpathy's 4 rules)

These guidelines bias toward caution over speed. For single-file, single-function changes with no design decisions, apply with lighter touch.

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

As the application grows and evolves, incremental refactoring is a key skill. Refactor when:

- A second or third similar case appears (duplication is now provable).
- A change becomes hard to make safely without first clarifying the model.

Apply the Boy Scout rule: leave the code slightly cleaner than you found it — but only when the change you are making is hard because the existing code is unclear or misstructured. Clean up only what is in your way.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Add feature X" → "Write tests for X, then make them pass"
- "Refactor Y" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan — numbered steps, one line each, 3–5 max:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

## Developer tooling

- **Setup:** See `Setup.md` for environment setup and pre-commit hook installation.
- **Graphify:** Run `/graphify .` in Copilot CLI to build a knowledge graph of the codebase (`graphify-out/` is git-ignored).
- **Context7:** MCP server available via `/mcp` — use it to fetch live API docs before implementing any external API call.

## External inspiration

The GitHub project `Workable/confluence-docs-as-code` may be used as feature inspiration only.

Use it to extract:

- useful features
- practical publishing ideas
- limitations to avoid

Do not copy its architecture blindly. Do not treat it as the foundation of this project.
