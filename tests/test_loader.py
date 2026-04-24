"""Tests for loader.config and loader.nav — Milestone 1."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import ConfigError, MkDocsConfig, load_config
from mkdocs_to_confluence.loader.nav import NavNode, find_section, find_section_by_folder, flat_pages, resolve_nav

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
        assert len(section.children) == 3  # Getting Started, Installation, Configuration
        assert all(child.level == 1 for child in section.children)

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
# awesome-pages / .pages file support
# ---------------------------------------------------------------------------


def _make_pages_config(tmp_path: Path, nav_file: str = ".pages") -> Path:
    """Create a minimal mkdocs.yml with confluence.nav_file set."""
    docs = tmp_path / "docs"
    docs.mkdir()
    yml = tmp_path / "mkdocs.yml"
    yml.write_text(
        textwrap.dedent(f"""\
            site_name: Test
            confluence:
              base_url: https://example.atlassian.net
              email: test@example.com
              token: tok
              space_key: TEST
              nav_file: "{nav_file}"
        """),
        encoding="utf-8",
    )
    return yml


class TestAwesomePagesNavFile:
    def test_no_nav_uses_pages_file_at_root(self, tmp_path: Path) -> None:
        yml = _make_pages_config(tmp_path)
        docs = tmp_path / "docs"
        # Create sub-directories for sections
        (docs / "cctv").mkdir()
        (docs / "gdpr").mkdir()
        (docs / "cctv" / "vendor-assessment.md").write_text("# Vendor", encoding="utf-8")
        (docs / "gdpr" / "gdpr-requirements.md").write_text("# GDPR", encoding="utf-8")
        # Root .pages file — references directories as sections
        (docs / ".pages").write_text(
            "nav:\n  - CCTV & AI: cctv\n  - GDPR: gdpr\n", encoding="utf-8"
        )
        config = load_config(yml)
        nodes = resolve_nav(config)
        assert len(nodes) == 2
        assert nodes[0].title == "CCTV & AI"
        assert nodes[0].is_section
        assert nodes[1].title == "GDPR"
        assert nodes[1].is_section

    def test_section_directory_reads_nested_pages_file(self, tmp_path: Path) -> None:
        yml = _make_pages_config(tmp_path)
        docs = tmp_path / "docs"
        (docs / "appendix" / "cctv").mkdir(parents=True)
        (docs / "appendix" / "gdpr").mkdir(parents=True)
        (docs / "appendix" / "cctv" / "vendor.md").write_text("# V", encoding="utf-8")
        (docs / "appendix" / "gdpr" / "requirements.md").write_text("# R", encoding="utf-8")
        # appendix/.pages defines two sub-sections
        (docs / "appendix" / ".pages").write_text(
            "nav:\n  - CCTV & AI: cctv\n  - GDPR: gdpr\n", encoding="utf-8"
        )
        # Each sub-folder lists its pages
        (docs / "appendix" / "cctv" / ".pages").write_text(
            "nav:\n  - vendor.md\n", encoding="utf-8"
        )
        (docs / "appendix" / "gdpr" / ".pages").write_text(
            "nav:\n  - requirements.md\n", encoding="utf-8"
        )
        # Root .pages points to appendix dir
        (docs / ".pages").write_text(
            "nav:\n  - Appendix: appendix\n", encoding="utf-8"
        )
        config = load_config(yml)
        nodes = resolve_nav(config)
        assert len(nodes) == 1
        appendix = nodes[0]
        assert appendix.title == "Appendix"
        assert appendix.is_section
        assert len(appendix.children) == 2
        cctv, gdpr = appendix.children
        assert cctv.title == "CCTV & AI" and cctv.is_section
        assert gdpr.title == "GDPR" and gdpr.is_section
        assert len(cctv.children) == 1
        assert cctv.children[0].title == "Vendor"

    def test_custom_nav_file_name(self, tmp_path: Path) -> None:
        yml = _make_pages_config(tmp_path, nav_file=".nav")
        docs = tmp_path / "docs"
        (docs / "guide").mkdir()
        (docs / "guide" / "intro.md").write_text("# Intro", encoding="utf-8")
        (docs / ".nav").write_text(
            "nav:\n  - Guide: guide\n", encoding="utf-8"
        )
        config = load_config(yml)
        nodes = resolve_nav(config)
        assert len(nodes) == 1
        assert nodes[0].title == "Guide"
        assert nodes[0].is_section

    def test_bare_directory_entry_builds_section(self, tmp_path: Path) -> None:
        """Bare directory name in .pages (no title, no colon) expands into a section."""
        yml = _make_pages_config(tmp_path)
        docs = tmp_path / "docs"
        (docs / "appendix" / "gdpr").mkdir(parents=True)
        (docs / "appendix" / "gdpr" / "requirements.md").write_text("# R", encoding="utf-8")
        (docs / "appendix" / ".pages").write_text(
            "nav:\n  - gdpr\n", encoding="utf-8"
        )
        # Root .pages uses bare directory name
        (docs / ".pages").write_text(
            "nav:\n  - index.md\n  - appendix\n", encoding="utf-8"
        )
        (docs / "index.md").write_text("# Home", encoding="utf-8")
        config = load_config(yml)
        nodes = resolve_nav(config)
        titles = [n.title for n in nodes]
        assert "Appendix" in titles
        appendix = next(n for n in nodes if n.title == "Appendix")
        assert appendix.is_section
        assert len(appendix.children) == 1
        assert appendix.children[0].title == "Gdpr"  # auto-titled from dirname
        assert appendix.children[0].is_section

    def test_mkdocs_yml_dir_ref_expands_with_pages_file(self, tmp_path: Path) -> None:
        """When mkdocs.yml nav has a directory reference, .pages inside it is read."""
        docs = tmp_path / "docs"
        (docs / "appendix" / "cctv").mkdir(parents=True)
        (docs / "appendix" / "cctv" / "vendor.md").write_text("# V", encoding="utf-8")
        (docs / "appendix" / ".pages").write_text(
            "nav:\n  - CCTV & AI: cctv\n", encoding="utf-8"
        )
        yml = tmp_path / "mkdocs.yml"
        yml.write_text(
            textwrap.dedent("""\
                site_name: Test
                nav:
                  - Appendix: appendix
                confluence:
                  base_url: https://example.atlassian.net
                  email: test@example.com
                  token: tok
                  space_key: TEST
            """),
            encoding="utf-8",
        )
        config = load_config(yml)
        nodes = resolve_nav(config)
        assert len(nodes) == 1
        appendix = nodes[0]
        assert appendix.is_section
        assert len(appendix.children) == 1
        assert appendix.children[0].title == "CCTV & AI"
        assert appendix.children[0].is_section


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
        assert "Installation" in titles
        assert "Configuration" in titles
        assert "About" in titles
        # sections must not appear in flat list
        assert all(p.is_page for p in pages)

    def test_no_sections_in_result(self, nested_config_path: Path) -> None:
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        pages = flat_pages(nodes)
        assert not any(p.is_section for p in pages)

    def test_section_scope_returns_all_pages(self, nested_config_path: Path) -> None:
        """All pages within a section are returned — not just the first one."""
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        section = find_section(nodes, "Guide")
        assert section is not None
        pages = flat_pages([section])
        titles = [p.title for p in pages]
        assert titles == ["Getting Started", "Installation", "Configuration"]
        assert "Home" not in titles
        assert "About" not in titles

    def test_section_scope_excludes_sibling_sections(self, nested_config_path: Path) -> None:
        """Pages from other sections are not included when scoping to a section."""
        config = load_config(nested_config_path)
        nodes = resolve_nav(config)
        section = find_section(nodes, "Guide")
        assert section is not None
        pages = flat_pages([section])
        assert all(p.docs_path is not None and p.docs_path.startswith("guide/") for p in pages)



# ---------------------------------------------------------------------------
# find_section helper
# ---------------------------------------------------------------------------

_SECTION_NODES: list[NavNode] = [
    NavNode(
        title="Guide",
        docs_path=None,
        source_path=None,
        level=0,
        children=(
            NavNode(title="Getting Started", docs_path="guide/start.md", source_path=None, level=1, children=()),
            NavNode(title="Installation", docs_path="guide/install.md", source_path=None, level=1, children=()),
        ),
    ),
    NavNode(title="About", docs_path="about.md", source_path=None, level=0, children=()),
]


class TestFindSection:
    def test_exact_top_level(self) -> None:
        result = find_section(_SECTION_NODES, "Guide")
        assert result is not None
        assert result.title == "Guide"

    def test_case_insensitive(self) -> None:
        result = find_section(_SECTION_NODES, "guide")
        assert result is not None
        assert result.title == "Guide"

    def test_partial_match(self) -> None:
        result = find_section(_SECTION_NODES, "Abo")
        assert result is not None
        assert result.title == "About"

    def test_nested_path(self) -> None:
        result = find_section(_SECTION_NODES, "Guide/Getting Started")
        assert result is not None
        assert result.title == "Getting Started"

    def test_nested_path_partial(self) -> None:
        result = find_section(_SECTION_NODES, "Guide/install")
        assert result is not None
        assert result.title == "Installation"

    def test_not_found_returns_none(self) -> None:
        assert find_section(_SECTION_NODES, "Nonexistent") is None

    def test_missing_child_returns_none(self) -> None:
        assert find_section(_SECTION_NODES, "Guide/Missing") is None

    def test_empty_path_returns_none(self) -> None:
        assert find_section(_SECTION_NODES, "") is None

    def test_exact_preferred_over_partial(self) -> None:
        nodes: list[NavNode] = [
            NavNode(title="Setup", docs_path="setup.md", source_path=None, level=0, children=()),
            NavNode(title="Setup Guide", docs_path="setup-guide.md", source_path=None, level=0, children=()),
        ]
        result = find_section(nodes, "Setup")
        assert result is not None
        assert result.title == "Setup"

    def test_deep_search_finds_nested_section(self) -> None:
        # Replicates the appendix bug: --section appendix where appendix is
        # nested under a top-level "Documentation" section, not at the root.
        docs = NavNode(
            title="Documentation",
            docs_path=None,
            source_path=None,
            level=0,
            children=(
                NavNode(
                    title="appendix",
                    docs_path=None,
                    source_path=None,
                    level=1,
                    children=(
                        NavNode(
                            title="CCTV & AI",
                            docs_path=None,
                            source_path=None,
                            level=2,
                            children=(
                                NavNode(
                                    title="Vendor Assessment",
                                    docs_path="appendix/cctv/vendor.md",
                                    source_path=None, level=3, children=(),
                                ),
                            ),
                        ),
                        NavNode(title="Index", docs_path="appendix/index.md", source_path=None, level=2, children=()),
                    ),
                ),
            ),
        )
        nav = [docs]
        result = find_section(nav, "appendix")
        assert result is not None
        assert result.title == "appendix"
        # Sub-sections must be preserved — not a flat page list
        assert len(result.children) == 2
        assert result.children[0].title == "CCTV & AI"
        assert result.children[0].is_section




class TestFindSectionByFolder:
    def test_matches_pages_in_folder(self) -> None:
        result = find_section_by_folder(_SECTION_NODES, "guide")
        assert result is not None
        pages = flat_pages([result])
        assert len(pages) == 2
        assert all(p.docs_path is not None and p.docs_path.startswith("guide/") for p in pages)

    def test_trailing_slash_ignored(self) -> None:
        result = find_section_by_folder(_SECTION_NODES, "guide/")
        assert result is not None
        assert len(result.children) == 2

    def test_leading_slash_ignored(self) -> None:
        result = find_section_by_folder(_SECTION_NODES, "/guide")
        assert result is not None

    def test_case_insensitive(self) -> None:
        result = find_section_by_folder(_SECTION_NODES, "GUIDE")
        assert result is not None
        assert len(result.children) == 2

    def test_no_match_returns_none(self) -> None:
        assert find_section_by_folder(_SECTION_NODES, "nonexistent") is None

    def test_synthetic_node_is_section(self) -> None:
        result = find_section_by_folder(_SECTION_NODES, "guide")
        assert result is not None
        assert result.is_section
        assert result.docs_path is None

    def test_does_not_match_root_page(self) -> None:
        """A root-level page like 'about.md' is not matched by folder 'about'."""
        result = find_section_by_folder(_SECTION_NODES, "about")
        assert result is None

    def test_subfolder_matching(self) -> None:
        nodes: list[NavNode] = [
            NavNode(
                title="Guide",
                docs_path=None,
                source_path=None,
                level=0,
                children=(
                    NavNode(title="Advanced", docs_path=None, source_path=None, level=1, children=(
                        NavNode(
                            title="Deep Dive", docs_path="guide/advanced/deep.md",
                            source_path=None, level=2, children=(),
                        ),
                    )),
                    NavNode(title="Basics", docs_path="guide/basics.md", source_path=None, level=1, children=()),
                ),
            ),
        ]
        result = find_section_by_folder(nodes, "guide/advanced")
        assert result is not None
        pages = flat_pages([result])
        assert len(pages) == 1
        assert pages[0].docs_path == "guide/advanced/deep.md"


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

        with pytest.raises((SystemExit, FileNotFoundError)):
            main(["publish"])
