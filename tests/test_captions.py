"""Tests for image captions and figure/figcaption support."""

from __future__ import annotations

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import ImageNode, Paragraph


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
