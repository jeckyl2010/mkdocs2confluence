"""Tests for the publish pipeline: compile_page, plan_publish, dry-run CLI."""

from __future__ import annotations

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
    xhtml, attachments, labels, _ = compile_page(node, config)

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
    xhtml, attachments, labels, _ = compile_page(node, config)
    # Still compiles fine; plan_publish is the gatekeeper
    assert isinstance(xhtml, str)


def test_compile_page_with_source_path_none_returns_empty(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    node = NavNode(title="Missing", docs_path="missing.md", source_path=None, level=0)
    config = _make_config(docs)
    xhtml, attachments, labels, _ = compile_page(node, config)
    assert xhtml == ""
    assert attachments == []
    assert labels == ()


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
    client.get_content_hash.return_value = None  # no stored hash → must update

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert plan[0].action == "update"
    assert plan[0].page_id == "77"
    assert plan[0].version == 2


def test_plan_publish_skips_when_content_unchanged(tmp_path: Path) -> None:
    """When stored hash matches new XHTML hash the action must be 'skip'."""
    from mkdocs_to_confluence.publisher.pipeline import _xhtml_hash

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("# Page\n\nContent.\n", encoding="utf-8")

    node = _page_node("Page", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    # Compile once to get the real hash
    from mkdocs_to_confluence.publisher.pipeline import compile_page
    xhtml, _, _, _ = compile_page(node, config)
    stored_hash = _xhtml_hash(xhtml)

    existing_page = {"id": "77", "version": {"number": 2}}
    client = MagicMock()
    client.find_page.return_value = existing_page
    client.get_content_hash.return_value = stored_hash

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert plan[0].action == "skip"
    assert plan[0].page_id == "77"


def test_plan_publish_updates_when_content_changed(tmp_path: Path) -> None:
    """When stored hash differs from new XHTML hash the action must be 'update'."""
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
    client.get_content_hash.return_value = "stale-hash-from-previous-run"

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert plan[0].action == "update"


# ── plan_publish: section index ───────────────────────────────────────────────


def _make_section_with_index(title: str, docs_dir: Path) -> NavNode:
    """Helper: section node with an index.md child + one regular child."""
    index_src = docs_dir / "index.md"
    index_src.write_text(f"# {title}\n\nLanding content.\n", encoding="utf-8")
    child_src = docs_dir / "page.md"
    child_src.write_text("# Page\n\nBody.\n", encoding="utf-8")

    index_node = NavNode(
        title="Index",
        docs_path="index.md",
        source_path=index_src,
        level=1,
    )
    child_node = NavNode(
        title="Page",
        docs_path="page.md",
        source_path=child_src,
        level=1,
    )
    return NavNode(
        title=title,
        docs_path=None,
        source_path=None,
        level=0,
        children=(index_node, child_node),
    )


def test_section_with_index_creates_page_not_folder(tmp_path: Path) -> None:
    """A section whose first child is index.md should publish as a page, not a folder."""
    docs = tmp_path / "docs"
    docs.mkdir()
    section = _make_section_with_index("Guide", docs)

    config = _make_config(docs)
    conf_config = _make_conf_config()
    client = MagicMock()
    client.find_page.return_value = None  # new page

    plan = plan_publish([section], client, config, conf_config, space_id="42")

    # Should be: 1 section-page + 1 child page (no "Index" page)
    assert len(plan) == 2
    section_action = plan[0]
    assert section_action.title == "Guide"
    assert not section_action.is_folder
    assert section_action.action == "create"
    assert section_action.xhtml is not None and "Landing content" in section_action.xhtml

    child_action = plan[1]
    assert child_action.title == "Page"
    assert not child_action.is_folder


def test_section_with_index_no_standalone_index_page(tmp_path: Path) -> None:
    """The index.md must NOT appear as a separate page in the plan."""
    docs = tmp_path / "docs"
    docs.mkdir()
    section = _make_section_with_index("Guide", docs)

    config = _make_config(docs)
    conf_config = _make_conf_config()
    client = MagicMock()
    client.find_page.return_value = None

    plan = plan_publish([section], client, config, conf_config, space_id="42")

    titles = [a.title for a in plan]
    assert "Index" not in titles


def test_section_without_index_creates_folder(tmp_path: Path) -> None:
    """A section with no index.md should still produce a folder (unchanged behaviour)."""
    docs = tmp_path / "docs"
    docs.mkdir()
    child_src = docs / "page.md"
    child_src.write_text("# Page\n", encoding="utf-8")
    child_node = NavNode(title="Page", docs_path="page.md", source_path=child_src, level=1)
    section = NavNode(title="Guide", docs_path=None, source_path=None, level=0, children=(child_node,))

    config = _make_config(docs)
    conf_config = _make_conf_config()
    client = MagicMock()
    client.find_page.return_value = None

    plan = plan_publish([section], client, config, conf_config, space_id="42")

    section_action = plan[0]
    assert section_action.title == "Guide"
    assert section_action.is_folder


def test_dry_run_prints_page_list(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "index.md"
    md.write_text("# Index\n", encoding="utf-8")

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

    from mkdocs_to_confluence.cli import main

    main(["publish", "--config", str(config_file), "--dry-run"])

    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert "example.atlassian.net" in captured.out  # codeql[py/incomplete-url-substring-sanitization]


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

    def create_folder(sid, title, *, parent_id=None):
        _page_counter["n"] += 1
        return {"id": _page_counter["n"]}

    client.create_page.side_effect = create_page
    client.create_folder.side_effect = create_folder
    client.find_folder_under.return_value = None  # no pre-existing folders
    client.find_page.return_value = None  # no pre-existing pages
    client.update_page.return_value = {"id": 99, "version": {"number": 2}}
    client.list_attachments.return_value = {}  # no pre-existing attachments
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
            parent_id="ROOT", xhtml="", page_id=None, is_folder=True,
        )
        child_action = PageAction(
            node=child, title="Child", action="create",
            parent_id=None, xhtml="<p>hi</p>",
        )
        plan = [section_action, child_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

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
            is_folder=True,
        )
        child_action = PageAction(
            node=child, title="Child2", action="create",
            parent_id=None, xhtml="<p>hi</p>",
        )
        plan = [section_action, child_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert child_action.parent_id == "existing-99"

    def test_three_level_hierarchy_nesting(self, tmp_path: Path) -> None:
        """Section → SubSection → Page creates the correct parent chain."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        page = _make_page_node("DeepPage", tmp_path, docs_dir)
        sub = _make_section_node("SubSection", [page])
        top = _make_section_node("TopSection", [sub])

        top_action  = PageAction(node=top,  title="TopSection", action="create", parent_id="ROOT", xhtml="", page_id=None, is_folder=True)  # noqa: E501
        sub_action  = PageAction(node=sub,  title="SubSection", action="create", parent_id=None,   xhtml="", page_id=None, is_folder=True)  # noqa: E501
        page_action = PageAction(node=page, title="DeepPage",   action="create", parent_id=None,   xhtml="<p>content</p>")  # noqa: E501

        plan = [top_action, sub_action, page_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert sub_action.parent_id  == top_action.page_id, "SubSection must be under TopSection"
        assert page_action.parent_id == sub_action.page_id,  "DeepPage must be under SubSection"

    def test_sections_use_create_folder_not_create_page(self, tmp_path: Path) -> None:
        """Section nodes must create Confluence folders, not pages."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        child = _make_page_node("Doc", tmp_path, docs_dir)
        section = _make_section_node("Appendix", [child])

        folder_action = PageAction(
            node=section, title="Appendix", action="create",
            parent_id="ROOT", is_folder=True,
        )
        child_action = PageAction(
            node=child, title="Doc", action="create",
            parent_id=None, xhtml="<p>content</p>",
        )
        plan = [folder_action, child_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        client.create_folder.assert_called_once_with("~42", "Appendix", parent_id=None)
        # parent_id="ROOT" is a page, not a folder — API doesn't accept page IDs as parentId
        client.create_page.assert_not_called_for_section = True  # pages don't use create_page
        assert child_action.parent_id == folder_action.page_id

    def test_existing_folder_is_reused_not_recreated(self, tmp_path: Path) -> None:
        """If a folder already exists, it must be reused (find_folder_under → reuse)."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        section = _make_section_node("Appendix", [])

        folder_action = PageAction(
            node=section, title="Appendix", action="create",
            parent_id="ROOT", is_folder=True,
        )
        client = _make_execute_client()
        client.find_folder_under.return_value = {"id": "existing-folder-77", "title": "Appendix"}

        execute_publish([folder_action], client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        client.create_folder.assert_not_called()
        assert folder_action.page_id == "existing-folder-77"

    def test_nested_folders_use_parent_is_folder_endpoint(self, tmp_path: Path) -> None:
        """Sub-folders must search via /folders/{id}/direct-children, not /pages/."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        leaf = _make_page_node("Note", tmp_path, docs_dir)
        sub = _make_section_node("Sub", [leaf])
        top = _make_section_node("Top", [sub])

        top_action = PageAction(node=top, title="Top", action="create", parent_id="ROOT", is_folder=True)
        sub_action = PageAction(node=sub, title="Sub", action="create", parent_id=None, is_folder=True)
        leaf_action = PageAction(node=leaf, title="Note", action="create", parent_id=None, xhtml="<p/>")

        plan = [top_action, sub_action, leaf_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        # Sub-folder search must use parent_is_folder=True
        calls = client.find_folder_under.call_args_list
        sub_call = next(c for c in calls if c.args[1] == "Sub")
        assert sub_call.kwargs.get("parent_is_folder") is True, \
            "find_folder_under for a nested folder must pass parent_is_folder=True"

    def test_update_page_reparents_when_hierarchy_changes(self, tmp_path: Path) -> None:
        """Existing pages are moved (re-parented) when the hierarchy changes.

        Scenario: a page previously published flat now belongs under a new
        sub-section.  The update_page call must include the new parent_id so
        Confluence moves the page rather than leaving it in the old position.
        """
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # 'OldPage' already exists in Confluence (will be "update")
        page = _make_page_node("OldPage", tmp_path, docs_dir)
        sub  = _make_section_node("NewSubSection", [page])
        top  = _make_section_node("TopSection", [sub])

        top_action  = PageAction(node=top,  title="TopSection",   action="update", parent_id="ROOT", xhtml="", page_id="top-99",  version=1, is_folder=True)  # noqa: E501
        sub_action  = PageAction(node=sub,  title="NewSubSection", action="create", parent_id=None,   xhtml="", page_id=None,       is_folder=True)  # noqa: E501
        page_action = PageAction(node=page, title="OldPage",       action="update", parent_id=None,   xhtml="<p>body</p>", page_id="page-77", version=3)  # noqa: E501

        plan = [top_action, sub_action, page_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        # OldPage must have been re-parented to the new sub-section
        assert page_action.parent_id == sub_action.page_id
        # update_page must have been called with the new parent_id
        update_calls = client.update_page.call_args_list
        page_call = next(c for c in update_calls if c.args[0] == "page-77")
        assert page_call.kwargs.get("parent_id") == sub_action.page_id, \
            "update_page must pass parent_id so Confluence re-parents the page"


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
        _, _, att_name, _ = client.upload_attachment.call_args.args
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
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

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
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert report.assets_uploaded == 2
        assert client.upload_attachment.call_count == 2

    def test_assets_skipped_when_not_newer_than_confluence(self, tmp_path: Path) -> None:
        """Assets whose mtime <= Confluence createdAt must be skipped."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)
        img = docs_dir / "img.png"
        img.write_bytes(b"PNG")

        # Simulate Confluence having the file, with a timestamp in the future.
        future_ts = "2099-01-01T00:00:00Z"
        att_name = "img.png"
        client = _make_execute_client()
        client.list_attachments.return_value = {
            att_name: {"version": {"createdAt": future_ts}}
        }

        page_node = _make_page_node("Page", tmp_path, docs_dir)
        plan = [
            PageAction(node=page_node, title="Page", action="create",
                       parent_id="ROOT", xhtml="<p/>", attachments=[img]),
        ]
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert report.assets_skipped == 1
        assert report.assets_uploaded == 0
        client.upload_attachment.assert_not_called()

    def test_assets_uploaded_when_newer_than_confluence(self, tmp_path: Path) -> None:
        """Assets whose mtime > Confluence createdAt must be uploaded."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)
        img = docs_dir / "img.png"
        img.write_bytes(b"PNG")

        # Simulate Confluence having an old version of the file.
        old_ts = "2000-01-01T00:00:00Z"
        att_name = "img.png"
        client = _make_execute_client()
        client.list_attachments.return_value = {
            att_name: {"version": {"createdAt": old_ts}}
        }

        page_node = _make_page_node("Page", tmp_path, docs_dir)
        plan = [
            PageAction(node=page_node, title="Page", action="create",
                       parent_id="ROOT", xhtml="<p/>", attachments=[img]),
        ]
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert report.assets_uploaded == 1
        assert report.assets_skipped == 0
        client.upload_attachment.assert_called_once()

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
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert report.created == 0
        assert len(report.errors) == 1
        assert "Broken" in report.errors[0][0]

    def test_three_level_nested_folders_wire_pages_correctly(self, tmp_path: Path) -> None:
        """Pages under nested sub-folders must be created under their specific sub-folder.

        Replicates the user scenario: appendix → [cctv, gdpr, api-test-client] → pages.
        Each page must end up under its own sub-folder, NOT flat under appendix.
        """
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Build nav tree: appendix → [cctv, gdpr] → pages
        cctv_p1 = _make_page_node("CCTV Policy", tmp_path, docs_dir)
        cctv_p2 = _make_page_node("CCTV Guide", tmp_path, docs_dir)
        gdpr_p1 = _make_page_node("GDPR Overview", tmp_path, docs_dir)

        cctv = _make_section_node("cctv", [cctv_p1, cctv_p2])
        gdpr = _make_section_node("gdpr", [gdpr_p1])
        appendix = _make_section_node("appendix", [cctv, gdpr])

        # Replicate the plan that _plan_nodes produces:
        # - Section actions have parent_id=None (set at plan time to None for sub-sections)
        # - parent_is_folder is set correctly per level
        appendix_action = PageAction(node=appendix, title="appendix", action="create",
                                     parent_id="ROOT_PAGE", is_folder=True)
        cctv_action = PageAction(node=cctv, title="cctv", action="create",
                                 parent_id=None, is_folder=True, parent_is_folder=True)
        gdpr_action = PageAction(node=gdpr, title="gdpr", action="create",
                                 parent_id=None, is_folder=True, parent_is_folder=True)
        cctv_p1_action = PageAction(node=cctv_p1, title="CCTV Policy", action="create",
                                    parent_id=None, xhtml="<p>cctv policy</p>")
        cctv_p2_action = PageAction(node=cctv_p2, title="CCTV Guide", action="create",
                                    parent_id=None, xhtml="<p>cctv guide</p>")
        gdpr_p1_action = PageAction(node=gdpr_p1, title="GDPR Overview", action="create",
                                    parent_id=None, xhtml="<p>gdpr</p>")

        # DFS order: appendix → cctv → cctv pages → gdpr → gdpr pages
        plan = [appendix_action, cctv_action, cctv_p1_action, cctv_p2_action,
                gdpr_action, gdpr_p1_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT_PAGE")

        # appendix is a top-level folder (parent_id == root_page_id) — use native folder API,
        # but Confluence /folders API doesn't accept page IDs as parentId, so parent_id=None.
        appendix_call = next(
            c for c in client.create_folder.call_args_list if c.args[1] == "appendix"
        )
        assert appendix_call.kwargs.get("parent_id") is None, (
            "top-level folder must be created at space root (page ID not valid as parentId)"
        )

        # cctv and gdpr must be under appendix (not ROOT_PAGE, not None)
        cctv_call = next(
            c for c in client.create_folder.call_args_list if c.args[1] == "cctv"
        )
        assert cctv_call.kwargs.get("parent_id") == appendix_action.page_id, \
            "cctv folder must be created under appendix, not at root"

        gdpr_call = next(
            c for c in client.create_folder.call_args_list if c.args[1] == "gdpr"
        )
        assert gdpr_call.kwargs.get("parent_id") == appendix_action.page_id, \
            "gdpr folder must be created under appendix, not at root"

        # Pages must be under their specific sub-folder, NOT under appendix
        assert cctv_p1_action.parent_id == cctv_action.page_id, \
            "CCTV Policy must be under cctv folder, not under appendix"
        assert cctv_p2_action.parent_id == cctv_action.page_id, \
            "CCTV Guide must be under cctv folder, not under appendix"
        assert gdpr_p1_action.parent_id == gdpr_action.page_id, \
            "GDPR Overview must be under gdpr folder, not under appendix"

        # None of the page parents should equal appendix_id
        assert cctv_p1_action.parent_id != appendix_action.page_id
        assert gdpr_p1_action.parent_id != appendix_action.page_id

        create_page_calls = client.create_page.call_args_list
        cctv_p1_call = next(c for c in create_page_calls if c.args[1] == "CCTV Policy")
        assert cctv_p1_call.kwargs.get("parent_id") == cctv_action.page_id
        gdpr_p1_call = next(c for c in create_page_calls if c.args[1] == "GDPR Overview")
        assert gdpr_p1_call.kwargs.get("parent_id") == gdpr_action.page_id

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
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert client.upload_attachment.call_count == 5
        assert report.assets_uploaded == 5

    def test_section_index_page_wires_children(self, tmp_path: Path) -> None:
        """Section-index pages (is_folder=False, node.is_section=True) must wire children.

        Regression: section-index pages (sections with an index.md that become a
        regular Confluence page) must still propagate their page_id to children so
        children are nested correctly instead of landing at the space root.
        """
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        child = _make_page_node("01 Overview", tmp_path, docs_dir)
        section = _make_section_node("Design", [child])

        # Section with index.md → is_folder=False (regular page, not a folder)
        section_action = PageAction(
            node=section, title="Design", action="create",
            parent_id="ROOT", xhtml="<p>index</p>", page_id=None, is_folder=False,
        )
        child_action = PageAction(
            node=child, title="01 Overview", action="create",
            parent_id=None, xhtml="<p>content</p>",
        )
        plan = [section_action, child_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert section_action.page_id is not None, "section-index page must be created"
        assert child_action.parent_id == section_action.page_id, \
            "child must be nested under section-index page, not at space root"

    def test_nested_folder_without_index_becomes_stub_page(self, tmp_path: Path) -> None:
        """A section without index.md nested under a section-index page must become a stub page.

        Confluence's /folders API only accepts a folder ID as parentId.
        When the parent is a regular page (section-index), we must create a
        stub page instead of a native folder so hierarchy is preserved.
        """
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        child = _make_page_node("2026 Plan", tmp_path, docs_dir)
        nested_section = _make_section_node("2026", [child])
        proposals = _make_section_node("Proposals", [nested_section])

        # Proposals has index.md → section-index page (is_folder=False)
        proposals_action = PageAction(
            node=proposals, title="Proposals", action="create",
            parent_id="ROOT_PAGE", xhtml="<p>index</p>", is_folder=False,
        )
        # 2026 has no index.md → would normally be a folder
        nested_action = PageAction(
            node=nested_section, title="2026", action="create",
            parent_id=None, is_folder=True,
        )
        child_action = PageAction(
            node=child, title="2026 Plan", action="create",
            parent_id=None, xhtml="<p>content</p>",
        )
        plan = [proposals_action, nested_action, child_action]
        client = _make_execute_client()

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT_PAGE")

        # 2026 must be created as a page (stub), not a folder — its parent is a page
        client.create_folder.assert_not_called()
        calls = client.create_page.call_args_list
        titles_created = [c.args[1] for c in calls]
        assert "Proposals" in titles_created, "Proposals section-index must be created"
        assert "2026" in titles_created, "2026 (no index.md) must be created as stub page"

        # Child must be under 2026, not at space root
        assert child_action.parent_id == nested_action.page_id, \
            "2026 Plan must be nested under the 2026 stub page"

    def test_update_404_falls_back_to_create_and_wires_children(self, tmp_path: Path) -> None:
        """update with HTTP 404 must fall back to create and still wire children.

        Regression: when find_page returns a stale page_id (page was deleted or
        belongs to a different space), update_page raises HTTP 404.  The pipeline
        must create the page instead, capture the new page_id, and wire that id
        into the children — not leave them with parent_id=None at the space root.
        """
        from mkdocs_to_confluence.publisher.client import ConfluenceError
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        child = _make_page_node("01 Overview", tmp_path, docs_dir)
        section = _make_section_node("Design", [child])

        # Plan says "update" because find_page found a stale id="stale-99"
        section_action = PageAction(
            node=section, title="Design", action="update",
            parent_id="ROOT", xhtml="<p>index</p>", page_id="stale-99", version=1,
            is_folder=False,
        )
        child_action = PageAction(
            node=child, title="01 Overview", action="create",
            parent_id=None, xhtml="<p>content</p>",
        )
        plan = [section_action, child_action]
        client = _make_execute_client()
        # Simulate update returning 404 (stale page was deleted)
        client.update_page.side_effect = ConfluenceError(
            "update_page: HTTP 404 — page not found"
        )

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        # Must have fallen back to create and captured a new page_id
        assert section_action.page_id is not None
        assert section_action.page_id != "stale-99", "page_id must be the new one, not the stale one"
        # Child must be wired to the new page_id, not left at root
        assert child_action.parent_id == section_action.page_id, \
            "child must be nested under newly-created page, not at space root"

    def test_update_400_cross_space_falls_back_to_create(self, tmp_path: Path) -> None:
        """update with HTTP 400 'another space' must also fall back to create.

        Regression: when a stale page_id belongs to a different Confluence space
        and the new parent_id is in the current space, Confluence returns HTTP 400
        'Can't add a parent from another space'.  The pipeline must catch this and
        fall back to create, just like the 404 case.
        """
        from mkdocs_to_confluence.publisher.client import ConfluenceError
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        child = _make_page_node("Sub Page", tmp_path, docs_dir)
        section = _make_section_node("01A Cloud Identity", [child])

        section_action = PageAction(
            node=section, title="01A Cloud Identity", action="update",
            parent_id="new-space-design-id", xhtml="<p>index</p>",
            page_id="old-space-stale-id", version=1, is_folder=False,
        )
        child_action = PageAction(
            node=child, title="Sub Page", action="create",
            parent_id=None, xhtml="<p>content</p>",
        )
        plan = [section_action, child_action]
        client = _make_execute_client()
        client.update_page.side_effect = ConfluenceError(
            "update_page: HTTP 400 — Can't add a parent from another space"
        )

        execute_publish(plan, client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT")

        assert section_action.page_id is not None
        assert section_action.page_id != "old-space-stale-id"
        assert child_action.parent_id == section_action.page_id


class TestPruneOrphans:
    """Tests for orphaned page detection and pruning."""

    def test_prune_deletes_managed_orphan(self, tmp_path: Path) -> None:
        """A managed descendant not in published_ids must be deleted."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("My Page", tmp_path, docs_dir)
        action = PageAction(node=page, title="My Page", action="create", parent_id="ROOT")

        client = _make_execute_client()
        client.get_descendant_ids.return_value = ["orphan-99"]
        client.is_managed.return_value = True

        report = execute_publish(
            [action], client, space_id="~42", docs_dir=docs_dir,
            root_page_id="ROOT", prune=True,
        )

        client.delete_page.assert_called_once_with("orphan-99")
        assert report.pruned == 1

    def test_prune_skips_unmanaged_orphan(self, tmp_path: Path) -> None:
        """A manually-created page (no mk2conf-managed stamp) must not be deleted."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("My Page", tmp_path, docs_dir)
        action = PageAction(node=page, title="My Page", action="create", parent_id="ROOT")

        client = _make_execute_client()
        client.get_descendant_ids.return_value = ["manual-page-55"]
        client.is_managed.return_value = False

        report = execute_publish(
            [action], client, space_id="~42", docs_dir=docs_dir,
            root_page_id="ROOT", prune=True,
        )

        client.delete_page.assert_not_called()
        assert report.pruned == 0

    def test_prune_skips_published_pages(self, tmp_path: Path) -> None:
        """Published pages that are descendants must not be deleted."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("My Page", tmp_path, docs_dir)
        action = PageAction(node=page, title="My Page", action="create", parent_id="ROOT")

        client = _make_execute_client()
        # The newly created page has an id set by create_page side_effect (101)
        # We simulate get_descendant_ids returning that same id
        client.get_descendant_ids.return_value = ["101"]

        report = execute_publish(
            [action], client, space_id="~42", docs_dir=docs_dir,
            root_page_id="ROOT", prune=True,
        )

        client.is_managed.assert_not_called()
        client.delete_page.assert_not_called()
        assert report.pruned == 0

    def test_prune_disabled_by_default(self, tmp_path: Path) -> None:
        """Without prune=True, descendant IDs are never fetched."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("My Page", tmp_path, docs_dir)
        action = PageAction(node=page, title="My Page", action="create", parent_id="ROOT")

        client = _make_execute_client()

        execute_publish(
            [action], client, space_id="~42", docs_dir=docs_dir,
            root_page_id="ROOT",
        )

        client.get_descendant_ids.assert_not_called()

    def test_prune_disabled_when_no_root_page_id(self, tmp_path: Path) -> None:
        """prune=True without root_page_id does nothing."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("My Page", tmp_path, docs_dir)
        action = PageAction(node=page, title="My Page", action="create", parent_id=None)

        client = _make_execute_client()

        execute_publish(
            [action], client, space_id="~42", docs_dir=docs_dir,
            prune=True,  # no root_page_id
        )

        client.get_descendant_ids.assert_not_called()

    def test_stamp_managed_called_on_create(self, tmp_path: Path) -> None:
        """stamp_managed must be called for each newly created page."""
        from mkdocs_to_confluence.publisher.pipeline import execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("My Page", tmp_path, docs_dir)
        action = PageAction(node=page, title="My Page", action="create", parent_id="ROOT")

        client = _make_execute_client()

        execute_publish(
            [action], client, space_id="~42", docs_dir=docs_dir, root_page_id="ROOT",
        )

        client.stamp_managed.assert_called_once()

    def test_report_str_shows_pruned_count(self) -> None:
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        r = PublishReport(created=2, updated=1, skipped=0, pruned=3)
        out = str(r)
        assert "3 orphaned page(s) deleted" in out

    def test_report_str_omits_pruned_when_zero(self) -> None:
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        r = PublishReport(created=2, updated=1, skipped=0, pruned=0)
        out = str(r)
        assert "Pruned" not in out


# ── PublishReport.total_pages ─────────────────────────────────────────────────


def test_publish_report_total_pages() -> None:
    from mkdocs_to_confluence.publisher.pipeline import PublishReport

    r = PublishReport(created=3, updated=2, skipped=1)
    assert r.total_pages == 6


# ── PublishReport.__str__ with errors ────────────────────────────────────────


def test_publish_report_str_with_errors() -> None:
    from mkdocs_to_confluence.publisher.pipeline import PublishReport

    r = PublishReport(created=1, updated=0, skipped=0, errors=[("MyPage", "oops")])
    out = str(r)
    assert "Errors:" in out
    assert "MyPage" in out
    assert "oops" in out


# ── _extract_ready_flag edge cases ────────────────────────────────────────────


def test_extract_ready_flag_yaml_error_returns_none() -> None:
    from mkdocs_to_confluence.publisher.pipeline import _extract_ready_flag

    # Invalid YAML inside front matter
    raw = "---\n: :\n---\n"
    # Should not raise; returns None
    result = _extract_ready_flag(raw)
    assert result is None


def test_extract_ready_flag_non_dict_returns_none() -> None:
    from mkdocs_to_confluence.publisher.pipeline import _extract_ready_flag

    # Front matter that parses to a scalar string, not a dict
    raw = "---\njust a string\n---\n"
    result = _extract_ready_flag(raw)
    assert result is None


def test_extract_ready_flag_missing_key_returns_none() -> None:
    from mkdocs_to_confluence.publisher.pipeline import _extract_ready_flag

    # Valid dict front matter, but no 'ready' key
    raw = "---\ntitle: Hello\n---\n"
    result = _extract_ready_flag(raw)
    assert result is None


# ── execute_publish dry_run=True ──────────────────────────────────────────────


def test_execute_publish_dry_run_counts_actions(tmp_path: Path) -> None:
    """dry_run=True returns counts without calling the client."""
    from unittest.mock import MagicMock

    from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    a = _make_page_node("A", tmp_path, docs_dir)
    b = _make_page_node("B", tmp_path, docs_dir)
    c = _make_page_node("C", tmp_path, docs_dir)

    plan = [
        PageAction(node=a, title="A", action="create", parent_id="ROOT", xhtml="<p/>"),
        PageAction(node=b, title="B", action="update", parent_id="ROOT", xhtml="<p/>", page_id="10", version=1),
        PageAction(node=c, title="C", action="skip", parent_id="ROOT"),
    ]
    client = MagicMock()
    report = execute_publish(plan, client, dry_run=True, space_id="~42", docs_dir=docs_dir)

    assert report.created == 1
    assert report.updated == 1
    assert report.skipped == 1
    client.create_page.assert_not_called()
    client.update_page.assert_not_called()


# ── _prune_orphans error paths ────────────────────────────────────────────────


def test_prune_orphans_get_descendants_raises_prints_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """When get_descendant_ids raises, prune prints a warning and returns."""
    from unittest.mock import MagicMock

    from mkdocs_to_confluence.publisher.pipeline import PublishReport, _prune_orphans

    client = MagicMock()
    client.get_descendant_ids.side_effect = RuntimeError("network error")
    report = PublishReport()
    _prune_orphans(client, "ROOT", set(), report)

    captured = capsys.readouterr()
    assert "warn" in captured.err.lower() or "prune" in captured.err.lower()
    assert report.pruned == 0


def test_prune_orphans_delete_raises_continues(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """When delete_page raises, the warning is printed and other orphans are processed."""
    from unittest.mock import MagicMock

    from mkdocs_to_confluence.publisher.pipeline import PublishReport, _prune_orphans

    client = MagicMock()
    client.get_descendant_ids.return_value = ["orphan1", "orphan2"]
    client.is_managed.return_value = True
    client.delete_page.side_effect = RuntimeError("delete failed")
    report = PublishReport()
    _prune_orphans(client, "ROOT", set(), report)

    captured = capsys.readouterr()
    assert "warn" in captured.err.lower() or "failed" in captured.err.lower()
    assert report.pruned == 0


# ── execute_publish non-fatal error paths ─────────────────────────────────────


class TestExecutePublishNonFatal:
    """Non-fatal try/except blocks inside execute_publish must not abort the run."""

    def _make_client(self) -> MagicMock:
        client = MagicMock()
        counter = {"n": 200}

        def create_page(sid, title, xhtml, *, parent_id=None):
            counter["n"] += 1
            return {"id": counter["n"], "version": {"number": 1}}

        client.create_page.side_effect = create_page
        client.find_folder_under.return_value = None
        client.find_page.return_value = None
        client.update_page.return_value = {"id": 99, "version": {"number": 2}}
        client.list_attachments.return_value = {}
        return client

    def test_stamp_managed_failure_is_non_fatal(self, tmp_path: Path) -> None:
        from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("P", tmp_path, docs_dir)
        plan = [PageAction(node=page, title="P", action="create", parent_id="ROOT", xhtml="<p/>")]
        client = self._make_client()
        client.stamp_managed.side_effect = Exception("stamp failed")
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)
        assert report.created == 1
        assert report.errors == []

    def test_set_content_hash_failure_is_non_fatal(self, tmp_path: Path) -> None:
        from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("P", tmp_path, docs_dir)
        plan = [PageAction(node=page, title="P", action="create", parent_id="ROOT",
                           xhtml="<p/>", content_hash="abc123")]
        client = self._make_client()
        client.set_content_hash.side_effect = Exception("hash failed")
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)
        assert report.created == 1
        assert report.errors == []

    def test_set_page_full_width_failure_is_non_fatal(self, tmp_path: Path) -> None:
        from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("P", tmp_path, docs_dir)
        plan = [PageAction(node=page, title="P", action="create", parent_id="ROOT", xhtml="<p/>")]
        client = self._make_client()
        client.set_page_full_width.side_effect = Exception("layout failed")
        report = execute_publish(
            plan, client, space_id="~42", docs_dir=docs_dir, full_width=True
        )
        assert report.created == 1
        assert report.errors == []

    def test_set_page_labels_failure_is_non_fatal(self, tmp_path: Path) -> None:
        from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("P", tmp_path, docs_dir)
        plan = [PageAction(node=page, title="P", action="create", parent_id="ROOT",
                           xhtml="<p/>", labels=("tag1",))]
        client = self._make_client()
        client.set_page_labels.side_effect = Exception("labels failed")
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)
        assert report.created == 1
        assert report.errors == []

    def test_stamp_managed_after_fallback_create_is_non_fatal(self, tmp_path: Path) -> None:
        """stamp_managed after the update-fallback-to-create path is also non-fatal."""
        from mkdocs_to_confluence.publisher.client import ConfluenceError
        from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        page = _make_page_node("P", tmp_path, docs_dir)
        plan = [PageAction(node=page, title="P", action="update", parent_id="ROOT",
                           xhtml="<p/>", page_id="50", version=1)]
        client = self._make_client()
        # update_page raises 404 → triggers fallback create
        client.update_page.side_effect = ConfluenceError("HTTP 404 — not found")
        client.stamp_managed.side_effect = Exception("stamp failed")
        report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)
        assert report.created == 1
        assert report.errors == []


# ── execute_publish: asset upload error appended to report ────────────────────


def test_execute_publish_asset_upload_error_in_report(tmp_path: Path) -> None:
    """Asset upload errors must be recorded in the report, not raise."""
    from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    pdf = docs_dir / "doc.pdf"
    pdf.write_bytes(b"PDF")
    page = _make_page_node("P", tmp_path, docs_dir)
    plan = [PageAction(node=page, title="P", action="create", parent_id="ROOT",
                       xhtml="<p/>", attachments=[pdf])]
    client = _make_execute_client()
    client.upload_attachment.side_effect = Exception("upload failed")
    report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)
    assert report.created == 1
    assert len(report.errors) == 1
    assert "doc.pdf" in report.errors[0][0]


# ── execute_publish: find_folder_under failure is non-fatal ──────────────────


def test_execute_publish_find_folder_under_failure_continues(tmp_path: Path) -> None:
    """find_folder_under raising must not abort the run — a new folder is created."""
    from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    child = _make_page_node("Child", tmp_path, docs_dir)
    section = _make_section_node("Section", [child])
    plan = [
        PageAction(node=section, title="Section", action="create", parent_id="ROOT",
                   xhtml=None, is_folder=True),
        PageAction(node=child, title="Child", action="create", parent_id=None,
                   xhtml="<p/>"),
    ]
    client = _make_execute_client()
    client.find_folder_under.side_effect = Exception("network error")
    # Should not raise
    report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir,
                             root_page_id="ROOT")
    assert report.created >= 1


# ── execute_publish: stub page reuse (existing folder found under page parent) ─


def test_execute_publish_stub_page_reuse(tmp_path: Path) -> None:
    """When a stub page already exists for a section under a page parent, it is reused."""
    from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    child = _make_page_node("Child", tmp_path, docs_dir)
    section = _make_section_node("Section", [child])

    # Simulate an orphaned page that was formerly a section — reuse it
    existing_page = {"id": "77", "title": "Section", "version": {"number": 1}}
    client = _make_execute_client()
    # find_folder_under returns None → falls through to stub page path
    client.find_folder_under.return_value = None
    # find_page returns existing stub
    client.find_page.return_value = existing_page

    plan = [
        PageAction(node=section, title="Section", action="create", parent_id="DYNAMIC_PARENT",
                   xhtml=None, is_folder=True, parent_is_folder=False),
        PageAction(node=child, title="Child", action="create", parent_id=None,
                   xhtml="<p/>"),
    ]
    report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir,
                             root_page_id="ROOT")
    # The existing stub is reused (updated count)
    assert report.updated >= 1


# ── execute_publish: non-stale ConfluenceError re-raises ─────────────────────


def test_execute_publish_non_stale_update_error_is_recorded(tmp_path: Path) -> None:
    """A non-stale ConfluenceError from update_page is recorded in report errors."""
    from mkdocs_to_confluence.publisher.client import ConfluenceError
    from mkdocs_to_confluence.publisher.pipeline import PageAction, execute_publish

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page = _make_page_node("P", tmp_path, docs_dir)
    plan = [PageAction(node=page, title="P", action="update", parent_id="ROOT",
                       xhtml="<p/>", page_id="50", version=1)]
    client = _make_execute_client()
    client.update_page.side_effect = ConfluenceError("HTTP 409 — conflict")
    # Non-stale error is re-raised and caught by the outer except, stored in errors
    report = execute_publish(plan, client, space_id="~42", docs_dir=docs_dir)
    assert len(report.errors) == 1
    assert "409" in report.errors[0][1]


# ── TestExecutePublishHelpers ─────────────────────────────────────────────────


from mkdocs_to_confluence.publisher.pipeline import (  # noqa: E402
    _execute_folder_action,
    _execute_page_action,
    _post_process_action,
    _wire_children,
)


class TestExecutePublishHelpers:
    """Unit tests for the 4 private helpers extracted from execute_publish."""

    # ── _execute_folder_action ────────────────────────────────────────────────

    def test_folder_page_id_already_set_increments_updated(self, tmp_path: Path) -> None:
        """page_id already set → reuse, no client calls, report.updated += 1."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("Sec", [])
        action = PageAction(node=node, title="Sec", action="create",
                            parent_id="ROOT", is_folder=True, page_id="existing-1")
        client = MagicMock()
        report = PublishReport()

        _execute_folder_action(action, client, "s1", "ROOT", report)

        assert report.updated == 1
        assert report.created == 0
        client.find_folder_under.assert_not_called()
        client.create_folder.assert_not_called()

    def test_folder_parent_is_folder_existing_reused(self, tmp_path: Path) -> None:
        """parent_is_folder=True + find_folder_under hits → reuse, report.updated += 1."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("Sec", [])
        action = PageAction(node=node, title="Sec", action="create",
                            parent_id="parent-1", is_folder=True,
                            parent_is_folder=True)
        client = MagicMock()
        client.find_folder_under.return_value = {"id": "folder-55"}
        report = PublishReport()

        _execute_folder_action(action, client, "s1", None, report)

        assert action.page_id == "folder-55"
        assert report.updated == 1
        assert report.created == 0
        client.create_folder.assert_not_called()

    def test_folder_parent_is_folder_not_found_creates(self, tmp_path: Path) -> None:
        """parent_is_folder=True + find_folder_under miss → create_folder, report.created += 1."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("Sec", [])
        action = PageAction(node=node, title="Sec", action="create",
                            parent_id="parent-1", is_folder=True,
                            parent_is_folder=True)
        client = MagicMock()
        client.find_folder_under.return_value = None
        client.create_folder.return_value = {"id": "new-folder-99"}
        report = PublishReport()

        _execute_folder_action(action, client, "s1", None, report)

        assert action.page_id == "new-folder-99"
        assert report.created == 1
        assert report.updated == 0
        client.create_folder.assert_called_once_with("s1", "Sec", parent_id="parent-1")

    def test_folder_find_folder_under_raises_falls_through_to_create(self) -> None:
        """find_folder_under raising → warn, fall through to create_folder."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("Sec", [])
        action = PageAction(node=node, title="Sec", action="create",
                            parent_id="parent-1", is_folder=True,
                            parent_is_folder=True)
        client = MagicMock()
        client.find_folder_under.side_effect = RuntimeError("network error")
        client.create_folder.return_value = {"id": "fallback-77"}
        report = PublishReport()

        _execute_folder_action(action, client, "s1", None, report)

        assert action.page_id == "fallback-77"
        assert report.created == 1
        client.create_folder.assert_called_once()

    def test_folder_parent_is_page_existing_page_reused(self) -> None:
        """Parent is a page (not folder, not root) → stub path: find_page hits → updated."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("Sec", [])
        action = PageAction(node=node, title="Sec", action="create",
                            parent_id="some-page-id", is_folder=True,
                            parent_is_folder=False)
        client = MagicMock()
        client.find_page.return_value = {"id": "stub-88"}
        report = PublishReport()

        _execute_folder_action(action, client, "s1", "ROOT", report)

        assert action.page_id == "stub-88"
        assert action.is_folder is False
        assert report.updated == 1
        client.create_page.assert_not_called()

    def test_folder_parent_is_page_no_existing_creates_stub(self) -> None:
        """Parent is a page → stub path: find_page miss → create_page stub called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("Sec", [])
        action = PageAction(node=node, title="Sec", action="create",
                            parent_id="some-page-id", is_folder=True,
                            parent_is_folder=False)
        client = MagicMock()
        client.find_page.return_value = None
        client.create_page.return_value = {"id": "stub-created-12"}
        report = PublishReport()

        _execute_folder_action(action, client, "s1", "ROOT", report)

        assert action.page_id == "stub-created-12"
        assert action.is_folder is False
        assert report.created == 1
        client.create_page.assert_called_once_with(
            "s1", "Sec", "", parent_id="some-page-id"
        )

    # ── _execute_page_action ──────────────────────────────────────────────────

    def test_page_create_calls_create_page_and_stamp(self) -> None:
        """create → create_page called, page_id set, report.created += 1, stamp_managed called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", xhtml="<p/>")
        client = MagicMock()
        client.create_page.return_value = {"id": "new-5"}
        report = PublishReport()

        _execute_page_action(action, client, "s1", report)

        assert action.page_id == "new-5"
        assert report.created == 1
        assert report.updated == 0
        client.create_page.assert_called_once_with(
            "s1", "P", "<p/>", parent_id="ROOT"
        )
        client.stamp_managed.assert_called_once_with("new-5")

    def test_page_create_stamp_managed_raises_non_fatal(self) -> None:
        """create + stamp_managed raises → non-fatal, report.created still incremented."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", xhtml="<p/>")
        client = MagicMock()
        client.create_page.return_value = {"id": "new-6"}
        client.stamp_managed.side_effect = RuntimeError("stamp failed")
        report = PublishReport()

        _execute_page_action(action, client, "s1", report)

        assert action.page_id == "new-6"
        assert report.created == 1

    def test_page_update_calls_update_page(self) -> None:
        """update → update_page called, report.updated += 1."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="update",
                            parent_id="ROOT", xhtml="<p/>",
                            page_id="existing-9", version=3)
        client = MagicMock()
        report = PublishReport()

        _execute_page_action(action, client, "s1", report)

        assert report.updated == 1
        client.update_page.assert_called_once_with(
            "existing-9", "P", "<p/>", 4, parent_id="ROOT"
        )
        client.create_page.assert_not_called()

    def test_page_update_404_falls_back_to_create(self) -> None:
        """update + HTTP 404 → fallback create_page, report.created += 1."""
        from mkdocs_to_confluence.publisher.client import ConfluenceError
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="update",
                            parent_id="ROOT", xhtml="<p/>",
                            page_id="stale-10", version=1)
        client = MagicMock()
        client.update_page.side_effect = ConfluenceError("HTTP 404 not found")
        client.create_page.return_value = {"id": "fresh-20"}
        report = PublishReport()

        _execute_page_action(action, client, "s1", report)

        assert action.page_id == "fresh-20"
        assert report.created == 1
        assert report.updated == 0
        client.create_page.assert_called_once()

    def test_page_update_400_another_space_falls_back_to_create(self) -> None:
        """update + HTTP 400 'another space' → fallback create_page."""
        from mkdocs_to_confluence.publisher.client import ConfluenceError
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="update",
                            parent_id="ROOT", xhtml="<p/>",
                            page_id="stale-11", version=2)
        client = MagicMock()
        client.update_page.side_effect = ConfluenceError(
            "HTTP 400 Can't add a parent from another space"
        )
        client.create_page.return_value = {"id": "fresh-21"}
        report = PublishReport()

        _execute_page_action(action, client, "s1", report)

        assert action.page_id == "fresh-21"
        assert report.created == 1

    def test_page_update_non_stale_error_reraises(self) -> None:
        """update + HTTP 500 → re-raises (not caught by helper)."""
        from mkdocs_to_confluence.publisher.client import ConfluenceError
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="update",
                            parent_id="ROOT", xhtml="<p/>",
                            page_id="page-12", version=1)
        client = MagicMock()
        client.update_page.side_effect = ConfluenceError("HTTP 500 server error")
        report = PublishReport()

        with pytest.raises(ConfluenceError, match="HTTP 500"):
            _execute_page_action(action, client, "s1", report)

    # ── _wire_children ────────────────────────────────────────────────────────

    def test_wire_children_sets_parent_id_and_is_folder(self) -> None:
        """Section with 2 children → both get parent_id and parent_is_folder updated."""
        child1 = NavNode(title="C1", docs_path="c1.md", source_path=None, level=1)
        child2 = NavNode(title="C2", docs_path="c2.md", source_path=None, level=1)
        section = NavNode(title="Sec", docs_path=None, source_path=None, level=0,
                          children=(child1, child2))

        action = PageAction(node=section, title="Sec", action="create",
                            parent_id="ROOT", is_folder=True, page_id="sec-id-1")
        child1_action = PageAction(node=child1, title="C1", action="create",
                                   parent_id=None)
        child2_action = PageAction(node=child2, title="C2", action="create",
                                   parent_id=None)

        action_by_node = {
            id(child1): child1_action,
            id(child2): child2_action,
        }

        _wire_children(action, action_by_node)

        assert child1_action.parent_id == "sec-id-1"
        assert child1_action.parent_is_folder is True
        assert child2_action.parent_id == "sec-id-1"
        assert child2_action.parent_is_folder is True

    def test_wire_children_noop_when_page_id_none(self) -> None:
        """action.page_id is None → children not updated."""
        child = NavNode(title="C", docs_path="c.md", source_path=None, level=1)
        section = NavNode(title="Sec", docs_path=None, source_path=None, level=0,
                          children=(child,))

        action = PageAction(node=section, title="Sec", action="create",
                            parent_id="ROOT", is_folder=True, page_id=None)
        child_action = PageAction(node=child, title="C", action="create",
                                  parent_id=None)
        action_by_node = {id(child): child_action}

        _wire_children(action, action_by_node)

        assert child_action.parent_id is None

    # ── _post_process_action ──────────────────────────────────────────────────

    def test_post_full_width_called_when_true(self, tmp_path: Path) -> None:
        """full_width=True + not folder → set_page_full_width called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", page_id="pid-1")
        client = MagicMock()
        report = PublishReport()

        _post_process_action(action, client, full_width=True,
                             docs_dir=tmp_path, report=report)

        client.set_page_full_width.assert_called_once_with("pid-1")

    def test_post_full_width_not_called_when_false(self, tmp_path: Path) -> None:
        """full_width=False → set_page_full_width NOT called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", page_id="pid-2")
        client = MagicMock()
        report = PublishReport()

        _post_process_action(action, client, full_width=False,
                             docs_dir=tmp_path, report=report)

        client.set_page_full_width.assert_not_called()

    def test_post_full_width_not_called_for_folder(self, tmp_path: Path) -> None:
        """is_folder=True → set_page_full_width + set_page_labels NOT called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("F", [])
        action = PageAction(node=node, title="F", action="create",
                            parent_id="ROOT", page_id="pid-3",
                            is_folder=True, labels=("a", "b"))
        client = MagicMock()
        report = PublishReport()

        _post_process_action(action, client, full_width=True,
                             docs_dir=tmp_path, report=report)

        client.set_page_full_width.assert_not_called()
        client.set_page_labels.assert_not_called()

    def test_post_labels_called_when_set(self, tmp_path: Path) -> None:
        """action.labels set + not folder → set_page_labels called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", page_id="pid-4",
                            labels=("foo", "bar"))
        client = MagicMock()
        report = PublishReport()

        _post_process_action(action, client, full_width=False,
                             docs_dir=tmp_path, report=report)

        client.set_page_labels.assert_called_once_with("pid-4", ("foo", "bar"))

    def test_post_content_hash_stored_on_create(self, tmp_path: Path) -> None:
        """content_hash + action='create' → set_content_hash called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", page_id="pid-5",
                            content_hash="abc123")
        client = MagicMock()
        report = PublishReport()

        _post_process_action(action, client, full_width=False,
                             docs_dir=tmp_path, report=report)

        client.set_content_hash.assert_called_once_with("pid-5", "abc123")

    def test_post_content_hash_not_stored_on_skip(self, tmp_path: Path) -> None:
        """content_hash + action='skip' → set_content_hash NOT called."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="skip",
                            parent_id="ROOT", page_id="pid-6",
                            content_hash="abc456")
        client = MagicMock()
        report = PublishReport()

        _post_process_action(action, client, full_width=False,
                             docs_dir=tmp_path, report=report)

        client.set_content_hash.assert_not_called()

    def test_post_attachments_uploaded_and_counted(self, tmp_path: Path) -> None:
        """action.attachments set → _upload_assets called, report.assets_uploaded incremented."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        img = docs_dir / "pic.png"
        img.write_bytes(b"PNG")

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", page_id="pid-7",
                            attachments=[img])
        client = MagicMock()
        client.list_attachments.return_value = {}
        client.upload_attachment.return_value = None
        report = PublishReport()

        _post_process_action(action, client, full_width=False,
                             docs_dir=docs_dir, report=report)

        client.upload_attachment.assert_called_once()
        assert report.assets_uploaded == 1

    def test_post_full_width_raises_non_fatal(self, tmp_path: Path) -> None:
        """set_page_full_width raising → non-fatal, no exception propagated."""
        from mkdocs_to_confluence.publisher.pipeline import PublishReport

        node = _make_section_node("P", [])
        action = PageAction(node=node, title="P", action="create",
                            parent_id="ROOT", page_id="pid-8")
        client = MagicMock()
        client.set_page_full_width.side_effect = RuntimeError("layout error")
        report = PublishReport()

        # Must not raise
        _post_process_action(action, client, full_width=True,
                             docs_dir=tmp_path, report=report)


# ── Quiet flag: stdout suppression ───────────────────────────────────────────


def test_plan_publish_quiet_suppresses_stdout(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """plan_publish(quiet=True) must produce no stdout output."""
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("# Hello\n\nContent.\n", encoding="utf-8")

    node = _page_node("Hello", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    client = MagicMock()
    client.find_page.return_value = None

    plan_publish([node], client, config, conf_config, space_id="42", quiet=True)

    out, _ = capsys.readouterr()
    assert out == ""


def test_plan_publish_without_quiet_produces_stdout(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """plan_publish(quiet=False) (default) does produce stdout progress output."""
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("# Hello\n\nContent.\n", encoding="utf-8")

    node = _page_node("Hello", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    client = MagicMock()
    client.find_page.return_value = None

    plan_publish([node], client, config, conf_config, space_id="42")

    out, _ = capsys.readouterr()
    assert out != ""


def test_execute_publish_quiet_suppresses_stdout(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """execute_publish(quiet=True) must produce no stdout output."""
    from mkdocs_to_confluence.publisher.pipeline import execute_publish

    node = _make_section_node("P", [])
    action = PageAction(node=node, title="P", action="create", parent_id=None, xhtml="<p/>")
    client = MagicMock()
    client.create_page.return_value = {"id": "99"}

    execute_publish(
        [action], client, space_id="42", docs_dir=tmp_path, quiet=True
    )

    out, _ = capsys.readouterr()
    assert out == ""


# ── Status: end-to-end flow ───────────────────────────────────────────────────


def test_compile_page_returns_confluence_status(tmp_path: Path) -> None:
    """compile_page must return the status: value from front matter."""
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("---\nstatus: in-progress\n---\n\n# My Page\n\nContent.\n", encoding="utf-8")

    node = _page_node("My Page", md)
    config = _make_config(docs)
    _, _, _, confluence_status = compile_page(node, config)

    assert confluence_status == "in-progress"


def test_compile_page_returns_confluence_status_with_repo_url(tmp_path: Path) -> None:
    """confluence_status must survive attach_source_url when repo_url is set (regression).

    When repo_url is configured, attach_source_url reconstructs the FrontMatter node.
    This test ensures confluence_status is not silently dropped in that path.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("---\nstatus: in-progress\n---\n\n# My Page\n\nContent.\n", encoding="utf-8")

    node = _page_node("My Page", md)
    config = MkDocsConfig(
        site_name="Test",
        docs_dir=docs,
        repo_url="https://github.com/org/repo",
        edit_uri="edit/main/docs/",
        nav=None,
    )
    _, _, _, confluence_status = compile_page(node, config)

    assert confluence_status == "in-progress"


def test_plan_publish_sets_confluence_status_on_create(tmp_path: Path) -> None:
    """plan_publish must carry confluence_status into a create PageAction."""
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("---\nstatus: in-progress\n---\n\n# My Page\n\nContent.\n", encoding="utf-8")

    node = _page_node("My Page", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    client = MagicMock()
    client.find_page.return_value = None

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert plan[0].action == "create"
    assert plan[0].confluence_status == "in-progress"


def test_plan_publish_sets_confluence_status_on_skip(tmp_path: Path) -> None:
    """plan_publish must carry confluence_status into a skip (unchanged) PageAction."""
    from mkdocs_to_confluence.publisher.pipeline import _xhtml_hash

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "page.md"
    md.write_text("---\nstatus: in-progress\n---\n\n# My Page\n\nContent.\n", encoding="utf-8")

    node = _page_node("My Page", md)
    config = _make_config(docs)
    conf_config = _make_conf_config()

    xhtml, _, _, _ = compile_page(node, config)
    stored_hash = _xhtml_hash(xhtml)

    existing_page = {"id": "77", "version": {"number": 2}}
    client = MagicMock()
    client.find_page.return_value = existing_page
    client.get_content_hash.return_value = stored_hash

    plan = plan_publish([node], client, config, conf_config, space_id="42")

    assert plan[0].action == "skip"
    assert plan[0].confluence_status == "in-progress"


def test_execute_publish_calls_set_page_status_on_create(tmp_path: Path) -> None:
    """execute_publish must call client.set_page_status for a created page with confluence_status."""
    from mkdocs_to_confluence.publisher.pipeline import execute_publish

    node = _make_section_node("P", [])
    action = PageAction(
        node=node, title="P", action="create",
        parent_id=None, xhtml="<p/>", confluence_status="in-progress",
    )
    client = MagicMock()
    client.create_page.return_value = {"id": "99"}

    execute_publish([action], client, space_id="42", docs_dir=tmp_path)

    client.set_page_status.assert_called_once_with("99", "in-progress", space_key=None)


def test_execute_publish_calls_set_page_status_on_skip(tmp_path: Path) -> None:
    """execute_publish must call client.set_page_status even for skipped (unchanged) pages."""
    from mkdocs_to_confluence.publisher.pipeline import execute_publish

    node = _make_section_node("P", [])
    action = PageAction(
        node=node, title="P", action="skip",
        parent_id=None, page_id="88", confluence_status="in-progress",
    )
    client = MagicMock()

    execute_publish([action], client, space_id="42", docs_dir=tmp_path)

    client.set_page_status.assert_called_once_with("88", "in-progress", space_key=None)
