"""Tests for Mermaid diagram rendering (Kroki) and XHTML emission."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import CodeBlock, MermaidDiagram, Paragraph, TextNode
from mkdocs_to_confluence.parser.markdown import parse
from mkdocs_to_confluence.transforms.mermaid import (
    DEFAULT_KROKI_URL,
    render_mermaid_diagrams,
)

_SAMPLE_SOURCE = "graph TD\n    A --> B\n"
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # minimal fake PNG bytes


# ── Parser ────────────────────────────────────────────────────────────────────


def test_parser_produces_mermaid_diagram_node():
    """A ```mermaid fenced block must parse to MermaidDiagram, not CodeBlock."""
    nodes = parse("```mermaid\ngraph TD\n    A --> B\n```\n")
    assert len(nodes) == 1
    assert isinstance(nodes[0], MermaidDiagram)
    assert "graph TD" in nodes[0].source


def test_parser_non_mermaid_code_block_stays_codeblock():
    """A ```python block must still parse to CodeBlock."""
    nodes = parse("```python\nprint('hello')\n```\n")
    assert len(nodes) == 1
    assert isinstance(nodes[0], CodeBlock)


# ── Emitter ───────────────────────────────────────────────────────────────────


def test_emit_mermaid_fallback_code_block():
    """Without attachment_name the emitter produces a code macro."""
    node = MermaidDiagram(source=_SAMPLE_SOURCE)
    result = emit((node,))
    assert 'ac:name="code"' in result
    assert "mermaid" in result
    assert "graph TD" in result


def test_emit_mermaid_attachment_image():
    """With attachment_name set the emitter produces an ac:image."""
    node = MermaidDiagram(source=_SAMPLE_SOURCE, attachment_name="mermaid_abc123.png")
    result = emit((node,))
    assert '<ac:image ac:align="center">' in result
    assert 'ri:filename="mermaid_abc123.png"' in result
    assert "code" not in result


# ── render_mermaid_diagrams ───────────────────────────────────────────────────


def test_render_uses_cache_on_second_call(tmp_path):
    """Second call for the same source must not hit the network."""
    node = MermaidDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.mermaid._kroki_png", return_value=_FAKE_PNG) as mock_fetch,
    ):
        render_mermaid_diagrams((node,))
        render_mermaid_diagrams((node,))

    mock_fetch.assert_called_once()  # only fetched once; second call hit cache


def test_render_sets_attachment_name(tmp_path):
    node = MermaidDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.mermaid._kroki_png", return_value=_FAKE_PNG),
    ):
        updated_nodes, attachments = render_mermaid_diagrams((node,))

    assert len(attachments) == 1
    assert attachments[0].suffix == ".png"
    rendered = updated_nodes[0]
    assert isinstance(rendered, MermaidDiagram)
    assert rendered.attachment_name == attachments[0].name


def test_render_deduplicates_identical_diagrams(tmp_path):
    """Two nodes with the same source → one attachment, not two."""
    node_a = MermaidDiagram(source=_SAMPLE_SOURCE)
    node_b = MermaidDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.mermaid._kroki_png", return_value=_FAKE_PNG),
    ):
        _, attachments = render_mermaid_diagrams((node_a, node_b))

    assert len(attachments) == 1


def test_render_fallback_on_network_error(tmp_path):
    """When Kroki is unreachable, node is left unchanged (code block fallback)."""
    import urllib.error

    node = MermaidDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch(
            "mkdocs_to_confluence.transforms.mermaid._kroki_png",
            side_effect=urllib.error.URLError("timeout"),
        ),
        pytest.warns(UserWarning, match="Mermaid rendering failed"),
    ):
        updated_nodes, attachments = render_mermaid_diagrams((node,))

    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name is None  # type: ignore[union-attr]


def test_render_uses_custom_kroki_url(tmp_path):
    """mermaid_render: kroki:https://internal.kroki passes the custom URL."""
    node = MermaidDiagram(source=_SAMPLE_SOURCE)
    captured: list[str] = []

    def fake_fetch(source: str, kroki_url: str) -> bytes:
        captured.append(kroki_url)
        return _FAKE_PNG

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.mermaid._kroki_png", side_effect=fake_fetch),
    ):
        render_mermaid_diagrams((node,), kroki_url="https://internal.kroki")

    assert captured == ["https://internal.kroki"]


def test_render_mermaid_none_skips(tmp_path):
    """mermaid_render: none leaves nodes untouched (no network call)."""
    # This is handled by pipeline.py checking the config value before calling
    # render_mermaid_diagrams. Here we just verify that if attachment_name is
    # already set, the transform is idempotent.
    node = MermaidDiagram(source=_SAMPLE_SOURCE, attachment_name="already_set.png")

    with patch("mkdocs_to_confluence.transforms.mermaid._kroki_png") as mock_fetch:
        updated_nodes, attachments = render_mermaid_diagrams((node,))

    mock_fetch.assert_not_called()
    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name == "already_set.png"  # type: ignore[union-attr]
