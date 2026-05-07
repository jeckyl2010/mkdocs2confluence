"""Tests for the edit-link / site-url attachment transform."""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import FrontMatter, Paragraph, TextNode
from mkdocs_to_confluence.transforms.editlink import attach_source_url

# ── attach_source_url ─────────────────────────────────────────────────────────


def test_source_url_ignored_when_only_edit_url_provided():
    """edit_url is now ignored; attach_source_url with no site_url returns nodes unchanged."""
    fm = FrontMatter(title="My Page", subtitle=None, properties=(), labels=())
    original = (fm, Paragraph(children=(TextNode(text="Hello"),)))
    result = attach_source_url(original, "https://github.com/org/repo/edit/main/docs/index.md")
    assert result is original


def test_existing_front_matter_fields_preserved():
    """Attaching site_url does not lose other FrontMatter fields."""
    fm = FrontMatter(
        title="My Page",
        subtitle="A subtitle",
        properties=(("Version", "1.0"),),
        labels=("arch",),
    )
    result = attach_source_url((fm,), "", site_url="https://site.io/page/")
    updated: FrontMatter = result[0]  # type: ignore[assignment]
    assert updated.title == "My Page"
    assert updated.subtitle == "A subtitle"
    assert updated.properties == (("Version", "1.0"),)
    assert updated.labels == ("arch",)
    assert updated.site_url == "https://site.io/page/"


def test_confluence_status_preserved_by_attach_source_url():
    """confluence_status must survive the attach_source_url transform (regression)."""
    fm = FrontMatter(
        title="My Page",
        subtitle=None,
        properties=(),
        labels=("arch",),
        confluence_status="in-progress",
    )
    result = attach_source_url((fm,), "", site_url="https://site.io/page/")
    updated: FrontMatter = result[0]  # type: ignore[assignment]
    assert updated.confluence_status == "in-progress"


def test_minimal_front_matter_created_when_none_present():
    """A minimal FrontMatter is prepended when the page has no front matter."""
    body = (Paragraph(children=(TextNode(text="Content"),)),)
    result = attach_source_url(body, "", site_url="https://site.io/page/")
    assert len(result) == 2
    assert isinstance(result[0], FrontMatter)
    assert result[0].site_url == "https://site.io/page/"
    assert result[0].title is None
    assert result[0].properties == ()
    assert result[1] is body[0]


def test_empty_nodes_gets_minimal_front_matter():
    result = attach_source_url((), "", site_url="https://site.io/")
    assert len(result) == 1
    assert isinstance(result[0], FrontMatter)
    assert result[0].site_url == "https://site.io/"


def test_no_site_url_returns_nodes_unchanged():
    """When site_url is absent, nodes are returned as-is (no FrontMatter injected)."""
    body = (Paragraph(children=(TextNode(text="Content"),)),)
    result = attach_source_url(body, "")
    assert result is body


# ── page_edit_url ─────────────────────────────────────────────────────────────


def test_page_edit_url_github(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path,
        repo_url="https://github.com/org/repo",
        edit_uri="edit/main/docs/",
        nav=None,
    )
    url = config.page_edit_url("guide/setup.md")
    assert url == "https://github.com/org/repo/edit/main/docs/guide/setup.md"


def test_page_edit_url_none_when_no_edit_uri(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path,
        repo_url="https://github.com/org/repo",
        edit_uri=None,
        nav=None,
    )
    assert config.page_edit_url("index.md") is None


def test_page_edit_url_none_when_no_repo_url(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path,
        repo_url=None,
        edit_uri="edit/main/docs/",
        nav=None,
    )
    assert config.page_edit_url("index.md") is None


