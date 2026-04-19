"""Tests for preprocess.includes — Milestone 3."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mkdocs_to_confluence.preprocess.includes import IncludeError, preprocess_includes


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_file(directory: Path, name: str, content: str) -> Path:
    """Write *content* to *directory/name* and return the path."""
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ── Happy path ───────────────────────────────────────────────────────────────


class TestHappyPath:
    def test_no_directives_unchanged(self, tmp_path: Path) -> None:
        src = make_file(tmp_path, "page.md", "# Hello\n\nNo includes here.\n")
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert result == src.read_text()

    def test_single_include_inlined(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snippet.md", "Snippet content.\n")
        src = make_file(tmp_path, "page.md", '--8<-- "snippet.md"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "Snippet content." in result

    def test_directive_line_replaced(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snippet.md", "Included.\n")
        src = make_file(tmp_path, "page.md", '--8<-- "snippet.md"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "--8<--" not in result

    def test_surrounding_content_preserved(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "MIDDLE\n")
        src = make_file(
            tmp_path,
            "page.md",
            """\
            BEFORE
            --8<-- "snip.md"
            AFTER
            """,
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "BEFORE" in result
        assert "MIDDLE" in result
        assert "AFTER" in result

    def test_include_resolved_relative_to_docs_dir(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "shared.md").write_text("From docs_dir.\n", encoding="utf-8")
        src = make_file(docs / "sub", "page.md", '--8<-- "shared.md"\n')
        result = preprocess_includes(src.read_text(), src, docs)
        assert "From docs_dir." in result

    def test_include_falls_back_to_sibling_resolution(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        # The snippet lives next to the source file, NOT under docs_dir root
        sub = docs / "sub"
        sub.mkdir()
        (sub / "sibling.md").write_text("Sibling content.\n", encoding="utf-8")
        src = make_file(sub, "page.md", '--8<-- "sibling.md"\n')
        result = preprocess_includes(src.read_text(), src, docs)
        assert "Sibling content." in result

    def test_multiple_includes(self, tmp_path: Path) -> None:
        make_file(tmp_path, "a.md", "AAA\n")
        make_file(tmp_path, "b.md", "BBB\n")
        src = make_file(
            tmp_path,
            "page.md",
            '--8<-- "a.md"\n--8<-- "b.md"\n',
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "AAA" in result
        assert "BBB" in result

    def test_result_ends_with_newline_after_include(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "No trailing newline")
        src = make_file(tmp_path, "page.md", '--8<-- "snip.md"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert result.endswith("\n")

    def test_using_real_shared_fixture(self, docs_dir: Path) -> None:
        src = docs_dir / "snippets" / "shared.md"
        text = src.read_text(encoding="utf-8")
        # No directives in shared.md itself — should be returned unchanged.
        result = preprocess_includes(text, src, docs_dir)
        assert result == text


# ── Line-range includes ──────────────────────────────────────────────────────


class TestLineRangeIncludes:
    def test_line_range_returns_subset(self, tmp_path: Path) -> None:
        content = "line1\nline2\nline3\nline4\nline5\n"
        make_file(tmp_path, "multi.md", content)
        src = make_file(tmp_path, "page.md", '--8<-- "multi.md:2:4"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "line2" in result
        assert "line3" in result
        assert "line4" in result
        assert "line1" not in result
        assert "line5" not in result

    def test_single_line_range(self, tmp_path: Path) -> None:
        make_file(tmp_path, "multi.md", "A\nB\nC\n")
        src = make_file(tmp_path, "page.md", '--8<-- "multi.md:2:2"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert result.strip() == "B"

    def test_full_range_equals_whole_file(self, tmp_path: Path) -> None:
        content = "X\nY\nZ\n"
        make_file(tmp_path, "multi.md", content)
        src_range = make_file(tmp_path, "range.md", '--8<-- "multi.md:1:3"\n')
        src_full = make_file(tmp_path, "full.md", '--8<-- "multi.md"\n')
        r1 = preprocess_includes(src_range.read_text(), src_range, tmp_path)
        r2 = preprocess_includes(src_full.read_text(), src_full, tmp_path)
        assert r1 == r2


# ── Nested includes ──────────────────────────────────────────────────────────


class TestNestedIncludes:
    def test_nested_include_resolved(self, tmp_path: Path) -> None:
        make_file(tmp_path, "inner.md", "Inner content.\n")
        make_file(tmp_path, "middle.md", '--8<-- "inner.md"\n')
        src = make_file(tmp_path, "page.md", '--8<-- "middle.md"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "Inner content." in result

    def test_three_level_nesting(self, tmp_path: Path) -> None:
        make_file(tmp_path, "level3.md", "DEEP\n")
        make_file(tmp_path, "level2.md", '--8<-- "level3.md"\n')
        make_file(tmp_path, "level1.md", '--8<-- "level2.md"\n')
        src = make_file(tmp_path, "page.md", '--8<-- "level1.md"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "DEEP" in result

    def test_nested_include_directive_not_present_in_result(
        self, tmp_path: Path
    ) -> None:
        make_file(tmp_path, "inner.md", "INNER\n")
        make_file(tmp_path, "middle.md", '--8<-- "inner.md"\n')
        src = make_file(tmp_path, "page.md", '--8<-- "middle.md"\n')
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "--8<--" not in result

    def test_real_nested_fixture(self, docs_dir: Path) -> None:
        """level2.md includes shared.md — both are real fixture files."""
        src = docs_dir / "snippets" / "level2.md"
        result = preprocess_includes(src.read_text(), src, docs_dir)
        assert "shared snippet content" in result.lower()
        assert "End of level 2" in result
        assert "--8<--" not in result

    def test_same_snippet_included_twice_is_ok(self, tmp_path: Path) -> None:
        make_file(tmp_path, "shared.md", "SHARED\n")
        src = make_file(
            tmp_path,
            "page.md",
            '--8<-- "shared.md"\n--8<-- "shared.md"\n',
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert result.count("SHARED") == 2


# ── Missing include ──────────────────────────────────────────────────────────


class TestMissingInclude:
    def test_missing_file_raises_include_error(self, tmp_path: Path) -> None:
        src = make_file(tmp_path, "page.md", '--8<-- "ghost.md"\n')
        with pytest.raises(IncludeError):
            preprocess_includes(src.read_text(), src, tmp_path)

    def test_error_contains_missing_filename(self, tmp_path: Path) -> None:
        src = make_file(tmp_path, "page.md", '--8<-- "ghost.md"\n')
        with pytest.raises(IncludeError, match="ghost.md"):
            preprocess_includes(src.read_text(), src, tmp_path)

    def test_error_contains_line_number(self, tmp_path: Path) -> None:
        src = make_file(
            tmp_path,
            "page.md",
            "# Heading\n\n--8<-- \"ghost.md\"\n",
        )
        with pytest.raises(IncludeError, match=":3:"):
            preprocess_includes(src.read_text(), src, tmp_path)

    def test_error_contains_source_path(self, tmp_path: Path) -> None:
        src = make_file(tmp_path, "page.md", '--8<-- "ghost.md"\n')
        with pytest.raises(IncludeError, match="page.md"):
            preprocess_includes(src.read_text(), src, tmp_path)

    def test_missing_nested_include_raises(self, tmp_path: Path) -> None:
        make_file(tmp_path, "middle.md", '--8<-- "ghost.md"\n')
        src = make_file(tmp_path, "page.md", '--8<-- "middle.md"\n')
        with pytest.raises(IncludeError, match="ghost.md"):
            preprocess_includes(src.read_text(), src, tmp_path)


# ── Circular includes ─────────────────────────────────────────────────────────


class TestCircularIncludes:
    def test_circular_raises_include_error(self, tmp_path: Path) -> None:
        a = make_file(tmp_path, "a.md", '--8<-- "b.md"\n')
        make_file(tmp_path, "b.md", '--8<-- "a.md"\n')
        with pytest.raises(IncludeError):
            preprocess_includes(a.read_text(), a, tmp_path)

    def test_circular_error_mentions_circular(self, tmp_path: Path) -> None:
        a = make_file(tmp_path, "a.md", '--8<-- "b.md"\n')
        make_file(tmp_path, "b.md", '--8<-- "a.md"\n')
        with pytest.raises(IncludeError, match="circular"):
            preprocess_includes(a.read_text(), a, tmp_path)

    def test_real_circular_fixtures(self, docs_dir: Path) -> None:
        src = docs_dir / "snippets" / "circular_a.md"
        with pytest.raises(IncludeError, match="circular"):
            preprocess_includes(src.read_text(), src, docs_dir)

    def test_self_include_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "self.md"
        src.write_text('--8<-- "self.md"\n', encoding="utf-8")
        with pytest.raises(IncludeError, match="circular"):
            preprocess_includes(src.read_text(), src, tmp_path)


# ── Fence-block awareness ────────────────────────────────────────────────────


class TestFenceBlockAwareness:
    def test_directive_inside_backtick_fence_not_expanded(
        self, tmp_path: Path
    ) -> None:
        make_file(tmp_path, "snip.md", "SHOULD NOT APPEAR\n")
        src = make_file(
            tmp_path,
            "page.md",
            '```\n--8<-- "snip.md"\n```\n',
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "SHOULD NOT APPEAR" not in result
        assert '--8<-- "snip.md"' in result

    def test_directive_inside_tilde_fence_not_expanded(
        self, tmp_path: Path
    ) -> None:
        make_file(tmp_path, "snip.md", "SHOULD NOT APPEAR\n")
        src = make_file(
            tmp_path,
            "page.md",
            '~~~\n--8<-- "snip.md"\n~~~\n',
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "SHOULD NOT APPEAR" not in result

    def test_directive_after_fence_is_expanded(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "AFTER FENCE\n")
        src = make_file(
            tmp_path,
            "page.md",
            '```\ncode\n```\n--8<-- "snip.md"\n',
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "AFTER FENCE" in result

    def test_longer_fence_marker_tracked_correctly(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "SHOULD NOT APPEAR\n")
        src = make_file(
            tmp_path,
            "page.md",
            '````python\n--8<-- "snip.md"\n````\n',
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "SHOULD NOT APPEAR" not in result

    def test_directive_in_info_string_fence_not_expanded(
        self, tmp_path: Path
    ) -> None:
        """A fence opening with an info string (e.g. ```python) must still open."""
        make_file(tmp_path, "snip.md", "NOPE\n")
        src = make_file(
            tmp_path,
            "page.md",
            '```python\n--8<-- "snip.md"\n```\n',
        )
        result = preprocess_includes(src.read_text(), src, tmp_path)
        assert "NOPE" not in result


# ── Invalid / unsupported syntax ─────────────────────────────────────────────


class TestInvalidSyntax:
    def test_named_section_raises_include_error(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "content\n")
        src = make_file(tmp_path, "page.md", '--8<-- "snip.md:mysection"\n')
        with pytest.raises(IncludeError, match="named-section"):
            preprocess_includes(src.read_text(), src, tmp_path)

    def test_invalid_line_range_raises_include_error(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "A\nB\n")
        src = make_file(tmp_path, "page.md", '--8<-- "snip.md:abc:xyz"\n')
        with pytest.raises(IncludeError, match="named-section"):
            preprocess_includes(src.read_text(), src, tmp_path)

    def test_inverted_range_raises_include_error(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "A\nB\nC\n")
        src = make_file(tmp_path, "page.md", '--8<-- "snip.md:3:1"\n')
        with pytest.raises(IncludeError, match="invalid line range"):
            preprocess_includes(src.read_text(), src, tmp_path)

    def test_zero_start_raises_include_error(self, tmp_path: Path) -> None:
        make_file(tmp_path, "snip.md", "A\nB\n")
        src = make_file(tmp_path, "page.md", '--8<-- "snip.md:0:2"\n')
        with pytest.raises(IncludeError, match="invalid line range"):
            preprocess_includes(src.read_text(), src, tmp_path)


# ── strip_html_comments ───────────────────────────────────────────────────────


from mkdocs_to_confluence.preprocess.includes import strip_html_comments


class TestStripHtmlComments:
    def test_removes_single_line_comment(self) -> None:
        text = "<!-- a comment -->\n*[IAM]: Identity and Access Management\n"
        result = strip_html_comments(text)
        assert "<!--" not in result
        assert "*[IAM]" in result

    def test_removes_multiline_comment(self) -> None:
        text = "Before\n<!-- this spans\nmultiple lines -->\nAfter\n"
        result = strip_html_comments(text)
        assert "<!--" not in result
        assert "Before" in result
        assert "After" in result

    def test_removes_inline_comment(self) -> None:
        text = "Some text <!-- note --> more text\n"
        result = strip_html_comments(text)
        assert "<!--" not in result
        assert "Some text" in result
        assert "more text" in result

    def test_leaves_fenced_code_untouched(self) -> None:
        text = "```html\n<!-- kept -->\n```\n"
        result = strip_html_comments(text)
        assert "<!-- kept -->" in result

    def test_no_comments_unchanged(self) -> None:
        text = "# Heading\n\nParagraph.\n"
        assert strip_html_comments(text) == text

    def test_multiple_comments_all_removed(self) -> None:
        text = "<!-- one -->\nContent\n<!-- two -->\n"
        result = strip_html_comments(text)
        assert "one" not in result
        assert "two" not in result
        assert "Content" in result

    def test_abbreviation_file_pattern(self) -> None:
        text = (
            "<!-- Abbreviation tooltips (apply where snippet is included) -->\n"
            "*[ACID]: Atomicity, Consistency, Isolation, and Durability\n"
            "*[AD]: Active Directory\n"
        )
        result = strip_html_comments(text)
        assert "<!--" not in result
        assert "*[ACID]" in result
        assert "*[AD]" in result
