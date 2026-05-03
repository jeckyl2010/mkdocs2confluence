"""Tests for CLI entry-point error handling."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mkdocs_to_confluence import __version__
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


class TestHelpText:
    def test_no_command_help_lists_subcommands(self, capsys) -> None:
        """main([]) help output must mention both subcommands."""
        with pytest.raises(SystemExit):
            main([])
        out = capsys.readouterr().out
        assert "preview" in out
        assert "publish" in out

    def test_preview_help_shows_examples(self, capsys) -> None:
        """mk2conf preview --help should include the examples epilog."""
        with pytest.raises(SystemExit):
            main(["preview", "--help"])
        out = capsys.readouterr().out
        assert "Examples" in out
        assert "--page" in out
        assert "--section" in out

    def test_publish_help_shows_auth_env_var(self, capsys) -> None:
        """mk2conf publish --help should include the auth env-var reference."""
        with pytest.raises(SystemExit):
            main(["publish", "--help"])
        out = capsys.readouterr().out
        assert "CONFLUENCE_API_TOKEN" in out
        assert "Authentication" in out


class TestVersionBanner:
    def test_banner_printed_when_stdout_is_tty(self, tmp_path: Path, capsys) -> None:
        """When stdout is a TTY a 'mk2conf <version>' banner should be emitted before running."""
        # Use a nonexistent config so the command exits with error after printing the banner.
        with patch("sys.stdout.isatty", return_value=True), pytest.raises(SystemExit):
            main(["preview", "--config", str(tmp_path / "missing.yml"), "--page", "index.md"])
        out = capsys.readouterr().out
        assert f"mk2conf {__version__}" in out

    def test_banner_suppressed_when_stdout_is_not_tty(self, tmp_path: Path, capsys) -> None:
        """When stdout is not a TTY (e.g. piped) the banner must not be printed."""
        with patch("sys.stdout.isatty", return_value=False), pytest.raises(SystemExit):
            main(["preview", "--config", str(tmp_path / "missing.yml"), "--page", "index.md"])
        out = capsys.readouterr().out
        assert "mk2conf" not in out

    def test_version_flag_prints_version(self, capsys) -> None:
        """--version should always print the version string regardless of TTY."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        # argparse prints to stdout for --version
        captured = capsys.readouterr()
        version_output = captured.out + captured.err
        assert f"mk2conf {__version__}" in version_output
        assert exc_info.value.code == 0


class TestQuietOutputBehavior:
    """Verify that the --quiet flag is forwarded into compile_page."""

    def _run_preview_with_quiet(self, tmp_path: Path, *, quiet: bool) -> MagicMock:
        """Set up a minimal real page and run preview, returning the compile_page mock."""
        yml = _minimal_config(tmp_path)
        (tmp_path / "docs" / "index.md").write_text("# Home\n\nHello.", encoding="utf-8")

        mock_compile = MagicMock(return_value=("<p>Hello</p>", [], ()))
        with patch("mkdocs_to_confluence.cli.compile_page", mock_compile), \
             patch("sys.stdout.isatty", return_value=False):
            flags = ["--quiet"] if quiet else []
            main(["preview", "--config", str(yml), "--page", "index.md"] + flags)

        return mock_compile

    def test_quiet_true_forwarded_to_compile_page(self, tmp_path: Path) -> None:
        """compile_page must receive quiet=True when --quiet is passed."""
        mock_compile = self._run_preview_with_quiet(tmp_path, quiet=True)
        _args, kwargs = mock_compile.call_args
        assert kwargs.get("quiet") is True

    def test_quiet_false_forwarded_to_compile_page(self, tmp_path: Path) -> None:
        """compile_page must receive quiet=False when --quiet is omitted."""
        mock_compile = self._run_preview_with_quiet(tmp_path, quiet=False)
        _args, kwargs = mock_compile.call_args
        assert kwargs.get("quiet") is False


class TestWatchFlag:
    """Parser-level tests for --watch; no live server or filesystem watching."""

    def test_watch_flag_accepted(self) -> None:
        from mkdocs_to_confluence.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["preview", "--page", "x.md", "--watch"])
        assert args.watch is True

    def test_watch_flag_defaults_false(self) -> None:
        from mkdocs_to_confluence.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["preview", "--page", "x.md"])
        assert args.watch is False

    def test_watch_with_section_accepted(self) -> None:
        from mkdocs_to_confluence.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["preview", "--section", "Guide", "--watch"])
        assert args.watch is True
        assert args.section == "Guide"

    def test_watch_renders_html_not_raw_xhtml(self, tmp_path: Path) -> None:
        """--watch must invoke render_page (HTML output), never raw XHTML."""
        yml = _minimal_config(tmp_path)
        (tmp_path / "docs" / "index.md").write_text("# Home\n", encoding="utf-8")

        mock_compile = MagicMock(return_value=("<p>Hello</p>", [], ()))
        mock_render = MagicMock(return_value="<html>preview</html>")

        with patch("mkdocs_to_confluence.cli.compile_page", mock_compile), \
             patch("mkdocs_to_confluence.cli.render_page", mock_render), \
             patch("mkdocs_to_confluence.cli.inject_livereload", return_value="<html>preview</html>"), \
             patch("mkdocs_to_confluence.preview.server.start_server"), \
             patch("mkdocs_to_confluence.preview.server.watch_and_rebuild",
                   side_effect=KeyboardInterrupt), \
             patch("webbrowser.open"), \
             patch("sys.stdout.isatty", return_value=False):
            main(["preview", "--config", str(yml), "--page", "index.md", "--watch"])

        mock_render.assert_called_once()