def test_edit_uri_default_github(tmp_path):
    """GitHub repo_url → default edit_uri is inferred at load time."""
    import textwrap
    yml = tmp_path / "mkdocs.yml"
    yml.write_text(textwrap.dedent("""\
        site_name: Test
        repo_url: https://github.com/org/repo
        docs_dir: docs
    """))
    (tmp_path / "docs").mkdir()
    from mkdocs_to_confluence.loader.config import load_config
    config = load_config(yml)
    assert config.edit_uri == "edit/main/docs/"
    assert config.page_edit_url("index.md") == \
        "https://github.com/org/repo/edit/main/docs/index.md"


def test_edit_uri_none_when_no_repo(tmp_path):
    import textwrap
    yml = tmp_path / "mkdocs.yml"
    yml.write_text(textwrap.dedent("""\
        site_name: Test
        docs_dir: docs
    """))
    (tmp_path / "docs").mkdir()
    from mkdocs_to_confluence.loader.config import load_config
    config = load_config(yml)
    assert config.edit_uri is None


def test_edit_uri_explicit_override(tmp_path):
    import textwrap
    yml = tmp_path / "mkdocs.yml"
    yml.write_text(textwrap.dedent("""\
        site_name: Test
        repo_url: https://github.com/org/repo
        edit_uri: edit/develop/docs/
        docs_dir: docs
    """))
    (tmp_path / "docs").mkdir()
    from mkdocs_to_confluence.loader.config import load_config
    config = load_config(yml)
    assert config.edit_uri == "edit/develop/docs/"


# ── page_site_url ─────────────────────────────────────────────────────────────


def test_page_site_url_regular_page(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path,
        repo_url=None,
        edit_uri=None,
        nav=None,
        site_url="https://example.github.io/",
    )
    assert config.page_site_url("guide/installation.md") == "https://example.github.io/guide/installation/"


def test_page_site_url_index_page(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path,
        repo_url=None,
        edit_uri=None,
        nav=None,
        site_url="https://example.github.io/",
    )
    assert config.page_site_url("index.md") == "https://example.github.io/"


def test_page_site_url_nested_index(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path,
        repo_url=None,
        edit_uri=None,
        nav=None,
        site_url="https://example.github.io/",
    )
    assert config.page_site_url("guide/index.md") == "https://example.github.io/guide/"


def test_page_site_url_none_when_no_site_url(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=tmp_path,
        repo_url=None,
        edit_uri=None,
        nav=None,
    )
    assert config.page_site_url("guide/install.md") is None


def test_page_site_url_loaded_from_yaml(tmp_path):
    import textwrap
    yml = tmp_path / "mkdocs.yml"
    yml.write_text(textwrap.dedent("""\
        site_name: Test
        site_url: https://studious-enigma-61j576e.pages.github.io/
        docs_dir: docs
    """))
    (tmp_path / "docs").mkdir()
    from mkdocs_to_confluence.loader.config import load_config
    config = load_config(yml)
    assert config.site_url == "https://studious-enigma-61j576e.pages.github.io/"
    assert config.page_site_url("arch/overview.md") == \
        "https://studious-enigma-61j576e.pages.github.io/arch/overview/"


# ── site_url in emitter ───────────────────────────────────────────────────────


def test_published_page_row_in_emitter():
    from mkdocs_to_confluence.emitter.xhtml import emit
    fm = FrontMatter(
        title="Test",
        subtitle=None,
        properties=(),
        labels=(),
        site_url="https://example.github.io/guide/install/",
    )
    out = emit((fm,))
    assert "Published Page" in out
    assert "https://example.github.io/guide/install/" in out


def test_published_page_row_omitted_when_no_site_url():
    from mkdocs_to_confluence.emitter.xhtml import emit
    fm = FrontMatter(
        title="Test",
        subtitle=None,
        properties=(),
        labels=(),
    )
    out = emit((fm,))
    assert "Published Page" not in out


def test_site_url_attached_by_transform():
    fm = FrontMatter(title="T", subtitle=None, properties=(), labels=())
    result = attach_source_url(
        (fm,), "https://github.com/edit", site_url="https://site.io/page/"
    )
    assert isinstance(result[0], FrontMatter)
    assert result[0].site_url == "https://site.io/page/"
