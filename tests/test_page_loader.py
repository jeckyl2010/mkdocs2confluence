"""Tests for loader.page — Milestone 2."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import load_config
from mkdocs_to_confluence.loader.nav import NavNode, resolve_nav
from mkdocs_to_confluence.loader.page import PageLoadError, find_page, load_page


@pytest.fixture
def full_config_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "mkdocs_full.yml"


@pytest.fixture
def sample_config_path() -> Path:
    return Path(__file__).parent.parent / "samples" / "tech-docs" / "mkdocs.yml"


# ---------------------------------------------------------------------------
# find_page
# ---------------------------------------------------------------------------


class TestFindPage:
    def test_finds_top_level_page(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "index.md")
        assert node is not None
        assert node.title == "Home"

    def test_finds_nested_page(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "guide/getting-started.md")
        assert node is not None
        assert node.title == "Getting Started"

    def test_returns_none_for_unknown_path(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        assert find_page(nodes, "nonexistent.md") is None

    def test_finds_deep_nested_page(self, full_config_path: Path) -> None:
        config = load_config(full_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "guide/getting-started.md")
        assert node is not None

    def test_finds_page_after_section(self, full_config_path: Path) -> None:
        config = load_config(full_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "admonitions.md")
        assert node is not None
        assert node.title == "Admonitions"

    def test_does_not_return_section_node(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        # "Guide" is a section, not a page; searching for its label should fail
        result = find_page(nodes, "Guide")
        assert result is None

    def test_empty_nav_returns_none(self) -> None:
        assert find_page([], "index.md") is None

    def test_returns_correct_docs_path(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "guide/getting-started.md")
        assert node is not None
        assert node.docs_path == "guide/getting-started.md"


# ---------------------------------------------------------------------------
# load_page — happy paths
# ---------------------------------------------------------------------------


class TestLoadPageHappyPath:
    def test_returns_string(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "index.md")
        assert node is not None
        content = load_page(node)
        assert isinstance(content, str)

    def test_content_is_not_empty(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "index.md")
        assert node is not None
        assert load_page(node).strip() != ""

    def test_content_matches_file_on_disk(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "index.md")
        assert node is not None
        content = load_page(node)
        expected = node.source_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
        assert content == expected

    def test_content_starts_with_heading(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "index.md")
        assert node is not None
        assert load_page(node).startswith("#")

    def test_nested_page_content(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "guide/getting-started.md")
        assert node is not None
        content = load_page(node)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_admonitions_fixture_loaded(self, full_config_path: Path) -> None:
        config = load_config(full_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "admonitions.md")
        assert node is not None
        content = load_page(node)
        assert "!!!" in content

    def test_code_blocks_fixture_loaded(self, full_config_path: Path) -> None:
        config = load_config(full_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "code_blocks.md")
        assert node is not None
        content = load_page(node)
        assert "```" in content


# ---------------------------------------------------------------------------
# load_page — error paths
# ---------------------------------------------------------------------------


class TestLoadPageErrors:
    def test_raises_page_load_error_when_source_path_is_none(
        self, tmp_path: Path
    ) -> None:
        orphan = NavNode(
            title="Missing Page",
            docs_path="missing.md",
            source_path=None,
            level=0,
        )
        with pytest.raises(PageLoadError, match="missing.md"):
            load_page(orphan)

    def test_error_message_includes_title(self, tmp_path: Path) -> None:
        orphan = NavNode(
            title="The Missing Page",
            docs_path="gone.md",
            source_path=None,
            level=0,
        )
        with pytest.raises(PageLoadError, match="The Missing Page"):
            load_page(orphan)

    def test_raises_os_error_when_file_deleted_after_nav_resolve(
        self, tmp_path: Path
    ) -> None:
        md = tmp_path / "page.md"
        md.write_text("# Hello\n", encoding="utf-8")
        node = NavNode(
            title="Ephemeral",
            docs_path="page.md",
            source_path=md,
            level=0,
        )
        md.unlink()  # delete the file after nav resolution
        with pytest.raises(OSError):
            load_page(node)


# ---------------------------------------------------------------------------
# Sample project smoke tests
# ---------------------------------------------------------------------------


class TestSampleProject:
    def test_sample_config_loads(self, sample_config_path: Path) -> None:
        config = load_config(sample_config_path)
        assert config.site_name == "Tech Docs"

    def test_sample_nav_resolves(self, sample_config_path: Path) -> None:
        config = load_config(sample_config_path)
        nodes = resolve_nav(config)
        assert len(nodes) > 0

    def test_sample_all_pages_have_source_paths(
        self, sample_config_path: Path
    ) -> None:
        from mkdocs_to_confluence.loader.nav import flat_pages

        config = load_config(sample_config_path)
        nodes = resolve_nav(config)
        pages = flat_pages(nodes)
        missing = [p for p in pages if p.source_path is None]
        assert missing == [], f"Missing source paths: {[p.docs_path for p in missing]}"

    def test_sample_index_loadable(self, sample_config_path: Path) -> None:
        config = load_config(sample_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "index.md")
        assert node is not None
        content = load_page(node)
        assert "Tech Docs" in content

    def test_sample_api_reference_loadable(self, sample_config_path: Path) -> None:
        config = load_config(sample_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "reference/api.md")
        assert node is not None
        content = load_page(node)
        assert "GET /ping" in content

    def test_sample_configuration_has_content_tabs(
        self, sample_config_path: Path
    ) -> None:
        config = load_config(sample_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "guide/configuration.md")
        assert node is not None
        content = load_page(node)
        assert '===' in content  # content tabs syntax

    def test_sample_getting_started_has_admonition(
        self, sample_config_path: Path
    ) -> None:
        config = load_config(sample_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "getting-started.md")
        assert node is not None
        content = load_page(node)
        assert "!!!" in content

    def test_sample_installation_has_code_blocks(
        self, sample_config_path: Path
    ) -> None:
        config = load_config(sample_config_path)
        nodes = resolve_nav(config)
        node = find_page(nodes, "guide/installation.md")
        assert node is not None
        content = load_page(node)
        assert "```" in content
