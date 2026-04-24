"""Tests for YAML front matter extraction, mapping, and emission."""

from __future__ import annotations

from mkdocs_to_confluence.emitter.xhtml import _source_link_label, emit
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


def test_source_url_renders_as_link_row():
    fm = FrontMatter(
        title=None,
        subtitle=None,
        properties=(),
        labels=(),
        source_url="https://github.com/org/repo/edit/main/docs/index.md",
    )
    xhtml = emit((fm,))
    assert 'ac:name="details"' in xhtml
    assert '<th>Source</th>' in xhtml
    assert 'href="https://github.com/org/repo/edit/main/docs/index.md"' in xhtml


def test_source_url_appears_after_other_properties():
    fm = FrontMatter(
        title=None,
        subtitle=None,
        properties=(("Version", "2.0"),),
        labels=(),
        source_url="https://example.com/edit",
    )
    xhtml = emit((fm,))
    version_pos = xhtml.index("Version")
    source_pos = xhtml.index("Source")
    assert source_pos > version_pos, "Source row should appear after other properties"


def test_source_url_alone_still_emits_details_macro():
    """A page with no front matter but a source_url should show the table."""
    fm = FrontMatter(title=None, subtitle=None, properties=(), labels=(), source_url="https://example.com/edit")
    xhtml = emit((fm,))
    assert 'ac:name="details"' in xhtml
    assert '<th>Source</th>' in xhtml


# --- _source_link_label ---

def test_source_link_label_github():
    assert _source_link_label("https://github.com/org/repo/edit/main/docs/page.md") == "Edit in GitHub ↗"


def test_source_link_label_gitlab_dot_com():
    assert _source_link_label("https://gitlab.com/org/repo/-/edit/main/docs/page.md") == "Edit in GitLab ↗"


def test_source_link_label_self_hosted_gitlab():
    assert _source_link_label("https://gitlab.mycompany.com/org/repo/-/edit/main/docs/page.md") == "Edit in GitLab ↗"


def test_source_link_label_bitbucket():
    assert _source_link_label("https://bitbucket.org/org/repo/src/main/docs/page.md") == "Edit in Bitbucket ↗"


def test_source_link_label_unknown_host_fallback():
    assert _source_link_label("https://example.com/edit") == "Edit source ↗"


def test_source_link_label_renders_in_xhtml():
    fm = FrontMatter(
        title=None, subtitle=None, properties=(), labels=(),
        source_url="https://github.com/org/repo/edit/main/docs/index.md",
    )
    xhtml = emit((fm,))
    assert "Edit in GitHub" in xhtml
