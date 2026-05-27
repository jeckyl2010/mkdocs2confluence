"""Unit tests for skill_installer.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mkdocs_to_confluence.skill_installer import _strip_front_matter, install_skill


def test_strip_front_matter_removes_yaml_block() -> None:
    content = "---\nname: foo\nversion: 1.0.0\n---\n\n# Title\n\nBody.\n"
    result = _strip_front_matter(content)
    assert result.startswith("# Title")
    assert "name: foo" not in result


def test_strip_front_matter_no_front_matter_unchanged() -> None:
    content = "# Title\n\nBody.\n"
    assert _strip_front_matter(content) == content


def test_install_skill_hermes(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".hermes").mkdir()
    with patch("mkdocs_to_confluence.skill_installer.Path.home", return_value=fake_home):
        installed = install_skill(project_dir=tmp_path / "project", tool="hermes")

    assert len(installed) == 1
    name, dest = installed[0]
    assert name == "hermes"
    assert dest.name == "SKILL.md"
    assert "mkdocs-changelog" in str(dest)
    content = dest.read_text(encoding="utf-8")
    # Full SKILL.md with frontmatter
    assert "name: mkdocs-changelog" in content


def test_install_skill_claude(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    installed = install_skill(project_dir=tmp_path, tool="claude")

    assert len(installed) == 1
    name, dest = installed[0]
    assert name == "claude"
    assert dest == tmp_path / ".claude" / "commands" / "mk2conf-changelog.md"
    content = dest.read_text(encoding="utf-8")
    # Frontmatter stripped for Claude Code
    assert "name: mkdocs-changelog" not in content
    assert "# MkDocs Changelog Entry" in content


def test_install_skill_copilot(tmp_path: Path) -> None:
    gh = tmp_path / ".github"
    gh.mkdir()
    (gh / "copilot-instructions.md").write_text("# Copilot\n", encoding="utf-8")
    installed = install_skill(project_dir=tmp_path, tool="copilot")

    assert len(installed) == 1
    name, dest = installed[0]
    assert name == "copilot"
    assert dest.name == "mk2conf-changelog.instructions.md"
    content = dest.read_text(encoding="utf-8")
    assert "name: mkdocs-changelog" not in content


def test_install_skill_cursor(tmp_path: Path) -> None:
    (tmp_path / ".cursor").mkdir()
    installed = install_skill(project_dir=tmp_path, tool="cursor")

    assert len(installed) == 1
    name, dest = installed[0]
    assert name == "cursor"
    assert dest.name == "mk2conf-changelog.mdc"
    content = dest.read_text(encoding="utf-8")
    assert "name: mkdocs-changelog" not in content


def test_install_skill_auto_detects_multiple(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch("mkdocs_to_confluence.skill_installer.Path.home", return_value=fake_home):
        installed = install_skill(project_dir=tmp_path)

    names = {n for n, _ in installed}
    assert "claude" in names
    assert "cursor" in names


def test_install_skill_fallback_when_nothing_detected(tmp_path: Path) -> None:
    # Patch Path.home() so ~/.hermes/ is not accidentally detected
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch("mkdocs_to_confluence.skill_installer.Path.home", return_value=fake_home):
        installed = install_skill(project_dir=tmp_path)

    assert len(installed) == 1
    name, dest = installed[0]
    assert name == "fallback"
    assert dest == tmp_path / ".mk2conf" / "changelog-skill.md"


def test_install_skill_explicit_tool_ignores_detection(tmp_path: Path) -> None:
    # .claude does NOT exist — but explicit --tool claude should still install
    installed = install_skill(project_dir=tmp_path, tool="claude")

    assert len(installed) == 1
    name, dest = installed[0]
    assert name == "claude"
    assert dest.exists()


def test_install_skill_overwrites_existing(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    dest = tmp_path / ".claude" / "commands" / "mk2conf-changelog.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("old content", encoding="utf-8")

    install_skill(project_dir=tmp_path, tool="claude")

    assert dest.read_text(encoding="utf-8") != "old content"
