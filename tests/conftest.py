"""Shared pytest fixtures for mkdocs-to-confluence tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the absolute path to the tests/fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def docs_dir(fixtures_dir: Path) -> Path:
    """Return the absolute path to the shared fixture docs/ directory."""
    return fixtures_dir / "docs"


@pytest.fixture
def simple_config_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "mkdocs_simple.yml"


@pytest.fixture
def nested_config_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "mkdocs_nested.yml"
