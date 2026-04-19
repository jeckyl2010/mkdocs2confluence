"""Tests for abbreviation extraction, stripping, and IR expansion."""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import (
    Admonition,
    BoldNode,
    BulletList,
    CodeBlock,
    LinkNode,
    Paragraph,
    Section,
    Table,
    TableCell,
    TableRow,
    TextNode,
)
from mkdocs_to_confluence.preprocess.abbrevs import (
    extract_abbreviations,
    strip_abbreviation_defs,
)
from mkdocs_to_confluence.transforms.abbrevs import apply_abbreviations

# ── extract_abbreviations ─────────────────────────────────────────────────────


def test_extract_single():
    text = "*[IAM]: Identity and Access Management\n\nSome content."
    assert extract_abbreviations(text) == {"IAM": "Identity and Access Management"}


def test_extract_multiple():
    text = "*[IAM]: Identity and Access Management\n*[RBAC]: Role-Based Access Control\n"
    result = extract_abbreviations(text)
    assert result == {
        "IAM": "Identity and Access Management",
        "RBAC": "Role-Based Access Control",
    }


def test_extract_none():
    assert extract_abbreviations("No abbreviations here.") == {}


def test_extract_last_definition_wins():
    text = "*[IAM]: First\n*[IAM]: Second\n"
    assert extract_abbreviations(text) == {"IAM": "Second"}


def test_extract_strips_surrounding_whitespace():
    text = "*[TLS]:   Transport Layer Security   \n"
    assert extract_abbreviations(text) == {"TLS": "Transport Layer Security"}


# ── strip_abbreviation_defs ───────────────────────────────────────────────────


def test_strip_removes_def_lines():
    text = "Some text.\n\n*[IAM]: Identity and Access Management\n\nMore text.\n"
    result = strip_abbreviation_defs(text)
    assert "*[IAM]" not in result
    assert "Some text." in result
    assert "More text." in result


def test_strip_leaves_unrelated_lines():
    text = "Hello\n*[not a def\nWorld\n"
    assert strip_abbreviation_defs(text) == text


def test_strip_empty_result_when_only_defs():
    text = "*[A]: Alpha\n*[B]: Beta\n"
    assert strip_abbreviation_defs(text).strip() == ""


# ── apply_abbreviations — expansion ──────────────────────────────────────────


def _para(text: str) -> Paragraph:
    return Paragraph(children=(TextNode(text),))


