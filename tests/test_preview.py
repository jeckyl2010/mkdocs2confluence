"""Tests for the local browser preview renderer."""

from __future__ import annotations

import base64
from pathlib import Path

from mkdocs_to_confluence.preview.render import (
    _load_image_data,
    inject_livereload,
    render_html,
    render_index,
    render_page,
)


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

    def test_expand_title_with_ampersand_not_double_escaped(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="expand">'
            '<ac:parameter ac:name="title">Architecture &amp; Resilience</ac:parameter>'
            "<ac:rich-text-body><p>content</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "Architecture &amp; Resilience" in out
        assert "&amp;amp;" not in out

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


class TestRenderPanelMacro:
    def test_panel_macro_uses_custom_colors(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="panel">'
            '<ac:parameter ac:name="borderColor">#ff0000</ac:parameter>'
            '<ac:parameter ac:name="bgColor">#ffe0e0</ac:parameter>'
            '<ac:parameter ac:name="titleBGColor">#cc0000</ac:parameter>'
            '<ac:parameter ac:name="title">Danger</ac:parameter>'
            "<ac:rich-text-body><p>watch out</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "#ff0000" in out
        assert "#ffe0e0" in out
        assert "Danger" in out
        assert "watch out" in out

    def test_details_macro_renders_card(self) -> None:
        xhtml = (
            '<ac:structured-macro ac:name="details">'
            "<ac:rich-text-body><p>metadata here</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        out = render_html(xhtml)
        assert "Page Properties" in out
        assert "metadata here" in out


class TestRenderImage:
    def test_url_image_renders_img_tag(self) -> None:
        xhtml = (
            '<ac:image ac:alt="logo">'
            '<ri:url ri:value="https://example.com/img.png"/>'
            "</ac:image>"
        )
        out = render_html(xhtml)
        assert '<img src="https://example.com/img.png"' in out
        assert 'alt="logo"' in out

    def test_attachment_without_local_path_renders_placeholder(self) -> None:
        xhtml = (
            "<ac:image>"
            '<ri:attachment ri:filename="diagram.png"/>'
            "</ac:image>"
        )
        out = render_html(xhtml)
        assert "diagram.png" in out
        assert "Attachment" in out

    def test_attachment_with_local_path_inlines_data(self, tmp_path: Path) -> None:
        # Minimal 1×1 white PNG
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6260000000020001e221bc330000000049454e44ae426082"
        )
        img = tmp_path / "img.png"
        img.write_bytes(png)
        xhtml = (
            f'<ac:image data-local-path="{img}">'
            '<ri:attachment ri:filename="img.png"/>'
            "</ac:image>"
        )
        out = render_html(xhtml)
        assert "data:image/png;base64," in out

    def test_url_image_with_local_non_http_path_inlines_data(self, tmp_path: Path) -> None:
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6260000000020001e221bc330000000049454e44ae426082"
        )
        img = tmp_path / "local.png"
        img.write_bytes(png)
        xhtml = (
            f'<ac:image><ri:url ri:value="{img}"/></ac:image>'
        )
        out = render_html(xhtml)
        assert "data:image/png;base64," in out

    def test_image_no_src_returns_original(self) -> None:
        xhtml = "<ac:image><ri:unknown/></ac:image>"
        out = render_html(xhtml)
        assert "<ac:image>" in out


class TestLoadImageData:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = _load_image_data(tmp_path / "ghost.png")
        assert result == ""

    def test_png_returns_data_uri(self, tmp_path: Path) -> None:
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        result = _load_image_data(img)
        assert result.startswith("data:image/png;base64,")

    def test_svg_uses_svg_mime(self, tmp_path: Path) -> None:
        img = tmp_path / "icon.svg"
        img.write_bytes(b"<svg/>")
        result = _load_image_data(img)
        assert result.startswith("data:image/svg+xml;base64,")

    def test_unknown_extension_defaults_to_png_mime(self, tmp_path: Path) -> None:
        img = tmp_path / "file.bmp"
        img.write_bytes(b"BM")
        result = _load_image_data(img)
        assert result.startswith("data:image/png;base64,")

    def test_content_is_valid_base64(self, tmp_path: Path) -> None:
        img = tmp_path / "test.png"
        content = b"fake image bytes"
        img.write_bytes(content)
        result = _load_image_data(img)
        encoded = result.split(",", 1)[1]
        assert base64.b64decode(encoded) == content


class TestRewritePageLinks:
    def test_known_page_link_becomes_anchor(self) -> None:
        xhtml = (
            '<ac:link><ri:page ri:content-title="Install"/>'
            "<ac:link-body>Install</ac:link-body></ac:link>"
        )
        out = render_html(xhtml, page_link_map={"Install": "install.html"})
        assert '<a href="install.html">Install</a>' in out

    def test_unknown_page_link_becomes_strikethrough(self) -> None:
        xhtml = (
            '<ac:link><ri:page ri:content-title="Missing"/>'
            "<ac:link-body>Missing</ac:link-body></ac:link>"
        )
        out = render_html(xhtml, page_link_map={"Other": "other.html"})
        assert "line-through" in out
        assert "Missing" in out

    def test_anchor_only_link(self) -> None:
        xhtml = '<ac:link ac:anchor="section-1"><ac:link-body>Section</ac:link-body></ac:link>'
        out = render_html(xhtml, page_link_map={"dummy": "x.html"})
        assert 'href="#section-1"' in out
        assert "Section" in out

    def test_link_with_anchor_appended_to_page(self) -> None:
        xhtml = (
            '<ac:link ac:anchor="intro">'
            '<ri:page ri:content-title="Guide"/>'
            "<ac:link-body>Guide intro</ac:link-body>"
            "</ac:link>"
        )
        out = render_html(xhtml, page_link_map={"Guide": "guide.html"})
        assert 'href="guide.html#intro"' in out

    def test_no_page_link_map_leaves_ac_link_untouched(self) -> None:
        xhtml = (
            '<ac:link><ri:page ri:content-title="X"/>'
            "<ac:link-body>X</ac:link-body></ac:link>"
        )
        out = render_html(xhtml, page_link_map=None)
        assert "<ac:link" in out

    def test_unrecognised_link_returned_unchanged(self) -> None:
        xhtml = "<ac:link><ri:unknown/></ac:link>"
        out = render_html(xhtml, page_link_map={"X": "x.html"})
        assert "<ac:link>" in out


class TestRenderIndex:
    def test_returns_full_html(self) -> None:
        out = render_index("My Section", [("Page A", "a.html"), ("Page B", "b.html")])
        assert "<!DOCTYPE html>" in out
        assert "<ul>" in out
        assert "My Section" in out

    def test_links_are_present(self) -> None:
        out = render_index("Sec", [("Alpha", "alpha.html"), ("Beta", "beta.html")])
        assert 'href="alpha.html"' in out
        assert "Alpha" in out
        assert 'href="beta.html"' in out

    def test_title_escaped(self) -> None:
        out = render_index("A & B", [])
        assert "A &amp; B" in out



class TestRenderLayout:
    def test_single_card_renders_ac_layout(self) -> None:
        xhtml = (
            "<ac:layout>\n"
            '  <ac:layout-section ac:type="single">\n'
            "    <ac:layout-cell><p>Hello</p></ac:layout-cell>\n"
            "  </ac:layout-section>\n"
            "</ac:layout>\n"
        )
        out = render_html(xhtml)
        assert '<div class="ac-layout">' in out
        assert '<div class="ac-layout-section ac-single">' in out
        assert '<div class="ac-layout-cell">' in out
        assert "<p>Hello</p>" in out
        assert "<ac:layout" not in out

    def test_two_equal_columns(self) -> None:
        xhtml = (
            "<ac:layout>"
            '<ac:layout-section ac:type="two_equal">'
            "<ac:layout-cell><p>A</p></ac:layout-cell>"
            "<ac:layout-cell><p>B</p></ac:layout-cell>"
            "</ac:layout-section>"
            "</ac:layout>"
        )
        out = render_html(xhtml)
        assert 'class="ac-layout-section ac-two-equal"' in out
        assert out.count('<div class="ac-layout-cell">') == 2

    def test_three_equal_columns(self) -> None:
        xhtml = (
            "<ac:layout>"
            '<ac:layout-section ac:type="three_equal">'
            "<ac:layout-cell><p>1</p></ac:layout-cell>"
            "<ac:layout-cell><p>2</p></ac:layout-cell>"
            "<ac:layout-cell><p>3</p></ac:layout-cell>"
            "</ac:layout-section>"
            "</ac:layout>"
        )
        out = render_html(xhtml)
        assert 'class="ac-layout-section ac-three-equal"' in out
        assert out.count('<div class="ac-layout-cell">') == 3

    def test_macro_inside_layout_cell_renders(self) -> None:
        xhtml = (
            "<ac:layout>"
            '<ac:layout-section ac:type="two_equal">'
            "<ac:layout-cell>"
            '<ac:structured-macro ac:name="info">'
            '<ac:rich-text-body><p>tip</p></ac:rich-text-body>'
            "</ac:structured-macro>"
            "</ac:layout-cell>"
            "<ac:layout-cell><p>B</p></ac:layout-cell>"
            "</ac:layout-section>"
            "</ac:layout>"
        )
        out = render_html(xhtml)
        assert "ac:layout" not in out
        assert "ac:structured-macro" not in out
        assert "tip" in out

    def test_layout_css_in_render_page(self) -> None:
        out = render_page("<p>hi</p>")
        assert ".ac-layout-section" in out


class TestInjectLivereload:
    def test_script_injected_before_body_close(self) -> None:
        html = "<html><body><p>hi</p></body></html>"
        out = inject_livereload(html)
        assert "<script>" in out
        assert out.index("<script>") < out.index("</body>")

    def test_livereload_polls_endpoint(self) -> None:
        html = "<html><body></body></html>"
        out = inject_livereload(html)
        assert "/__livereload" in out

    def test_noop_when_no_body_close(self) -> None:
        html = "<p>no body tag</p>"
        out = inject_livereload(html)
        assert out == html
