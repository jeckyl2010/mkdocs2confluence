"""Tests for YAML front matter extraction, mapping, and emission."""

from __future__ import annotations

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import FrontMatter
from mkdocs_to_confluence.preprocess.frontmatter import extract_front_matter

_SAMPLE = """\
---
title: "Architecture Proposal – IAM"
subtitle: "Hybrid Identity Hub for manufacturing sites"
documentId: AP-IAM-HYBRID-2026
version: "0.1"
lastUpdated: 2026-01-12
author: "Anders Hybertz"
tags: [architecture, iam, keycloak]
ready: true
source: "docs/proposals/2026/iam-platform.md"
---

# Overview

Content here.
"""


# ── extract_front_matter ──────────────────────────────────────────────────────


def test_extracts_title():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    assert fm.title == "Architecture Proposal – IAM"


def test_extracts_subtitle():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    assert fm.subtitle == "Hybrid Identity Hub for manufacturing sites"


def test_extracts_labels_from_tags():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    assert "architecture" in fm.labels
    assert "iam" in fm.labels
    assert "keycloak" in fm.labels


def test_strips_source_field():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    prop_keys = [k for k, _ in fm.properties]
    assert "Source" not in prop_keys
    assert "source" not in prop_keys


def test_ready_true_becomes_ready_status():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    statuses = [v for k, v in fm.properties if k == "Status"]
    assert statuses == ["✅ Ready"]


def test_ready_false_becomes_draft_status():
    text = "---\nready: false\n---\n\nContent.\n"
    fm, _ = extract_front_matter(text)
    assert fm is not None
    statuses = [v for k, v in fm.properties if k == "Status"]
    assert statuses == ["📝 Draft"]


def test_document_id_display_name():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    prop_keys = [k for k, _ in fm.properties]
    assert "Document ID" in prop_keys


def test_last_updated_display_name():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    prop_keys = [k for k, _ in fm.properties]
    assert "Last Updated" in prop_keys


def test_remaining_text_excludes_front_matter():
    _, remaining = extract_front_matter(_SAMPLE)
    assert "---" not in remaining.split("\n")[0]
    assert "# Overview" in remaining


def test_no_front_matter_returns_none_and_original():
    text = "# Just a heading\n\nParagraph.\n"
    fm, remaining = extract_front_matter(text)
    assert fm is None
    assert remaining == text


def test_tags_joined_in_properties():
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    tags_values = [v for k, v in fm.properties if k == "Tags"]
    assert len(tags_values) == 1
    assert "architecture" in tags_values[0]
    assert "iam" in tags_values[0]


def test_subtitle_not_in_properties_table():
    """Subtitle is rendered separately as a lead paragraph, not in the table."""
    fm, _ = extract_front_matter(_SAMPLE)
    assert fm is not None
    prop_keys = [k for k, _ in fm.properties]
    assert "Subtitle" not in prop_keys


def test_unknown_field_humanized():
    text = "---\nmyCustomField: hello\n---\n\nContent.\n"
    fm, _ = extract_front_matter(text)
    assert fm is not None
    prop_keys = [k for k, _ in fm.properties]
    assert "My Custom Field" in prop_keys


def test_invalid_yaml_returns_none():
    text = "---\n: invalid: yaml: [\n---\n\nContent.\n"
    fm, remaining = extract_front_matter(text)
    assert fm is None


def test_status_extracted_as_confluence_status():
    """status: in front matter is stored in confluence_status, not the table."""
    text = "---\nstatus: in-progress\n---\n\nContent.\n"
    fm, _ = extract_front_matter(text)
    assert fm is not None
    assert fm.confluence_status == "in-progress"
    prop_keys = [k for k, _ in fm.properties]
    assert "Status" not in prop_keys


def test_status_absent_is_none():
    """When status: is absent, confluence_status is None."""
    text = "---\ntitle: My Page\n---\n\nContent.\n"
    fm, _ = extract_front_matter(text)
    assert fm is not None
    assert fm.confluence_status is None


# ── emitter ───────────────────────────────────────────────────────────────────


def test_emits_details_macro():
    fm = FrontMatter(
        title="My Doc",
        subtitle=None,
        properties=(("Title", "My Doc"), ("Version", "1.0")),
        labels=(),
    )
    xhtml = emit((fm,))
    assert 'ac:name="details"' in xhtml
    assert '<th>Title</th>' in xhtml
    assert "<td>My Doc</td>" in xhtml
    assert '<th>Version</th>' in xhtml
    assert "<td>1.0</td>" in xhtml


def test_emits_subtitle_as_italic_paragraph():
    fm = FrontMatter(
        title=None,
        subtitle="A great subtitle",
        properties=(),
        labels=(),
    )
    xhtml = emit((fm,))
    assert "<em>A great subtitle</em>" in xhtml
    assert "<p>" in xhtml


def test_no_output_when_no_properties_and_no_subtitle():
    fm = FrontMatter(title=None, subtitle=None, properties=(), labels=())
    xhtml = emit((fm,))
    assert xhtml == ""


def test_special_chars_escaped_in_properties():
    fm = FrontMatter(
        title=None,
        subtitle=None,
        properties=(("Author", "O'Brien & Co <Ltd>"),),
        labels=(),
    )
    xhtml = emit((fm,))
    assert "&amp;" in xhtml
    assert "&lt;" in xhtml
    assert "O&#x27;Brien" in xhtml or "O&apos;Brien" in xhtml or "O&#39;" in xhtml or "O'" not in xhtml


class TestExcludeProperties:
    def test_excluded_key_omitted_from_table(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("version",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Version" not in labels

    def test_non_excluded_keys_retained(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("version",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Author" in labels
        assert "Document ID" in labels

    def test_excluding_tags_still_yields_labels(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("tags",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Tags" not in labels
        # side-effect preserved: tags still become Confluence labels
        assert fm.labels == ("architecture", "iam", "keycloak")

    def test_excluding_title_keeps_page_title(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("title",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Title" not in labels
        assert fm.title == "Architecture Proposal – IAM"

    def test_excluding_nonexistent_key_is_noop(self) -> None:
        baseline, _ = extract_front_matter(_SAMPLE)
        excluded, _ = extract_front_matter(_SAMPLE, exclude_properties=("not_here",))
        assert baseline is not None and excluded is not None
        assert baseline.properties == excluded.properties

    def test_exclude_is_case_sensitive(self) -> None:
        # 'Version' != 'version' — wrong case does not exclude
        fm, _ = extract_front_matter(_SAMPLE, exclude_properties=("Version",))
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Version" in labels

    def test_default_no_exclude_preserves_behavior(self) -> None:
        fm, _ = extract_front_matter(_SAMPLE)
        assert fm is not None
        labels = [display for display, _ in fm.properties]
        assert "Version" in labels and "Author" in labels
