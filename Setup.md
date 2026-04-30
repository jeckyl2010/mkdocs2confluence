# Dev Environment Setup

## Prerequisites

Install system tools (once):

```bash
brew install uv          # fast Python package/version manager
```

## Create a Virtual Environment

uv will automatically fetch Python 3.14 if you don't have it:

```bash
uv venv --python 3.14
source .venv/bin/activate
```

## Install the Package

Install in editable mode with dev dependencies (includes pytest, ruff, mypy, build):

```bash
uv pip install -e ".[dev]"
```

## Verify

```bash
mk2conf --help
pytest
```

## Publish a GitHub release

Bump the version in `pyproject.toml`, commit, tag, and push — GitHub Actions handles the rest:

```bash
git add pyproject.toml
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z && git push origin main --tags
```

The release workflow will run tests, build the wheel, and create the GitHub release automatically.

## Deactivate

```bash
deactivate
```
