---
name: release
description: Run pre-release quality checks and cut a tagged GitHub release for mkdocs2confluence.
trigger: /release
---

# /release

Use this skill when you are ready to cut a release.

## Pre-release checklist

Run all four checks. All must pass before tagging:

```bash
uv run pytest -q                        # tests
uv run ruff check src tests             # lint (use --fix to auto-correct import sort)
uv run mypy src                         # type-check
uv run vulture src --min-confidence 80  # dead code
```

## Release order

**Never tag before the branch push is confirmed.**

```bash
# 1. Bump version in pyproject.toml
git add pyproject.toml
git commit -m "chore: bump version to vX.Y.Z"

# 2. Push to main first — confirm it landed
git push origin main

# 3. Only then tag and push
git tag vX.Y.Z
git push origin vX.Y.Z

# 4. Create the GitHub release
uv build -q
gh release create vX.Y.Z dist/mkdocs_to_confluence-X.Y.Z* \
  --title "vX.Y.Z" \
  --notes "$(git log $(git describe --tags --abbrev=0 HEAD^)..HEAD --oneline --no-merges | sed 's/^/- /')"
```

Release notes should be a bullet-point summary of commits since the last tag.
