# Dev Environment Setup

## Install uv

[uv](https://docs.astral.sh/uv/) is a fast, modern Python package and version manager.

```bash
brew install uv
```

## Create a Virtual Environment

uv will automatically fetch Python 3.14 if you don't have it:

```bash
uv venv --python 3.14
source .venv/bin/activate
```

## Install the Package

Install in editable mode with dev dependencies:

```bash
uv pip install -e ".[dev]"
```

## Verify

```bash
mk2conf --help
pytest
```

## Deactivate

```bash
deactivate
```