def test_expands_first_occurrence_in_paragraph():
    abbrevs = {"IAM": "Identity and Access Management"}
    nodes = (_para("The IAM platform handles IAM requests."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="The IAM platform handles IAM requests.")
    para = result[0]
    assert isinstance(para, Paragraph)
    text = para.children[0].text  # type: ignore[union-attr]
    assert "IAM (Identity and Access Management)" in text
    # Second occurrence not expanded
    assert text.count("IAM (Identity and Access Management)") == 1
    assert text.endswith("IAM requests.")


def test_expands_multiple_different_abbrevs():
    abbrevs = {"IAM": "Identity and Access Management", "RBAC": "Role-Based Access Control"}
    nodes = (_para("Use IAM and RBAC for access control."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="Use IAM and RBAC for access control.")
    text = result[0].children[0].text  # type: ignore[union-attr]
    assert "IAM (Identity and Access Management)" in text
    assert "RBAC (Role-Based Access Control)" in text


def test_no_expand_when_no_abbrevs():
    nodes = (_para("The IAM platform."),)
    result = apply_abbreviations(nodes, {})
    assert result == nodes


def test_no_expand_in_section_heading():
    abbrevs = {"IAM": "Identity and Access Management"}
    section = Section(
        level=2,
        anchor="iam",
        title=(TextNode("IAM Platform"),),
        children=(),
    )
    result = apply_abbreviations((section,), abbrevs, page_text="IAM Platform")
    heading_text = result[0].title[0].text  # type: ignore[union-attr]
    assert heading_text == "IAM Platform"  # not expanded


def test_glossary_appended_for_heading_only_abbrev():
    abbrevs = {"IAM": "Identity and Access Management"}
    section = Section(
        level=2,
        anchor="iam",
        title=(TextNode("IAM Platform"),),
        children=(),
    )
    result = apply_abbreviations((section,), abbrevs, page_text="IAM Platform")
    # A Glossary section should be appended
    assert len(result) == 2
    glossary = result[1]
    assert isinstance(glossary, Section)
    assert glossary.anchor == "glossary"
    # Glossary should list the term
    bullet_list = glossary.children[0]
    assert isinstance(bullet_list, BulletList)
    item_text = bullet_list.items[0].children[0].children[0].text  # type: ignore[union-attr]
    assert "IAM" in item_text
    assert "Identity and Access Management" in item_text


def test_no_glossary_when_abbrev_expanded_inline():
    abbrevs = {"IAM": "Identity and Access Management"}
    nodes = (_para("The IAM platform."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="The IAM platform.")
    # Expanded inline, so no glossary section needed
    assert len(result) == 1


def test_no_expand_in_table_header_cell():
    abbrevs = {"API": "Application Programming Interface"}
    header = TableRow(cells=(
        TableCell(children=(TextNode("API Endpoint"),), is_header=True),
    ))
    body = TableRow(cells=(
        TableCell(children=(TextNode("The API docs"),), is_header=False),
    ))
    table = Table(header=header, rows=(body,))
    result = apply_abbreviations((table,), abbrevs, page_text="API Endpoint The API docs")

    # Header cell: not expanded
    header_text = result[0].header.cells[0].children[0].text  # type: ignore[union-attr]
    assert header_text == "API Endpoint"

    # Body cell: first occurrence expanded
    body_text = result[0].rows[0].cells[0].children[0].text  # type: ignore[union-attr]
    assert "API (Application Programming Interface)" in body_text


def test_no_expand_in_admonition_title():
    abbrevs = {"TLS": "Transport Layer Security"}
    admonition = Admonition(
        kind="note",
        title="TLS Configuration",
        children=(_para("Use TLS for encryption."),),
    )
    result = apply_abbreviations((admonition,), abbrevs, page_text="TLS Configuration Use TLS for encryption.")
    # Title is str, unchanged
    assert result[0].title == "TLS Configuration"  # type: ignore[union-attr]
    # Body paragraph: expanded
    body_text = result[0].children[0].children[0].text  # type: ignore[union-attr]
    assert "TLS (Transport Layer Security)" in body_text


def test_no_expand_in_code_block():
    abbrevs = {"SQL": "Structured Query Language"}
    code = CodeBlock(code="SELECT * FROM SQL_table", language="sql")
    nodes = (code,)
    result = apply_abbreviations(nodes, abbrevs, page_text="SELECT * FROM SQL_table")
    assert result[0].code == "SELECT * FROM SQL_table"


def test_no_expand_in_link_text():
    abbrevs = {"CLI": "Command Line Interface"}
    link = LinkNode(
        href="https://example.com",
        children=(TextNode("CLI tools"),),
    )
    para = Paragraph(children=(link,))
    result = apply_abbreviations((para,), abbrevs, page_text="CLI tools")
    link_text = result[0].children[0].children[0].text  # type: ignore[union-attr]
    assert link_text == "CLI tools"  # not expanded inside link


def test_expands_inside_bold():
    abbrevs = {"CI": "Continuous Integration"}
    bold = BoldNode(children=(TextNode("CI pipeline"),))
    para = Paragraph(children=(bold,))
    result = apply_abbreviations((para,), abbrevs, page_text="CI pipeline")
    bold_text = result[0].children[0].children[0].text  # type: ignore[union-attr]
    assert "CI (Continuous Integration)" in bold_text


def test_word_boundary_not_partial_match():
    abbrevs = {"API": "Application Programming Interface"}
    nodes = (_para("The RAPID response via API."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="The RAPID response via API.")
    text = result[0].children[0].text  # type: ignore[union-attr]
    # RAPID should not be touched; API should be expanded
    assert "RAPID" in text
    assert "API (Application Programming Interface)" in text


def test_abbrev_not_in_text_produces_no_glossary():
    abbrevs = {"XYZ": "Some Definition"}
    nodes = (_para("Nothing relevant here."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="Nothing relevant here.")
    # XYZ never mentioned → no glossary
    assert len(result) == 1


def test_glossary_entries_sorted_alphabetically():
    abbrevs = {"RBAC": "Role-Based Access Control", "IAM": "Identity and Access Management"}
    # Both only in heading (unsafe), so both go to glossary
    section = Section(
        level=1,
        anchor="overview",
        title=(TextNode("IAM and RBAC Overview"),),
        children=(),
    )
    result = apply_abbreviations(
        (section,), abbrevs, page_text="IAM and RBAC Overview"
    )
    glossary = result[-1]
    assert isinstance(glossary, Section)
    items = glossary.children[0].items  # type: ignore[union-attr]
    labels = [item.children[0].children[0].text for item in items]  # type: ignore[union-attr]
    assert labels == sorted(labels)
