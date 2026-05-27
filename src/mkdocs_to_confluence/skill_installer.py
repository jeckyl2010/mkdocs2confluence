"""Install the bundled mkdocs-changelog skill into detected AI tool directories."""

from __future__ import annotations

import re
from pathlib import Path

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)
_SKILL_NAME = "mkdocs-changelog"


def _read_skill() -> str:
    from importlib.resources import files
    return files("mkdocs_to_confluence").joinpath(f"skills/{_SKILL_NAME}/SKILL.md").read_text(encoding="utf-8")


def _strip_front_matter(content: str) -> str:
    return _FRONT_MATTER_RE.sub("", content).lstrip("\n")


def install_skill(
    project_dir: Path | None = None,
    tool: str | None = None,
) -> list[tuple[str, Path]]:
    """Detect AI tools and install the changelog skill.

    Args:
        project_dir: Root of the current project (default: ``Path.cwd()``).
        tool: If given, install only to this tool name (``hermes``, ``claude``,
              ``copilot``, ``cursor``). Skips detection and always writes.

    Returns:
        List of ``(tool_name, install_path)`` pairs for each file written.
    """
    if project_dir is None:
        project_dir = Path.cwd()

    content_full = _read_skill()
    content_body = _strip_front_matter(content_full)

    installed: list[tuple[str, Path]] = []
    explicit = tool is not None

    def _want(name: str) -> bool:
        return tool is None or tool == name

    # Hermes — user-level, installed regardless of project directory
    if _want("hermes"):
        hermes_dir = Path.home() / ".hermes"
        if explicit or hermes_dir.exists():
            dest = hermes_dir / "skills" / "tooling" / _SKILL_NAME / "SKILL.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content_full, encoding="utf-8")
            installed.append(("hermes", dest))

    # .github/skills — project-level, skills repo format (full SKILL.md)
    if _want("github-skills"):
        gh_skills = project_dir / ".github" / "skills"
        if explicit or gh_skills.exists():
            dest = gh_skills / "tooling" / _SKILL_NAME / "SKILL.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content_full, encoding="utf-8")
            installed.append(("github-skills", dest))

    # Claude Code — project-level, YAML frontmatter stripped
    if _want("claude"):
        claude_dir = project_dir / ".claude"
        if explicit or claude_dir.exists():
            dest = claude_dir / "commands" / "mk2conf-changelog.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content_body, encoding="utf-8")
            installed.append(("claude", dest))

    # GitHub Copilot — project-level, body only as .instructions.md
    if _want("copilot"):
        copilot_marker = project_dir / ".github" / "copilot-instructions.md"
        if explicit or copilot_marker.exists():
            dest = project_dir / ".github" / "instructions" / "mk2conf-changelog.instructions.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content_body, encoding="utf-8")
            installed.append(("copilot", dest))

    # Cursor — project-level, body as .mdc
    if _want("cursor"):
        cursor_dir = project_dir / ".cursor"
        if explicit or cursor_dir.exists():
            dest = cursor_dir / "rules" / "mk2conf-changelog.mdc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content_body, encoding="utf-8")
            installed.append(("cursor", dest))

    # Fallback — no markers detected in auto mode
    if not installed and not explicit:
        dest = project_dir / ".mk2conf" / "changelog-skill.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content_full, encoding="utf-8")
        installed.append(("fallback", dest))

    return installed
