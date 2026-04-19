"""Tests for the edit-link injection transform."""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import Admonition, Paragraph, TextNode
from mkdocs_to_confluence.transforms.editlink import inject_edit_link, _edit_label


# ── _edit_label ───────────────────────────────────────────────────────────────


def test_label_github():
    assert _edit_label("https://github.com/org/repo") == "Edit on GitHub ↗"


def test_label_gitlab():
    assert _edit_label("https://gitlab.com/org/repo") == "Edit on GitLab ↗"


def test_label_bitbucket():
    assert _edit_label("https://bitbucket.org/org/repo") == "Edit on Bitbucket ↗"


def test_label_unknown():
    assert _edit_label("https://custom.example.com/repo") == "Edit source ↗"


def test_label_none():
    assert _edit_label(None) == "Edit source ↗"


# ── inject_edit_link ──────────────────────────────────────────────────────────


def test_banner_prepended():
    """Banner is the first node in the returned tuple."""
    original = (Paragraph(children=(TextNode(text="Hello"),)),)
    result = inject_edit_link(original, "https://github.com/org/repo/edit/main/docs/index.md")
    assert len(result) == 2
    assert isinstance(result[0], Admonition)
    assert result[1] is original[0]


def test_banner_kind_is_info():
    result = inject_edit_link((), "https://example.com/edit/index.md")
    assert result[0].kind == "info"  # type: ignore[attr-defined]


def test_banner_contains_link():
    """Banner body paragraph contains a link with the edit URL."""
    from mkdocs_to_confluence.ir.nodes import LinkNode
    result = inject_edit_link((), "https://github.com/org/repo/edit/main/docs/guide.md")
    banner: Admonition = result[0]  # type: ignore[assignment]
    para: Paragraph = banner.children[0]  # type: ignore[assignment]
    links = [n for n in para.children if isinstance(n, LinkNode)]
    assert len(links) == 1
    assert links[0].href == "https://github.com/org/repo/edit/main/docs/guide.md"


def test_banner_link_label_github():
    from mkdocs_to_confluence.ir.nodes import LinkNode, TextNode as TN
    result = inject_edit_link(
        (), "https://github.com/org/repo/edit/main/docs/index.md",
        repo_url="https://github.com/org/repo",
    )
    banner: Admonition = result[0]  # type: ignore[assignment]
    para: Paragraph = banner.children[0]  # type: ignore[assignment]
    link = next(n for n in para.children if isinstance(n, LinkNode))
    label_text = link.children[0]
    assert isinstance(label_text, TN)
    assert "GitHub" in label_text.text


def test_empty_nodes_still_gets_banner():
    result = inject_edit_link((), "https://example.com/edit")
    assert len(result) == 1
    assert isinstance(result[0], Admonition)


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
