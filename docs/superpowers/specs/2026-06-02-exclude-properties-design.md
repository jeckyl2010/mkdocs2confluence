# Design: `exclude_properties` — control front matter → Page Properties

**Date:** 2026-06-02
**Status:** Approved

## Problem

Every YAML front matter key (other than a small hardcoded set) is converted into
a row in the Confluence **Page Properties** table. Some keys are internal tooling
metadata — e.g. `source_documents` — that are irrelevant on the published page and
should not be exposed. Authors have no way to suppress specific keys.

## Goal

Let the user list front matter keys to exclude from the Page Properties table via
config in `mkdocs.yml`.

## Decisions

- **Match target:** the raw front matter key (e.g. `source_documents`), not the
  humanized display name. Most predictable — you exclude exactly what you wrote.
- **Matching:** exact, case-sensitive (YAML keys are case-sensitive).
- **Scope:** table row only. Special behaviors are unaffected — `title` still sets
  the page title, `tags` still become Confluence labels, `status` still sets the
  page lifecycle status. Excluding such a key only removes its visible row.
- **Pure exclusion:** no wildcards, no regex, no glob — a literal key list.

## Config

New optional key in the `confluence:` block of `mkdocs.yml`:

```yaml
confluence:
  base_url: https://yourorg.atlassian.net/wiki
  # ...
  exclude_properties:
    - source_documents
    - internal_ref
```

- Absent → no extra exclusions (default `()`).
- Present and a list → each entry stringified into the exclude set.
- Present and **not** a list → raise `ConfigError` with a clear message, matching
  the existing validation style in `load_config`.

## Data flow

1. `load_config` (`loader/config.py`) parses `exclude_properties` into a new
   `ConfluenceConfig.exclude_properties: tuple[str, ...] = ()` field.
2. `compile_page` (`compiler/page.py`) reads
   `config.confluence.exclude_properties` (falling back to `()` when no confluence
   block) and passes it to `extract_front_matter`.
3. `extract_front_matter(text, exclude_properties=())` forwards the set to
   `_build_node(raw, exclude)`.
4. In `_build_node`, the two property-appending loops skip any key in
   `_STRIP_FIELDS | set(exclude)`. The built-in always-stripped set (`source`,
   `status`) is unchanged; user excludes are additive.
5. `title`, `subtitle`, `confluence_status`, and `labels` are computed
   independently of those loops, so excluding `tags`/`title`/etc. hides only the
   table row — never the side-effect. This is "table row only" for free.

## Components touched

| File | Change |
|---|---|
| `loader/config.py` | New `exclude_properties` field; parse + validate from `confluence:` block |
| `preprocess/frontmatter.py` | `extract_front_matter` / `_build_node` gain an `exclude` param (default `()`, keeps existing callers working) |
| `compiler/page.py` | One line threading config → extractor |
| `docs/features.md`, `README.md` | Document the new config key |

## Testing (TDD)

**frontmatter unit tests**
- Excluded key is omitted from the properties table.
- Non-excluded keys are retained.
- Excluding `tags` still yields Confluence labels (side-effect preserved).
- Excluding a non-existent key is a no-op.
- Matching is case-sensitive (`Source_Documents` ≠ `source_documents`).
- Default (no exclude arg) preserves current behavior.

**config tests**
- `exclude_properties` list parses to a tuple on `ConfluenceConfig`.
- Absent → `()`.
- Non-list value → `ConfigError`.

**integration**
- One `compile_page` test proving an excluded key does not appear in emitted XHTML.

## Out of scope (YAGNI)

- Per-page front matter overrides.
- Allow-list (include-only) mode.
- Wildcard / regex / glob matching.
- Suppressing side-effects (labels, title, status) via exclusion.
