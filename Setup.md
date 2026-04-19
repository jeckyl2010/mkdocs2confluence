# Dev Environment Setup

## Prerequisites

Install system tools (once):

```bash
brew install uv          # fast Python package/version manager
brew install gh          # GitHub CLI (needed for gh release create)
gh auth login            # authenticate with your GitHub account
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

## Build a release wheel

```bash
python -m build          # produces dist/mkdocs_to_confluence-x.y.z-py3-none-any.whl
```

## Publish a GitHub release

```bash
git tag vX.Y.Z && git push --tags
gh release create vX.Y.Z dist/*.whl dist/*.tar.gz --title "vX.Y.Z — <title>" --notes "<notes>"
```

## Deactivate

```bash
deactivate
```
