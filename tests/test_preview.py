"""Tests for the local browser preview renderer."""

from __future__ import annotations

from mkdocs_to_confluence.preview.render import render_html, render_page


class TestRenderHtml:
    def test_passthrough_plain_html(self) -> None:
        html = "<p>Hello world.</p>"
        assert render_html(html) == html

    def test_code_macro_renders_pre(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">python</ac:parameter>'
            "<ac:plain-text-body><![CDATA[print('hi')]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "<pre>" in out
        assert "<code" in out
        assert "print(&#x27;hi&#x27;)" in out  # html-escaped

    def test_code_macro_shows_language(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">bash</ac:parameter>'
            "<ac:plain-text-body><![CDATA[echo hi]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "bash" in out

    def test_code_macro_no_language(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="code">'
            "<ac:plain-text-body><![CDATA[some code]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "some code" in out
        assert "<pre>" in out

    def test_info_macro_renders_panel(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="info">'
            '<ac:parameter ac:name="title">Note</ac:parameter>'
            "<ac:rich-text-body><p>body text</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "Note" in out
        assert "body text" in out
        assert "panel" in out

    def test_warning_macro_renders_panel(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="warning">'
            '<ac:parameter ac:name="title">Alert</ac:parameter>'
            "<ac:rich-text-body><p>danger</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "Alert" in out
        assert "danger" in out

    def test_expand_macro_renders_details(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="expand">'
            '<ac:parameter ac:name="title">Show more</ac:parameter>'
            "<ac:rich-text-body><p>hidden content</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "<details" in out
        assert "<summary" in out
        assert "Show more" in out
        assert "hidden content" in out

    def test_nested_code_inside_warning(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="warning">'
            '<ac:parameter ac:name="title">Heads up</ac:parameter>'
            "<ac:rich-text-body>"
            "<p>Read this:</p>"
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">bash</ac:parameter>'
            "<ac:plain-text-body><![CDATA[rm -rf /]]></ac:plain-text-body>"
            "</ac:structured-macro>"
            "</ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "Heads up" in out
        assert "Read this:" in out
        assert "rm -rf /" in out
        assert "<pre>" in out

    def test_unknown_macro_shows_placeholder(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="fancy-charts">'
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "fancy-charts" in out

    def test_no_raw_ac_tags_remain(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="info">'
            '<ac:parameter ac:name="title">T</ac:parameter>'
            "<ac:rich-text-body><p>x</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "<ac:" not in out


class TestRenderPage:
    def test_returns_full_html_document(self) -> None:
        out = render_page("<p>Hello</p>")
        assert "<!DOCTYPE html>" in out
        assert "<html>" in out
        assert "<body>" in out
        assert "Hello" in out

    def test_page_name_in_title(self) -> None:
        out = render_page("<p>x</p>", page="guide/installation.md")
        assert "guide/installation.md" in out

    def test_css_included(self) -> None:
        out = render_page("<p>x</p>")
        assert "<style>" in out
