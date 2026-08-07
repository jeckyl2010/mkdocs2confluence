# Project instructions

You are building a Python CLI tool (`mk2conf`) that compiles MkDocs-flavoured Markdown into native Confluence storage XHTML/macros.

This file is the single source of truth for all agent instructions. `CLAUDE.md` and `.github/copilot-instructions.md` point here.

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
- Prefer typed models and pure functions
- Do not refactor unrelated code — every changed line traces to the request. If your change orphans an import or helper, remove it; leave pre-existing dead code alone and mention it instead
- Only implement what was asked — no speculative features, no abstractions for single-use code, no configurability that wasn't requested
- Refactor when earned, not speculatively: when a second or third similar case makes duplication provable, or when the existing structure is actively blocking the change you are making
- Add tests for any new behaviour or bug fix — bug fixes always get a regression test
- Stop after the requested milestone

## Quality gates

Run `uv run pytest -q` after any change — it is the one gate pre-commit does not run for you.

Dev tooling is split across two mechanisms, so **never run a bare `uv sync`** — it uninstalls
pytest, ruff, mypy, pre-commit and bandit (declared in `[project.optional-dependencies].dev`,
which uv skips unless asked). Only vulture and import-linter survive, because they live in
`[dependency-groups].dev`, which uv syncs by default. Use `uv sync --all-extras`, or
`uv pip install -e ".[dev]"` as in `Setup.md`.

Pre-commit already runs ruff, mypy, vulture, import-linter and gitleaks on commit, and CI
re-runs all five plus pytest. Run them by hand only when diagnosing a hook or CI failure:

```bash
uv run ruff check src tests             # lint (--fix auto-corrects import sort)
uv run mypy src                         # type-check
uv run vulture src --min-confidence 80  # dead code
uv run lint-imports                     # architecture boundaries (import-linter)
```

## Security rules

- Never commit secrets or API tokens into source code
- API tokens are always via `!ENV VAR_NAME` in `mkdocs.yml` or environment variables
- Secret scanning is enforced by the `gitleaks` pre-commit hook — never bypass it with `--no-verify`

## API usage

- Always fetch official API documentation before implementing any external API call. Context7 is the preferred source: `npx ctx7@latest library <name> "<question>"` to resolve the ID, then `npx ctx7@latest docs <id> "<question>"`. Never guess parameter formats, encoding schemes, or endpoint behaviour
- **Confluence REST API:** Prefer the v2 API (`/wiki/api/v2/`) for any given task. Fall back to v1 (`/wiki/rest/api/`) only if the v2 API does not support what you need
- See `.github/instructions/publisher.instructions.md` for endpoint-level details (page lookup, Kroki)

## Documentation rules

- Every feature addition or removal **must** include a README update
- Check `README.md` before closing any task that changes user-facing functionality (flags, commands, supported features, known limitations)

## Commit messages

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `perf:`
- Subject line under 72 characters, imperative mood, no trailing period
- Never add AI attribution, trailers, emoji, or tool advertising to commit messages or PR descriptions

## Release

Use the `/release` skill (`.claude/skills/release/SKILL.md`). It contains the full pre-release checklist and release order. The key invariant: **always push main and confirm before tagging.**

## Working principles

- **Think before coding.** State assumptions explicitly; ask when uncertain. If multiple interpretations exist, present them rather than picking silently. If a simpler approach exists, say so.
- **Verify, don't assert.** Turn tasks into checks: "fix the bug" → write a failing test, then make it pass. For multi-step work, state a 3–5 step plan with a verification per step.

## Developer tooling

- **Setup:** See `Setup.md` for environment setup and pre-commit hook installation
- **Local AI proxy:** See `docs/developer/local-ai.md` (`litellm_config.yaml`, `copilot_auto_router.json`)
- **`/release` skill:** hand-edit `.claude/skills/release/SKILL.md`. `.github/skills/release/SKILL.md` is a symlink to it so Copilot CLI sees the same file
- **mkdocs-changelog skill — generated, never edit in place.** This repo dogfoods its own
  `mk2conf install-skill`. The source is `src/mkdocs_to_confluence/skills/mkdocs-changelog/SKILL.md`
  (shipped as package data); edit that, then run `uv run mk2conf install-skill` to regenerate
  `.claude/commands/`, `.github/skills/`, `.github/instructions/` and `.mk2conf/scripts/`.
  Editing a generated copy is silently lost on the next install

## External inspiration

The GitHub project `Workable/confluence-docs-as-code` may be used as feature inspiration only.

Use it to extract:

- useful features
- practical publishing ideas
- limitations to avoid

Do not copy its architecture blindly. Do not treat it as the foundation of this project.
