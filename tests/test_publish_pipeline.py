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


# ── execute_publish: section parent wiring + attachment names ─────────────────


def _make_execute_client(space_id: str = "~42") -> MagicMock:
    """Return a minimal mock ConfluenceClient for execute_publish tests."""
    client = MagicMock()
    _page_counter = {"n": 100}

    def create_page(sid, title, xhtml, *, parent_id=None):
        _page_counter["n"] += 1
        return {"id": _page_counter["n"], "version": {"number": 1}}

    client.create_page.side_effect = create_page
    client.update_page.return_value = {"id": 99, "version": {"number": 2}}
    return client


def _make_section_node(title: str, children: list) -> NavNode:
    return NavNode(title=title, docs_path=None, source_path=None, level=0, children=tuple(children))


def _make_page_node(title: str, tmp_path: Path, docs_dir: Path) -> NavNode:
    src = docs_dir / f"{title.lower().replace(' ', '_')}.md"
    src.write_text(f"# {title}\n")
    return NavNode(
        title=title,
        docs_path=src.relative_to(docs_dir).as_posix(),
        source_path=src,
        level=0,
    )


class TestExecutePublish:
    def test_new_section_children_get_correct_parent_id(self, tmp_path: Path) -> None:
        """Children of a newly-created section must be nested under it."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        child = _make_page_node("Child", tmp_path, docs_dir)
        section = _make_section_node("My Section", [child])

        section_action = PageAction(
            node=section, title="My Section", action="create",
            parent_id="ROOT", xhtml="", page_id=None,
        )
        child_action = PageAction(
            node=child, title="Child", action="create",
            parent_id=None, xhtml="<p>hi</p>",
        )
        plan = [section_action, child_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)

        # Section was created first → got page_id
        assert section_action.page_id is not None
        # Child's parent_id must be the section's new page_id, not None
        assert child_action.parent_id == section_action.page_id

    def test_existing_section_children_wired_from_update(self, tmp_path: Path) -> None:
        """Children of an existing (update) section are also wired correctly."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        child = _make_page_node("Child2", tmp_path, docs_dir)
        section = _make_section_node("Existing Section", [child])

        section_action = PageAction(
            node=section, title="Existing Section", action="update",
            parent_id="ROOT", xhtml="", page_id="existing-99", version=1,
        )
        child_action = PageAction(
            node=child, title="Child2", action="create",
            parent_id=None, xhtml="<p>hi</p>",
        )
        plan = [section_action, child_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)

        assert child_action.parent_id == "existing-99"

    def test_attachment_uses_collision_safe_name(self, tmp_path: Path) -> None:
        """Attachments must be uploaded with the docs_dir-relative name."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        assets = docs_dir / "assets" / "images"
        assets.mkdir(parents=True)
        img = assets / "logo.png"
        img.write_bytes(b"PNG")

        page_node = NavNode(
            title="Page", docs_path="page.md",
            source_path=docs_dir / "page.md",
            level=0,
        )
        page_action = PageAction(
            node=page_node, title="Page", action="create",
            parent_id="ROOT", xhtml="<p/>", page_id=None,
            attachments=[img],
        )
        client = _make_execute_client()

        execute_publish([page_action], client, space_id="~42", docs_dir=docs_dir)

        # upload_attachment must be called with the collision-safe name
        client.upload_attachment.assert_called_once()
        _, _, att_name = client.upload_attachment.call_args.args
        assert att_name == "assets_images_logo.png"
        assert att_name != "logo.png"

    def test_returns_publish_report(self, tmp_path: Path) -> None:
        """execute_publish must return a PublishReport with accurate counts."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport, execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page_node = _make_page_node("Alpha", tmp_path, docs_dir)
        skip_node = _make_page_node("Beta", tmp_path, docs_dir)

        plan = [
            PageAction(node=page_node, title="Alpha", action="create",
                       parent_id="ROOT", xhtml="<p/>"),
            PageAction(node=skip_node, title="Beta", action="skip",
                       parent_id="ROOT"),
        ]
        client = _make_execute_client()
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)

        assert isinstance(report, PublishReport)
        assert report.created == 1
        assert report.skipped == 1
        assert report.updated == 0
        assert report.errors == []

    def test_report_counts_assets_uploaded(self, tmp_path: Path) -> None:
        """assets_uploaded in the report must count all uploaded files."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        img1 = docs_dir / "a.png"
        img2 = docs_dir / "b.pdf"
        img1.write_bytes(b"PNG")
        img2.write_bytes(b"PDF")

        page_node = _make_page_node("Page", tmp_path, docs_dir)
        plan = [
            PageAction(node=page_node, title="Page", action="create",
                       parent_id="ROOT", xhtml="<p/>", attachments=[img1, img2]),
        ]
        client = _make_execute_client()
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)

        assert report.assets_uploaded == 2
        assert client.upload_attachment.call_count == 2

    def test_report_captures_page_error(self, tmp_path: Path) -> None:
        """A page that fails to create is logged in report.errors."""
        from mkdocs_to_confluence.publisher.client import ConfluenceError
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page_node = _make_page_node("Broken", tmp_path, docs_dir)

        client = _make_execute_client()
        client.create_page.side_effect = ConfluenceError("500 boom")

        plan = [PageAction(node=page_node, title="Broken", action="create",
                           parent_id="ROOT", xhtml="<p/>")]
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)

        assert report.created == 0
        assert len(report.errors) == 1
        assert "Broken" in report.errors[0][0]

    def test_parallel_uploads_all_called(self, tmp_path: Path) -> None:
        """All attachments are uploaded even when running in parallel."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        files = []
        for i in range(5):
            f = docs_dir / f"asset_{i}.png"
            f.write_bytes(b"X")
            files.append(f)

        page_node = _make_page_node("Multi", tmp_path, docs_dir)
        plan = [PageAction(node=page_node, title="Multi", action="create",
                           parent_id="ROOT", xhtml="<p/>", attachments=files)]
        client = _make_execute_client()
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)

        assert client.upload_attachment.call_count == 5
        assert report.assets_uploaded == 5
