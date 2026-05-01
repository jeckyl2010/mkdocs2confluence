"""Tests for Mermaid diagram rendering (Kroki) and XHTML emission."""

from __future__ import annotations

from unittest.mock import patch

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import CodeBlock, MermaidDiagram
from mkdocs_to_confluence.parser.markdown import parse
from mkdocs_to_confluence.transforms.mermaid import (
    render_mermaid_diagrams,
)

_SAMPLE_SOURCE = "graph TD\n    A --> B\n"
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG > _MIN_PNG_BYTES (67)


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


def test_render_fallback_on_network_error(tmp_path, capsys):
    """When Kroki is unreachable, node is left unchanged (code block fallback)."""
    import urllib.error

    node = MermaidDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.mermaid.time.sleep"),
        patch(
            "mkdocs_to_confluence.transforms.mermaid._kroki_png",
            side_effect=urllib.error.URLError("timed out"),
        ),
    ):
        updated_nodes, attachments = render_mermaid_diagrams((node,))

    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name is None  # type: ignore[union-attr]
    err = capsys.readouterr().err
    assert "falling back to code block" in err


def test_render_fallback_on_http_error(tmp_path, capsys):
    """When Kroki returns an HTTP error, node falls back to code block."""
    import urllib.error

    node = MermaidDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.mermaid.time.sleep"),
        patch(
            "mkdocs_to_confluence.transforms.mermaid._kroki_png",
            side_effect=urllib.error.HTTPError(
                url=None, code=503, msg="Service Unavailable", hdrs=None, fp=None  # type: ignore[arg-type]
            ),
        ),
    ):
        updated_nodes, attachments = render_mermaid_diagrams((node,))

    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name is None  # type: ignore[union-attr]
    err = capsys.readouterr().err
    assert "falling back to code block" in err


def test_render_fallback_on_empty_response(tmp_path, capsys):
    """When Kroki returns too-small a response, node falls back to code block."""
    node = MermaidDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path),
        patch(
            "mkdocs_to_confluence.transforms.mermaid._kroki_png",
            return_value=b"",  # empty response
        ),
    ):
        updated_nodes, attachments = render_mermaid_diagrams((node,))

    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name is None  # type: ignore[union-attr]
    err = capsys.readouterr().err
    assert "falling back to code block" in err


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


# ── Parallel rendering ────────────────────────────────────────────────────────


def test_render_multiple_diagrams_concurrently(tmp_path):
    """Multiple distinct diagrams are all rendered (parallel path)."""
    sources = [f"graph TD\n    A{i} --> B{i}\n" for i in range(4)]
    nodes = tuple(MermaidDiagram(source=s) for s in sources)

    with patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.mermaid._kroki_png", return_value=_FAKE_PNG):
        updated, attachments = render_mermaid_diagrams(nodes)

    assert len(attachments) == 4
    for node in updated:
        assert isinstance(node, MermaidDiagram)
        assert node.attachment_name is not None


def test_render_one_failure_does_not_block_others(tmp_path):
    """If one diagram fails, the rest still render successfully."""
    import urllib.error

    good_source = "graph TD\n    A --> B\n"
    bad_source = "graph TD\n    X --> Y\n"
    nodes = (MermaidDiagram(source=good_source), MermaidDiagram(source=bad_source))

    def fake_kroki(source: str, url: str) -> bytes:
        if source == bad_source:
            raise urllib.error.URLError("timeout")
        return _FAKE_PNG

    with patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.mermaid._kroki_png", side_effect=fake_kroki):
        updated, attachments = render_mermaid_diagrams(nodes)

    # One attachment for the successful diagram
    assert len(attachments) == 1
    # Good diagram got attachment_name; bad one stayed as code-block fallback
    assert updated[0].attachment_name is not None  # type: ignore[union-attr]
    assert updated[1].attachment_name is None  # type: ignore[union-attr]


def test_render_one_cached(tmp_path):
    """_render_one returns the cache path immediately for cached diagrams."""
    from mkdocs_to_confluence.transforms.mermaid import _render_one, _cache_path

    path = tmp_path / "mermaid_cached.png"
    path.write_bytes(_FAKE_PNG)

    with patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.mermaid._cache_path", return_value=path), \
         patch("mkdocs_to_confluence.transforms.mermaid._kroki_png") as mock_fetch:
        result = _render_one(_SAMPLE_SOURCE, "https://kroki.io")

    mock_fetch.assert_not_called()
    assert result == path


def test_render_one_network_failure_returns_none(tmp_path):
    """_render_one returns None after all retries on persistent network failure."""
    import urllib.error
    from mkdocs_to_confluence.transforms.mermaid import _render_one

    with patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.mermaid.time.sleep"), \
         patch("mkdocs_to_confluence.transforms.mermaid._kroki_png",
               side_effect=urllib.error.URLError("connection refused")):
        result = _render_one(_SAMPLE_SOURCE, "https://kroki.io")

    assert result is None


# ── Retry behaviour ───────────────────────────────────────────────────────────


def test_render_one_retries_on_503_then_succeeds(tmp_path):
    """_render_one retries on HTTP 503 and succeeds on the second attempt."""
    import urllib.error
    from mkdocs_to_confluence.transforms.mermaid import _render_one

    calls = [urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None), _FAKE_PNG]

    def fake_kroki(source: str, url: str) -> bytes:
        result = calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.mermaid.time.sleep") as mock_sleep, \
         patch("mkdocs_to_confluence.transforms.mermaid._kroki_png", side_effect=fake_kroki):
        result = _render_one(_SAMPLE_SOURCE, "https://kroki.io")

    assert result is not None
    assert result.exists()
    mock_sleep.assert_called_once_with(1.0)  # backed off once


def test_render_one_non_retryable_http_error_returns_none(tmp_path):
    """_render_one does not retry on HTTP 400 (bad input) — returns None immediately."""
    import urllib.error
    from mkdocs_to_confluence.transforms.mermaid import _render_one

    with patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.mermaid.time.sleep") as mock_sleep, \
         patch("mkdocs_to_confluence.transforms.mermaid._kroki_png",
               side_effect=urllib.error.HTTPError("url", 400, "Bad Request", {}, None)):
        result = _render_one(_SAMPLE_SOURCE, "https://kroki.io")

    assert result is None
    mock_sleep.assert_not_called()  # no retry for 400


def test_render_one_exhausts_retries_on_persistent_503(tmp_path):
    """_render_one returns None after all attempts on persistent 503."""
    import urllib.error
    from mkdocs_to_confluence.transforms.mermaid import _render_one, _RETRY_ATTEMPTS

    with patch("mkdocs_to_confluence.transforms.mermaid._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.mermaid.time.sleep"), \
         patch("mkdocs_to_confluence.transforms.mermaid._kroki_png",
               side_effect=urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)) as mock_fetch:
        result = _render_one(_SAMPLE_SOURCE, "https://kroki.io")

    assert result is None
    assert mock_fetch.call_count == _RETRY_ATTEMPTS

