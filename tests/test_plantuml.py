"""Tests for PlantUML diagram rendering (Kroki) and XHTML emission."""

from __future__ import annotations

from unittest.mock import patch

from mkdocs_to_confluence.emitter.xhtml import emit
from mkdocs_to_confluence.ir.nodes import CodeBlock, PlantUMLDiagram
from mkdocs_to_confluence.parser.markdown import parse
from mkdocs_to_confluence.transforms.plantuml import (
    render_plantuml_diagrams,
)

_SAMPLE_SOURCE = "@startuml\nAlice -> Bob: Hello\n@enduml\n"
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG > _MIN_PNG_BYTES (67)


# ── Parser ────────────────────────────────────────────────────────────────────


def test_parser_produces_plantuml_diagram_node():
    """A ```plantuml fenced block must parse to PlantUMLDiagram, not CodeBlock."""
    nodes = parse("```plantuml\n@startuml\nAlice -> Bob: Hello\n@enduml\n```\n")
    assert len(nodes) == 1
    assert isinstance(nodes[0], PlantUMLDiagram)
    assert "@startuml" in nodes[0].source


def test_parser_plantuml_case_insensitive():
    """Language tag ``PlantUML`` (mixed case) must also produce PlantUMLDiagram."""
    nodes = parse("```PlantUML\n@startuml\nA -> B\n@enduml\n```\n")
    assert len(nodes) == 1
    assert isinstance(nodes[0], PlantUMLDiagram)


def test_parser_non_plantuml_code_block_stays_codeblock():
    """A ```python block must still parse to CodeBlock."""
    nodes = parse("```python\nprint('hello')\n```\n")
    assert len(nodes) == 1
    assert isinstance(nodes[0], CodeBlock)


# ── Emitter ───────────────────────────────────────────────────────────────────


def test_emit_plantuml_fallback_code_block():
    """Without attachment_name the emitter produces a code macro."""
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)
    result = emit((node,))
    assert 'ac:name="code"' in result
    assert "@startuml" in result


def test_emit_plantuml_attachment_image():
    """With attachment_name set the emitter produces an ac:image."""
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE, attachment_name="plantuml_abc123.png")
    result = emit((node,))
    assert '<ac:image ac:align="center">' in result
    assert 'ri:filename="plantuml_abc123.png"' in result
    assert "code" not in result


# ── render_plantuml_diagrams ──────────────────────────────────────────────────


def test_render_uses_cache_on_second_call(tmp_path):
    """Second call for the same source must not hit the network."""
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.plantuml._kroki_png", return_value=_FAKE_PNG) as mock_fetch,
    ):
        render_plantuml_diagrams((node,))
        render_plantuml_diagrams((node,))

    mock_fetch.assert_called_once()  # only fetched once; second call hit cache


def test_render_sets_attachment_name(tmp_path):
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.plantuml._kroki_png", return_value=_FAKE_PNG),
    ):
        updated_nodes, attachments = render_plantuml_diagrams((node,))

    assert len(attachments) == 1
    assert attachments[0].suffix == ".png"
    rendered = updated_nodes[0]
    assert isinstance(rendered, PlantUMLDiagram)
    assert rendered.attachment_name == attachments[0].name


def test_render_deduplicates_identical_diagrams(tmp_path):
    """Two nodes with the same source → one attachment, not two."""
    node_a = PlantUMLDiagram(source=_SAMPLE_SOURCE)
    node_b = PlantUMLDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.plantuml._kroki_png", return_value=_FAKE_PNG),
    ):
        _, attachments = render_plantuml_diagrams((node_a, node_b))

    assert len(attachments) == 1


def test_render_fallback_on_network_error(tmp_path, capsys):
    """When Kroki is unreachable, node falls back to code block."""
    import urllib.error

    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.plantuml.time.sleep"),
        patch(
            "mkdocs_to_confluence.transforms.plantuml._kroki_png",
            side_effect=urllib.error.URLError("timed out"),
        ),
    ):
        updated_nodes, attachments = render_plantuml_diagrams((node,))

    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name is None  # type: ignore[union-attr]
    err = capsys.readouterr().err
    assert "falling back to code block" in err


