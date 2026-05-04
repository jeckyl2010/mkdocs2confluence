"""Tests for abbreviation extraction, stripping, and IR expansion."""

from __future__ import annotations

from mkdocs_to_confluence.ir.nodes import (
    AbbrevFootnoteNode,
    AbbrevGlossaryBlock,
    Admonition,
    BoldNode,
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


def test_expands_first_occurrence_as_footnote():
    abbrevs = {"IAM": "Identity and Access Management"}
    nodes = (_para("The IAM platform handles IAM requests."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="The IAM platform handles IAM requests.")
    para = result[0]
    assert isinstance(para, Paragraph)
    children = para.children
    # TextNode("The ") + AbbrevFootnoteNode + TextNode(" platform handles IAM requests.")
    assert len(children) == 3
    assert isinstance(children[0], TextNode) and children[0].text == "The "
    fn = children[1]
    assert isinstance(fn, AbbrevFootnoteNode)
    assert fn.abbr == "IAM"
    assert fn.definition == "Identity and Access Management"
    assert fn.number == 1
    # Second occurrence left as plain text
    assert isinstance(children[2], TextNode)
    assert "IAM requests." in children[2].text
    # Glossary block appended
    glossary = result[1]
    assert isinstance(glossary, AbbrevGlossaryBlock)
    assert glossary.footnoted[0].abbr == "IAM"
    assert glossary.footnoted[0].number == 1


def test_expands_multiple_different_abbrevs():
    abbrevs = {"IAM": "Identity and Access Management", "RBAC": "Role-Based Access Control"}
    nodes = (_para("Use IAM and RBAC for access control."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="Use IAM and RBAC for access control.")
    para = result[0]
    footnotes = [c for c in para.children if isinstance(c, AbbrevFootnoteNode)]
    abbrs = {fn.abbr for fn in footnotes}
    assert "IAM" in abbrs
    assert "RBAC" in abbrs
    numbers = sorted(fn.number for fn in footnotes)
    assert numbers == [1, 2]


def test_no_expand_when_no_abbrevs():
    nodes = (_para("The IAM platform."),)
    result = apply_abbreviations(nodes, {})
    assert result == nodes


def test_no_expand_in_section_heading():
    abbrevs = {"IAM": "Identity and Access Management"}
    section = Section(level=2, anchor="iam", title=(TextNode("IAM Platform"),), children=())
    result = apply_abbreviations((section,), abbrevs, page_text="IAM Platform")
    heading_text = result[0].title[0].text  # type: ignore[union-attr]
    assert heading_text == "IAM Platform"  # not annotated


def test_glossary_block_appended_for_heading_only_abbrev():
    abbrevs = {"IAM": "Identity and Access Management"}
    section = Section(level=2, anchor="iam", title=(TextNode("IAM Platform"),), children=())
    result = apply_abbreviations((section,), abbrevs, page_text="IAM Platform")
    assert len(result) == 2
    glossary = result[1]
    assert isinstance(glossary, AbbrevGlossaryBlock)
    assert len(glossary.footnoted) == 0
    assert glossary.extras == (("IAM", "Identity and Access Management"),)


def test_no_glossary_when_abbrev_footnoted_inline():
    abbrevs = {"IAM": "Identity and Access Management"}
    nodes = (_para("The IAM platform."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="The IAM platform.")
    assert len(result) == 2
    assert isinstance(result[1], AbbrevGlossaryBlock)
    assert len(result[1].extras) == 0


def test_no_expand_in_table_header_cell():
    abbrevs = {"API": "Application Programming Interface"}
    header = TableRow(cells=(TableCell(children=(TextNode("API Endpoint"),), is_header=True),))
    body = TableRow(cells=(TableCell(children=(TextNode("The API docs"),), is_header=False),))
    table = Table(header=header, rows=(body,))
    result = apply_abbreviations((table,), abbrevs, page_text="API Endpoint The API docs")
    header_text = result[0].header.cells[0].children[0].text  # type: ignore[union-attr]
    assert header_text == "API Endpoint"
    body_children = result[0].rows[0].cells[0].children  # type: ignore[union-attr]
    assert any(isinstance(c, AbbrevFootnoteNode) and c.abbr == "API" for c in body_children)


def test_no_expand_in_admonition_title():
    abbrevs = {"TLS": "Transport Layer Security"}
    admonition = Admonition(
        kind="note", title="TLS Configuration",
        children=(_para("Use TLS for encryption."),),
    )
    result = apply_abbreviations((admonition,), abbrevs, page_text="TLS Configuration Use TLS for encryption.")
    assert result[0].title == "TLS Configuration"  # type: ignore[union-attr]
    body_children = result[0].children[0].children  # type: ignore[union-attr]
    assert any(isinstance(c, AbbrevFootnoteNode) and c.abbr == "TLS" for c in body_children)


def test_no_expand_in_code_block():
    abbrevs = {"SQL": "Structured Query Language"}
    code = CodeBlock(code="SELECT * FROM SQL_table", language="sql")
    result = apply_abbreviations((code,), abbrevs, page_text="SELECT * FROM SQL_table")
    assert result[0].code == "SELECT * FROM SQL_table"  # type: ignore[union-attr]


def test_no_expand_in_link_text():
    abbrevs = {"CLI": "Command Line Interface"}
    link = LinkNode(href="https://example.com", children=(TextNode("CLI tools"),))
    result = apply_abbreviations((Paragraph(children=(link,)),), abbrevs, page_text="CLI tools")
    assert result[0].children[0].children[0].text == "CLI tools"  # type: ignore[union-attr]


def test_expands_inside_bold():
    abbrevs = {"CI": "Continuous Integration"}
    bold = BoldNode(children=(TextNode("CI pipeline"),))
    result = apply_abbreviations((Paragraph(children=(bold,)),), abbrevs, page_text="CI pipeline")
    bold_children = result[0].children[0].children  # type: ignore[union-attr]
    assert any(isinstance(c, AbbrevFootnoteNode) and c.abbr == "CI" for c in bold_children)


def test_word_boundary_not_partial_match():
    abbrevs = {"API": "Application Programming Interface"}
    nodes = (_para("The RAPID response via API."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="The RAPID response via API.")
    para = result[0]
    all_text = "".join(c.text for c in para.children if isinstance(c, TextNode))
    assert "RAPID" in all_text
    assert any(isinstance(c, AbbrevFootnoteNode) and c.abbr == "API" for c in para.children)


def test_footnoted_abbrevs_not_in_extras():
    abbrevs = {"API": "Application Programming Interface", "IAM": "Identity and Access Management"}
    nodes = (_para("Use the API and IAM to authenticate."),)
    result = apply_abbreviations(nodes, abbrevs, page_text="Use the API and IAM to authenticate.")
    assert len(result) == 2
    glossary = result[1]
    assert isinstance(glossary, AbbrevGlossaryBlock)
    assert {fn.abbr for fn in glossary.footnoted} == {"API", "IAM"}
    assert len(glossary.extras) == 0


def test_abbrev_not_in_text_produces_no_glossary():
    abbrevs = {"XYZ": "Some Definition"}
    result = apply_abbreviations((_para("Nothing relevant here."),), abbrevs, page_text="Nothing relevant here.")
    assert len(result) == 1


def test_extras_sorted_alphabetically():
    abbrevs = {"RBAC": "Role-Based Access Control", "IAM": "Identity and Access Management"}
    section = Section(level=1, anchor="overview", title=(TextNode("IAM and RBAC Overview"),), children=())
    result = apply_abbreviations((section,), abbrevs, page_text="IAM and RBAC Overview")
    glossary = result[-1]
    assert isinstance(glossary, AbbrevGlossaryBlock)
    extra_abbrs = [abbr for abbr, _ in glossary.extras]
    assert extra_abbrs == sorted(extra_abbrs)
