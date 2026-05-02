"""Tests for CLI entry-point error handling."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mkdocs_to_confluence.cli import main


def _minimal_config(tmp_path: Path, *, extra: str = "") -> Path:
    yml = tmp_path / "mkdocs.yml"
    yml.write_text(
        textwrap.dedent(f"""\
            site_name: Test
            docs_dir: docs
            confluence:
              base_url: https://example.atlassian.net
              email: test@example.com
              token: tok
              space_key: TEST
            {extra}
        """),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    return yml


class TestMainErrorHandling:
    def test_missing_config_file_exits_cleanly(self, tmp_path: Path, capsys) -> None:
        """A missing mkdocs.yml should print 'error:' and exit 1, not traceback."""
        with pytest.raises(SystemExit) as exc_info:
            main(["preview", "--config", str(tmp_path / "nonexistent.yml"), "--page", "index.md"])
        assert exc_info.value.code == 1
        assert "error:" in capsys.readouterr().err

    def test_malformed_pages_file_exits_cleanly(self, tmp_path: Path, capsys) -> None:
        """A broken .pages file should print 'error:' and exit 1, not traceback."""
        yml = _minimal_config(tmp_path)
        docs = tmp_path / "docs"
        (docs / "index.md").write_text("# Home", encoding="utf-8")
        (docs / ".pages").write_text(": bad: yaml: [unclosed", encoding="utf-8")
        # Need nav_file configured
        yml.write_text(
            textwrap.dedent("""\
                site_name: Test
                docs_dir: docs
                confluence:
                  base_url: https://example.atlassian.net
                  email: test@example.com
                  token: tok
                  space_key: TEST
                  nav_file: ".pages"
            """),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc_info:
            main(["preview", "--config", str(yml), "--page", "index.md"])
        assert exc_info.value.code == 1
        assert "error:" in capsys.readouterr().err

    def test_no_command_prints_help(self, capsys) -> None:
        """Calling mk2conf with no subcommand prints help and exits 0."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0


class TestQuietFlag:
    def test_preview_quiet_flag_accepted(self, tmp_path: Path) -> None:
        """mk2conf preview --quiet should be accepted by the argument parser."""
        from mkdocs_to_confluence.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["preview", "--quiet", "--config", "mkdocs.yml", "--page", "index.md"])
        assert args.quiet is True

    def test_preview_quiet_short_flag_accepted(self, tmp_path: Path) -> None:
        """mk2conf preview -q should be accepted by the argument parser."""
        from mkdocs_to_confluence.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["preview", "-q", "--config", "mkdocs.yml", "--page", "index.md"])
        assert args.quiet is True

    def test_publish_quiet_flag_accepted(self, tmp_path: Path) -> None:
        """mk2conf publish --quiet should be accepted by the argument parser."""
        from mkdocs_to_confluence.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["publish", "--quiet", "--config", "mkdocs.yml"])
        assert args.quiet is True

    def test_publish_quiet_short_flag_accepted(self, tmp_path: Path) -> None:
        """mk2conf publish -q should be accepted by the argument parser."""
        from mkdocs_to_confluence.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["publish", "-q", "--config", "mkdocs.yml"])
        assert args.quiet is True

    def test_preview_quiet_default_is_false(self) -> None:
        """quiet defaults to False when not provided."""
        from mkdocs_to_confluence.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["preview", "--config", "mkdocs.yml", "--page", "index.md"])
        assert args.quiet is False