def test_render_fallback_on_http_error(tmp_path, capsys):
    """When Kroki returns an HTTP error, node falls back to code block."""
    import urllib.error

    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.plantuml.time.sleep"),
        patch(
            "mkdocs_to_confluence.transforms.plantuml._kroki_png",
            side_effect=urllib.error.HTTPError(
                url=None, code=503, msg="Service Unavailable", hdrs=None, fp=None  # type: ignore[arg-type]
            ),
        ),
    ):
        updated_nodes, attachments = render_plantuml_diagrams((node,))

    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name is None  # type: ignore[union-attr]
    err = capsys.readouterr().err
    assert "falling back to code block" in err


def test_render_fallback_on_empty_response(tmp_path, capsys):
    """When Kroki returns too-small a response, node falls back to code block."""
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch(
            "mkdocs_to_confluence.transforms.plantuml._kroki_png",
            return_value=b"",
        ),
    ):
        updated_nodes, attachments = render_plantuml_diagrams((node,))

    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name is None  # type: ignore[union-attr]
    err = capsys.readouterr().err
    assert "falling back to code block" in err


def test_render_uses_custom_kroki_url(tmp_path):
    """mermaid_render: kroki:https://internal.kroki passes the custom URL."""
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)
    captured: list[str] = []

    def fake_fetch(source: str, kroki_url: str) -> bytes:
        captured.append(kroki_url)
        return _FAKE_PNG

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.plantuml._kroki_png", side_effect=fake_fetch),
    ):
        render_plantuml_diagrams((node,), kroki_url="https://internal.kroki")

    assert captured == ["https://internal.kroki"]


def test_render_plantuml_none_skips(tmp_path):
    """Nodes with attachment_name already set are left untouched."""
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE, attachment_name="already_set.png")

    with patch("mkdocs_to_confluence.transforms.plantuml._kroki_png") as mock_fetch:
        updated_nodes, attachments = render_plantuml_diagrams((node,))

    mock_fetch.assert_not_called()
    assert len(attachments) == 0
    assert updated_nodes[0].attachment_name == "already_set.png"  # type: ignore[union-attr]


def test_render_multiple_diagrams_concurrently(tmp_path):
    """Multiple distinct diagrams are all rendered (parallel path)."""
    sources = [f"@startuml\nA{i} -> B{i}\n@enduml\n" for i in range(4)]
    nodes = tuple(PlantUMLDiagram(source=s) for s in sources)

    with patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.plantuml._kroki_png", return_value=_FAKE_PNG):
        updated, attachments = render_plantuml_diagrams(nodes)

    assert len(attachments) == 4
    for node in updated:
        assert isinstance(node, PlantUMLDiagram)
        assert node.attachment_name is not None


def test_render_retries_on_503_then_succeeds(tmp_path):
    """_render_one retries on HTTP 503 and succeeds on the second attempt."""
    import urllib.error

    from mkdocs_to_confluence.transforms.plantuml import _render_one

    calls = [urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None), _FAKE_PNG]

    def fake_kroki(source: str, url: str) -> bytes:
        result = calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.plantuml.time.sleep") as mock_sleep, \
         patch("mkdocs_to_confluence.transforms.plantuml._kroki_png", side_effect=fake_kroki):
        result = _render_one(_SAMPLE_SOURCE, "https://kroki.io")

    assert result is not None
    assert result.exists()
    mock_sleep.assert_called_once_with(1.0)


def test_render_no_mermaid_ink_fallback(tmp_path):
    """PlantUML has no mermaid.ink fallback — 504 on public kroki returns None."""
    import urllib.error

    from mkdocs_to_confluence.transforms.plantuml import _render_one

    with patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path), \
         patch("mkdocs_to_confluence.transforms.plantuml.time.sleep"), \
         patch("mkdocs_to_confluence.transforms.plantuml._kroki_png",
               side_effect=urllib.error.HTTPError("url", 504, "Gateway Timeout", {}, None)):
        result = _render_one(_SAMPLE_SOURCE, "https://kroki.io")

    assert result is None


def test_render_quiet_suppresses_stdout(tmp_path, capsys):
    """render_plantuml_diagrams(quiet=True) must produce no stdout output."""
    node = PlantUMLDiagram(source=_SAMPLE_SOURCE)

    with (
        patch("mkdocs_to_confluence.transforms.plantuml._CACHE_DIR", tmp_path),
        patch("mkdocs_to_confluence.transforms.plantuml._kroki_png", return_value=_FAKE_PNG),
    ):
        render_plantuml_diagrams((node,), quiet=True)

    out, _ = capsys.readouterr()
    assert out == ""
