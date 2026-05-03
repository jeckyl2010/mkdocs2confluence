"""Tests for pdf/render.py and pdf/generator.py, and the pdf CLI subcommand."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mkdocs_to_confluence.pdf.render import _anchor, build_pdf_html

# ── pdf/render.py ─────────────────────────────────────────────────────────────


class TestAnchor:
    def test_simple(self) -> None:
        assert _anchor("Getting Started") == "getting-started"

    def test_special_chars(self) -> None:
        assert _anchor("Guide/Setup & Config") == "guide-setup---config"

    def test_numeric(self) -> None:
        assert _anchor("Step 1") == "step-1"


class TestBuildPdfHtml:
    def _make(self, **kwargs: object) -> str:
        return build_pdf_html(
            "My Section",
            [("Intro", "<p>Hello</p>"), ("Setup", "<p>World</p>")],
            **kwargs,  # type: ignore[arg-type]
        )

    def test_is_valid_html(self) -> None:
        html = self._make()
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_cover_contains_title(self) -> None:
        html = self._make()
        assert "My Section" in html

    def test_cover_contains_date(self) -> None:
        from datetime import date

        html = self._make()
        assert date.today().strftime("%Y") in html

    def test_cover_author_shown(self) -> None:
        html = self._make(author="Jane Doe")
        assert "Jane Doe" in html

    def test_cover_version_shown(self) -> None:
        html = self._make(version="v2.0")
        assert "v2.0" in html

    def test_cover_no_subtitle_when_empty(self) -> None:
        html = self._make()
        assert 'class="subtitle"' not in html

    def test_toc_lists_all_chapters(self) -> None:
        html = self._make()
        assert "Intro" in html
        assert "Setup" in html

    def test_toc_links_use_anchors(self) -> None:
        html = self._make()
        assert 'href="#intro"' in html
        assert 'href="#setup"' in html

    def test_chapters_have_articles(self) -> None:
        html = self._make()
        assert html.count("<article") == 2

    def test_chapter_ids_match_toc(self) -> None:
        html = self._make()
        assert 'id="intro"' in html
        assert 'id="setup"' in html

    def test_chapter_content_rendered(self) -> None:
        html = self._make()
        assert "<p>Hello</p>" in html
        assert "<p>World</p>" in html

    def test_pdf_css_included(self) -> None:
        html = self._make()
        assert "@page" in html
        assert "page-break-before" in html

    def test_macros_are_rendered(self) -> None:
        """XHTML macros in chapters are translated to HTML (not left as raw XML)."""
        macro = (
            '<ac:structured-macro ac:name="info">'
            "<ac:rich-text-body><p>tip</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        html = build_pdf_html("S", [("P", macro)])
        assert "ac:structured-macro" not in html
        assert "tip" in html


# ── pdf/generator.py ──────────────────────────────────────────────────────────


class TestWritePdf:
    def test_calls_weasyprint(self, tmp_path: Path) -> None:
        mock_wp = MagicMock()
        mock_html_instance = MagicMock()
        mock_wp.HTML.return_value = mock_html_instance
        out = tmp_path / "out.pdf"

        with patch.dict(sys.modules, {"weasyprint": mock_wp}):
            from importlib import reload

            import mkdocs_to_confluence.pdf.generator as gen_mod
            reload(gen_mod)
            gen_mod.write_pdf("<html></html>", out)

        mock_wp.HTML.assert_called_once_with(string="<html></html>")
        mock_html_instance.write_pdf.assert_called_once_with(str(out))

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        mock_wp = MagicMock()
        mock_wp.HTML.return_value = MagicMock()
        out = tmp_path / "subdir" / "nested" / "out.pdf"

        with patch.dict(sys.modules, {"weasyprint": mock_wp}):
            from importlib import reload

            import mkdocs_to_confluence.pdf.generator as gen_mod
            reload(gen_mod)
            gen_mod.write_pdf("<html></html>", out)

        assert out.parent.exists()

    def test_missing_weasyprint_raises_import_error(self, tmp_path: Path) -> None:
        with patch.dict(sys.modules, {"weasyprint": None}):  # type: ignore[dict-item]
            from importlib import reload

            import mkdocs_to_confluence.pdf.generator as gen_mod
            reload(gen_mod)
            with pytest.raises(ImportError, match="pip install"):
                gen_mod.write_pdf("<html></html>", tmp_path / "out.pdf")


# ── CLI: mk2conf pdf ───────────────────────────────────────────────────────────


class TestPdfCli:
    """Tests for the `pdf` subcommand in cli.py."""

    def _run(self, argv: list[str], config_path: Path) -> None:
        from mkdocs_to_confluence.cli import main
        main(["--"] + argv if argv[0].startswith("-") else argv)

    def test_requires_section_or_page(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        cfg = tmp_path / "mkdocs.yml"
        cfg.write_text("site_name: T\ndocs_dir: docs\nnav:\n  - Home: index.md\n")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "index.md").write_text("# Home\n")

        with pytest.raises(SystemExit, match="1"):
            from mkdocs_to_confluence.cli import main
            main(["pdf", "--config", str(cfg)])

        err = capsys.readouterr().err
        assert "--section or --page" in err

    def test_section_not_found(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        cfg = tmp_path / "mkdocs.yml"
        cfg.write_text("site_name: T\ndocs_dir: docs\nnav:\n  - Home: index.md\n")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "index.md").write_text("# Home\n")

        with pytest.raises(SystemExit, match="1"):
            from mkdocs_to_confluence.cli import main
            main(["pdf", "--config", str(cfg), "--section", "Missing"])

        assert "not found in nav" in capsys.readouterr().err

    def test_pdf_written(self, tmp_path: Path) -> None:
        cfg = tmp_path / "mkdocs.yml"
        cfg.write_text("site_name: T\ndocs_dir: docs\nnav:\n  - Home: index.md\n")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "index.md").write_text("# Home\nHello world.\n")
        out = tmp_path / "out.pdf"

        import mkdocs_to_confluence.pdf.generator as gen_mod
        mock_write = MagicMock()
        original = gen_mod.write_pdf
        gen_mod.write_pdf = mock_write  # type: ignore[assignment]
        try:
            from mkdocs_to_confluence.cli import main
            main(["pdf", "--config", str(cfg), "--page", "index.md", "--out", str(out), "--quiet"])
            mock_write.assert_called_once()
            call_args = mock_write.call_args
            assert "Home" in call_args[0][0]
            assert call_args[0][1] == out
        finally:
            gen_mod.write_pdf = original  # type: ignore[assignment]
