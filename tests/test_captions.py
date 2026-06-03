"""Tests for image captions and figure/figcaption support."""

from __future__ import annotations

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import ImageNode, Paragraph
from mkdocs_to_confluence.transforms.captions import resolve_captions


def test_emit_image_with_caption_local():
    node = Paragraph(children=(ImageNode(src="arch.png", alt="A", caption="Figure 1"),))
    out = emit((node,))
    # caption must be nested inside <ac:image>, after the attachment ref
    assert (
        '<ri:attachment ri:filename="arch.png"/>'
        "<ac:caption><p>Figure 1</p></ac:caption></ac:image>" in out
    )


def test_emit_image_without_caption_has_no_caption_element():
    node = Paragraph(children=(ImageNode(src="arch.png", alt="A"),))
    out = emit((node,))
    assert "<ac:caption>" not in out


def test_emit_image_caption_external_url():
    node = Paragraph(
        children=(ImageNode(src="https://x.test/a.png", alt="A", caption="Remote"),)
    )
    out = emit((node,))
    assert (
        '<ri:url ri:value="https://x.test/a.png"/>'
        "<ac:caption><p>Remote</p></ac:caption></ac:image>" in out
    )


def test_emit_image_caption_is_escaped():
    node = Paragraph(children=(ImageNode(src="a.png", alt="A", caption="x & <y>"),))
    out = emit((node,))
    assert "x &amp; &lt;y&gt;" in out


def test_resolve_captions_title_becomes_caption():
    nodes = (Paragraph(children=(ImageNode(src="a.png", alt="A", title="Cap"),)),)
    out = resolve_captions(nodes)
    img = out[0].children[0]
    assert img.caption == "Cap"
    assert img.title is None  # cleared so it is not also a tooltip


def test_resolve_captions_existing_caption_wins():
    nodes = (
        Paragraph(children=(ImageNode(src="a.png", alt="A", title="T", caption="C"),)),
    )
    out = resolve_captions(nodes)
    img = out[0].children[0]
    assert img.caption == "C"
    assert img.title == "T"  # untouched when caption already set


def test_resolve_captions_no_title_unchanged():
    nodes = (Paragraph(children=(ImageNode(src="a.png", alt="A"),)),)
    out = resolve_captions(nodes)
    assert out[0].children[0].caption is None


def test_resolve_captions_external_image():
    nodes = (
        Paragraph(children=(ImageNode(src="https://x.test/a.png", alt="A", title="Cap"),)),
    )
    out = resolve_captions(nodes)
    assert out[0].children[0].caption == "Cap"
    assert out[0].children[0].title is None  # same clearing guarantee as local images


def test_rewrite_figure_caption_basic():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = (
        '<figure markdown="span">\n'
        "  ![Arch](arch.png)\n"
        "  <figcaption>System overview</figcaption>\n"
        "</figure>\n"
    )
    out = rewrite_figure_captions(md)
    assert out.strip() == '![Arch](arch.png "System overview")'


def test_rewrite_figure_caption_precedence_over_title():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = (
        "<figure>\n"
        '![Arch](arch.png "ignored title")\n'
        "<figcaption>Real caption</figcaption>\n"
        "</figure>\n"
    )
    out = rewrite_figure_captions(md)
    assert out.strip() == '![Arch](arch.png "Real caption")'


def test_rewrite_figure_caption_escapes_quotes():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = '<figure>\n![A](a.png)\n<figcaption>a "quoted" cap</figcaption>\n</figure>\n'
    out = rewrite_figure_captions(md)
    assert out.strip() == "![A](a.png \"a 'quoted' cap\")"


def test_rewrite_figure_caption_no_figure_unchanged():
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions

    md = "Just text with ![A](a.png) inline.\n"
    assert rewrite_figure_captions(md) == md


def test_figure_pipeline_end_to_end():
    from mkdocs_to_confluence.parser.markdown import parse
    from mkdocs_to_confluence.preprocess.captions import rewrite_figure_captions
    from mkdocs_to_confluence.transforms.captions import resolve_captions

    md = "<figure>\n![Arch](arch.png)\n<figcaption>Overview</figcaption>\n</figure>\n"
    out = emit(resolve_captions(parse(rewrite_figure_captions(md))))
    assert "<ac:caption><p>Overview</p></ac:caption>" in out


def test_compile_page_renders_image_caption(tmp_path):
    from mkdocs_to_confluence.loader.config import MkDocsConfig
    from mkdocs_to_confluence.loader.nav import NavNode
    from mkdocs_to_confluence.publisher.pipeline import compile_page

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (docs / "index.md").write_text('![Logo](logo.png "Our logo")\n', encoding="utf-8")

    node = NavNode(
        title="Index", docs_path="index.md", source_path=docs / "index.md", level=0
    )
    config = MkDocsConfig(
        site_name="T", docs_dir=docs, repo_url=None, edit_uri=None, nav=None
    )
    xhtml, _, _, _, _ = compile_page(node, config)
    assert "<ac:caption><p>Our logo</p></ac:caption>" in xhtml
