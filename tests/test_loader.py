"""Tests for loader.config and loader.nav — Milestone 1."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import ConfigError, MkDocsConfig, load_config
from mkdocs_to_confluence.loader.nav import flat_pages, resolve_nav

# ---------------------------------------------------------------------------
# load_config — happy paths
# ---------------------------------------------------------------------------


class TestLoadConfigHappyPath:
    def test_simple_config_returns_mkdocs_config(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        assert isinstance(config, MkDocsConfig)

    def test_site_name_parsed(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        assert config.site_name == "My Project Docs"

    def test_repo_url_parsed(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        assert config.repo_url == "https://github.com/example/my-project"

    def test_docs_dir_is_absolute(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        assert config.docs_dir.is_absolute()

    def test_docs_dir_resolves_relative_to_yml(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        expected = (simple_config_path.parent / "docs").resolve()
        assert config.docs_dir == expected

    def test_nav_is_list(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        assert isinstance(config.nav, list)
        assert len(config.nav) > 0

    def test_repo_url_optional(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        (tmp_path / "docs").mkdir()
        yml.write_text(
            textwrap.dedent("""\
                site_name: No Repo
                nav:
                  - Home: index.md
            """),
            encoding="utf-8",
        )
        config = load_config(yml)
        assert config.repo_url is None

    def test_custom_docs_dir(self, tmp_path: Path) -> None:
        (tmp_path / "pages").mkdir()
        yml = tmp_path / "mkdocs.yml"
        yml.write_text(
            textwrap.dedent("""\
                site_name: Custom Docs Dir
                docs_dir: pages
                nav:
                  - Home: index.md
            """),
            encoding="utf-8",
        )
        config = load_config(yml)
        assert config.docs_dir == (tmp_path / "pages").resolve()


# ---------------------------------------------------------------------------
# load_config — error paths
# ---------------------------------------------------------------------------


class TestLoadConfigErrors:
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="mkdocs.yml not found"):
            load_config(tmp_path / "nonexistent.yml")

    def test_missing_site_name_raises_config_error(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        yml.write_text("nav:\n  - Home: index.md\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="site_name"):
            load_config(yml)

    def test_empty_site_name_raises_config_error(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        yml.write_text(
            "site_name: ''\nnav:\n  - Home: index.md\n", encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="site_name"):
            load_config(yml)

    def test_missing_nav_returns_none_nav(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        yml.write_text("site_name: Test\n", encoding="utf-8")
        config = load_config(yml)
        assert config.nav is None

    def test_empty_nav_raises_config_error(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        yml.write_text("site_name: Test\nnav: []\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="nav"):
            load_config(yml)

    def test_invalid_repo_url_raises_config_error(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        yml.write_text(
            textwrap.dedent("""\
                site_name: Test
                repo_url: not-a-url
                nav:
                  - Home: index.md
            """),
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="repo_url"):
            load_config(yml)

    def test_non_mapping_yaml_raises_config_error(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        yml.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(yml)


# ---------------------------------------------------------------------------
# resolve_nav — happy paths
# ---------------------------------------------------------------------------


class TestResolveNavHappyPath:
    def test_returns_list(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        assert isinstance(nodes, list)

    def test_flat_nav_all_pages(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        assert all(n.is_page for n in nodes)

    def test_flat_nav_titles(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        titles = [n.title for n in nodes]
        assert "Home" in titles
        assert "Getting Started" in titles

    def test_flat_nav_level_zero(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        assert all(n.level == 0 for n in nodes)

    def test_source_paths_are_absolute(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        for node in nodes:
            assert node.source_path is not None
            assert node.source_path.is_absolute()

    def test_nested_nav_section_node(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        section = next((n for n in nodes if n.is_section), None)
        assert section is not None
        assert section.title == "Guide"

    def test_nested_nav_section_level(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        section = next(n for n in nodes if n.is_section)
        assert section.level == 0

    def test_nested_nav_child_level(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        section = next(n for n in nodes if n.is_section)
        assert len(section.children) == 1
        assert section.children[0].level == 1

    def test_nested_nav_child_title(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        section = next(n for n in nodes if n.is_section)
        assert section.children[0].title == "Getting Started"

    def test_section_has_no_source_path(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        section = next(n for n in nodes if n.is_section)
        assert section.source_path is None
        assert section.docs_path is None


# ---------------------------------------------------------------------------
# resolve_nav — missing files warn instead of error
# ---------------------------------------------------------------------------


class TestResolveNavMissingFiles:
    def test_missing_page_issues_warning(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        yml = tmp_path / "mkdocs.yml"
        yml.write_text(
            textwrap.dedent("""\
                site_name: Test
                nav:
                  - Home: missing.md
            """),
            encoding="utf-8",
        )
        config = load_config(yml)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            resolve_nav(config)
        assert any("missing.md" in str(w.message) for w in caught)

    def test_missing_page_source_path_is_none(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        yml = tmp_path / "mkdocs.yml"
        yml.write_text(
            textwrap.dedent("""\
                site_name: Test
                nav:
                  - Home: missing.md
            """),
            encoding="utf-8",
        )
        config = load_config(yml)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            nodes = resolve_nav(config)
        assert nodes[0].source_path is None

    def test_missing_page_still_has_docs_path(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        yml = tmp_path / "mkdocs.yml"
        yml.write_text(
            textwrap.dedent("""\
                site_name: Test
                nav:
                  - Home: missing.md
            """),
            encoding="utf-8",
        )
        config = load_config(yml)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            nodes = resolve_nav(config)
        assert nodes[0].docs_path == "missing.md"


# ---------------------------------------------------------------------------
# flat_pages helper
# ---------------------------------------------------------------------------


class TestFlatPages:
    def test_flat_nav_unchanged(self, simple_config_path: Path) -> None:
        config = load_config(simple_config_path)
        nodes = resolve_nav(config)
        pages = flat_pages(nodes)
        assert len(pages) == len(nodes)  # all top-level nodes are pages

    def test_nested_nav_flattened(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        pages = flat_pages(nodes)
        titles = [p.title for p in pages]
        assert "Home" in titles
        assert "Getting Started" in titles
        assert "About" in titles
        # sections must not appear in flat list
        assert all(p.is_page for p in pages)

    def test_no_sections_in_result(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        pages = flat_pages(nodes)
        assert not any(p.is_section for p in pages)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCLI:
    def test_help_exits_zero(self) -> None:
        from mkdocs_to_confluence.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_version_exits_zero(self) -> None:
        from mkdocs_to_confluence.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_no_args_exits_zero(self) -> None:
        from mkdocs_to_confluence.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0

    def test_preview_missing_config_exits_nonzero(self) -> None:
        from mkdocs_to_confluence.cli import main

        with pytest.raises((SystemExit, FileNotFoundError)):
            main(["preview", "--config", "nonexistent.yml", "--page", "index.md"])

    def test_publish_not_implemented(self) -> None:
        from mkdocs_to_confluence.cli import main

        with pytest.raises(NotImplementedError):
            main(["publish"])
