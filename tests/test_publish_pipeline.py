"""Tests for the publish pipeline: compile_page, plan_publish, dry-run CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mkdocs_to_confluence.loader.config import ConfluenceConfig, MkDocsConfig
from mkdocs_to_confluence.loader.nav import NavNode
from mkdocs_to_confluence.publisher.pipeline import PageAction, compile_page, plan_publish


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_conf_config() -> ConfluenceConfig:
    return ConfluenceConfig(
        base_url="https://example.atlassian.net",
        space_key="TECH",
        email="user@example.com",
        token="tok",
    )


def _make_config(docs_dir: Path) -> MkDocsConfig:
    return MkDocsConfig(
        site_name="Test",
        docs_dir=docs_dir,
        repo_url=None,
        edit_uri=None,
        nav=None,
    )


def _page_node(title: str, path: Path) -> NavNode:
    return NavNode(
        title=title,
        docs_path=path.name,
        source_path=path,
        level=0,
    )


# ── compile_page ──────────────────────────────────────────────────────────────


def test_compile_page_returns_xhtml(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "index.md"
    md.write_text("# Hello\n\nThis is a paragraph.\n", encoding="utf-8")

    node = _page_node("Index", md)
    config = _make_config(docs)
    xhtml, attachments = compile_page(node, config)

    assert "<h1>" in xhtml or "Hello" in xhtml
    assert attachments == []


def test_compile_page_with_ready_false_still_compiles(tmp_path: Path) -> None:
    """compile_page doesn't check ready flag — that's done by plan_publish."""
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "draft.md"
    md.write_text("---\nready: false\n---\n\n# Draft\n", encoding="utf-8")

    node = _page_node("Draft", md)
    config = _make_config(docs)
    xhtml, attachments = compile_page(node, config)
    # Still compiles fine; plan_publish is the gatekeeper
    assert isinstance(xhtml, str)


def test_compile_page_with_source_path_none_returns_empty(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    node = NavNode(title="Missing", docs_path="missing.md", source_path=None, level=0)
    config = _make_config(docs)
    xhtml, attachments = compile_page(node, config)
    assert xhtml == ""
    assert attachments == []


# ── plan_publish: ready: false ────────────────────────────────────────────────


def test_plan_publish_skips_ready_false(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "draft.md"
    md.write_text("---\nready: false\n---\n\n# Draft\n", encoding="utf-8")

    node = _page_node("Draft", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    client = MagicMock()
    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert len(plan) == 1
    assert plan[0].action == "skip"


def test_plan_publish_publishes_ready_true(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("---\nready: true\n---\n\n# Page\n", encoding="utf-8")

    node = _page_node("Page", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    client = MagicMock()
    client.find_page.return_value = None  # page doesn't exist yet

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert len(plan) == 1
    assert plan[0].action == "create"


def test_plan_publish_publishes_no_ready_field(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("# Page\n\nContent.\n", encoding="utf-8")

    node = _page_node("Page", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    client = MagicMock()
    client.find_page.return_value = None

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert len(plan) == 1
    assert plan[0].action == "create"


def test_plan_publish_update_when_page_exists(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("# Page\n\nContent.\n", encoding="utf-8")

    node = _page_node("Page", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    existing_page = {"id": "77", "version": {"number": 2}}
    client = MagicMock()
    client.find_page.return_value = existing_page

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert plan[0].action == "update"
    assert plan[0].page_id == "77"
    assert plan[0].version == 2


# ── dry-run CLI ───────────────────────────────────────────────────────────────


def test_dry_run_prints_page_list(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "index.md"
    md.write_text("# Index\n", encoding="utf-8")

    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        f"site_name: Test\ndocs_dir: docs\n"
        f"confluence:\n"
        f"  base_url: https://example.atlassian.net\n"
        f"  space_key: TECH\n"
        f"  email: user@example.com\n"
        f"  token: tok\n",
        encoding="utf-8",
    )

    from mkdocs_to_confluence.cli import main

    main(["publish", "--config", str(config_file), "--dry-run"])

    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert "example.atlassian.net" in captured.out


def test_dry_run_no_api_calls(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Dry run should not import or call ConfluenceClient."""
    docs = tmp_path / "docs"
    docs.mkdir()

    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        "site_name: Test\ndocs_dir: docs\n"
        "confluence:\n"
        "  base_url: https://example.atlassian.net\n"
        "  space_key: TECH\n"
        "  email: user@example.com\n"
        "  token: tok\n",
        encoding="utf-8",
    )

    from unittest.mock import patch

    with patch("mkdocs_to_confluence.publisher.client.ConfluenceClient") as mock_cls:
        from mkdocs_to_confluence.cli import main

        main(["publish", "--config", str(config_file), "--dry-run"])
        mock_cls.assert_not_called()
