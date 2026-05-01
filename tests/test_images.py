"""Tests for the image resolution transform."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from mkdocs_to_confluence.ir.nodes import ImageNode, LinkNode, Paragraph, TextNode
from mkdocs_to_confluence.transforms.assets import (
    _make_attachment_name,
    _resolve_asset_path,
    resolve_local_assets,
)
from mkdocs_to_confluence.transforms.images import is_local, resolve_images

# ── is_local ─────────────────────────────────────────────────────────────────


def test_is_local_http():
    assert not is_local("http://example.com/img.png")


def test_is_local_https():
    assert not is_local("https://example.com/img.png")


def test_is_local_protocol_relative():
    assert not is_local("//example.com/img.png")


def test_is_local_data_uri():
    assert not is_local("data:image/png;base64,abc")


def test_is_local_relative_path():
    assert is_local("images/logo.png")


def test_is_local_absolute_path():
    assert is_local("/absolute/path/logo.png")


def test_is_local_plain_filename():
    assert is_local("logo.png")


# ── resolve_images ────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_image(tmp_path: Path) -> Path:
    """Create a tiny 1-byte placeholder image file for tests."""
    img = tmp_path / "images" / "logo.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\x89PNG")
    return img


def _make_nodes(*images: ImageNode) -> tuple:
    """Wrap ImageNodes inside Paragraphs so we have a realistic IR tree."""
    return tuple(Paragraph(children=(img,)) for img in images)


def test_relative_path_resolved(tmp_image: Path):
    """Relative path resolved to absolute when file exists beside the page."""
    page_path = tmp_image.parent.parent / "index.md"
    docs_dir = tmp_image.parent.parent

    img = ImageNode(src="images/logo.png", alt="logo")
    nodes = _make_nodes(img)

    updated, attachments = resolve_images(
        nodes, page_path=page_path, docs_dir=docs_dir
    )

    resolved_img = updated[0].children[0]  # type: ignore[attr-defined]
    assert resolved_img.src == str(tmp_image)
    assert attachments == [tmp_image]


def test_docs_dir_fallback(tmp_path: Path):
    """Falls back to docs_dir when path is not relative to the page directory."""
    docs_dir = tmp_path / "docs"
    img_file = docs_dir / "assets" / "logo.png"
    img_file.parent.mkdir(parents=True)
    img_file.write_bytes(b"\x89PNG")

    page_path = docs_dir / "sub" / "index.md"
    (docs_dir / "sub").mkdir()

    img = ImageNode(src="assets/logo.png", alt="logo")
    nodes = _make_nodes(img)

    updated, attachments = resolve_images(
        nodes, page_path=page_path, docs_dir=docs_dir
    )

    resolved_img = updated[0].children[0]  # type: ignore[attr-defined]
    assert resolved_img.src == str(img_file)
    assert attachments == [img_file]


def test_url_left_unchanged(tmp_path: Path):
    """HTTP URLs pass through untouched."""
    page_path = tmp_path / "index.md"
    img = ImageNode(src="https://example.com/logo.png", alt="logo")
    nodes = _make_nodes(img)

    updated, attachments = resolve_images(
        nodes, page_path=page_path, docs_dir=tmp_path
    )

    resolved_img = updated[0].children[0]  # type: ignore[attr-defined]
    assert resolved_img.src == "https://example.com/logo.png"
    assert attachments == []


def test_nonexistent_file_left_as_is(tmp_path: Path):
    """Images that can't be found are left as-is and not registered."""
    page_path = tmp_path / "index.md"
    img = ImageNode(src="missing.png", alt="nope")
    nodes = _make_nodes(img)

    updated, attachments = resolve_images(
        nodes, page_path=page_path, docs_dir=tmp_path
    )

    resolved_img = updated[0].children[0]  # type: ignore[attr-defined]
    assert resolved_img.src == "missing.png"
    assert attachments == []


def test_multiple_images(tmp_path: Path):
    """Multiple images in the same tree are each resolved independently."""
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "b.png").write_bytes(b"\x89PNG")

    page_path = tmp_path / "index.md"
    img_a = ImageNode(src="a.png", alt="a")
    img_b = ImageNode(src="b.png", alt="b")
    nodes = _make_nodes(img_a, img_b)

    updated, attachments = resolve_images(
        nodes, page_path=page_path, docs_dir=tmp_path
    )

    assert updated[0].children[0].src == str(tmp_path / "a.png")  # type: ignore[attr-defined]
    assert updated[1].children[0].src == str(tmp_path / "b.png")  # type: ignore[attr-defined]
    assert len(attachments) == 2


def test_no_images_returns_original_nodes(tmp_path: Path):
    """When no images are present the original nodes tuple is returned unchanged."""
    page_path = tmp_path / "index.md"
    text = TextNode(text="Hello")
    para = Paragraph(children=(text,))
    nodes = (para,)

    updated, attachments = resolve_images(
        nodes, page_path=page_path, docs_dir=tmp_path
    )

    assert updated is nodes
    assert attachments == []


# ── assets: _make_attachment_name ────────────────────────────────────────────


def test_make_attachment_name_inside_docs_dir(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    abs_path = docs_dir / "assets" / "images" / "logo.png"
    assert _make_attachment_name(abs_path, docs_dir) == "assets_images_logo.png"


def test_make_attachment_name_outside_docs_dir(tmp_path: Path) -> None:
    """Falls back to bare filename when path is outside docs_dir."""
    docs_dir = tmp_path / "docs"
    abs_path = tmp_path / "other" / "logo.png"
    assert _make_attachment_name(abs_path, docs_dir) == "logo.png"


# ── assets: _resolve_asset_path ──────────────────────────────────────────────


def test_resolve_asset_path_found_in_docs_dir(tmp_path: Path) -> None:
    """Falls back to docs_dir when not found relative to page_dir."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    img = docs_dir / "logo.png"
    img.write_bytes(b"PNG")
    page_dir = tmp_path / "subdir"
    page_dir.mkdir()
    result = _resolve_asset_path("logo.png", page_dir, docs_dir)
    assert result == img.resolve()


def test_resolve_asset_path_not_found_returns_none(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_dir = tmp_path / "subdir"
    page_dir.mkdir()
    result = _resolve_asset_path("missing.png", page_dir, docs_dir)
    assert result is None


# ── assets: resolve_local_assets ─────────────────────────────────────────────


def _wrap(*nodes) -> tuple:
    return tuple(Paragraph(children=(n,)) for n in nodes)


def test_resolve_local_assets_skips_url_image(tmp_path: Path) -> None:
    """URL images are left unchanged."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    img = ImageNode(src="https://example.com/logo.png", alt="logo")
    nodes = _wrap(img)
    updated, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []
    assert updated[0].children[0].src == "https://example.com/logo.png"  # type: ignore[attr-defined]


def test_resolve_local_assets_skips_missing_image(tmp_path: Path) -> None:
    """Image not found on disk → node is left unchanged, no attachment."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    img = ImageNode(src="ghost.png", alt="ghost")
    nodes = _wrap(img)
    updated, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []


def test_resolve_local_assets_link_local_file(tmp_path: Path) -> None:
    """A local file link gets attachment_name set and is collected."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    pdf = docs_dir / "report.pdf"
    pdf.write_bytes(b"PDF")
    page_path = docs_dir / "index.md"
    link = LinkNode(href="report.pdf", children=(TextNode(text="report"),))
    nodes = _wrap(link)
    updated, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert len(attachments) == 1
    result_link = updated[0].children[0]  # type: ignore[attr-defined]
    assert result_link.attachment_name == "report.pdf"


def test_resolve_local_assets_link_not_found_warns(tmp_path: Path) -> None:
    """A local file link that doesn't exist emits a warning and is skipped."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    link = LinkNode(href="missing.pdf", children=(TextNode(text="file"),))
    nodes = _wrap(link)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        updated, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []
    assert any("missing.pdf" in str(w.message) for w in caught)


def test_resolve_local_assets_skips_url_link(tmp_path: Path) -> None:
    """URL link hrefs are skipped."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    link = LinkNode(href="https://example.com/file.pdf", children=(TextNode(text="ext"),))
    nodes = _wrap(link)
    _, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []


def test_resolve_local_assets_skips_md_link(tmp_path: Path) -> None:
    """Links to .md pages are skipped."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    link = LinkNode(href="other.md", children=(TextNode(text="page"),))
    nodes = _wrap(link)
    _, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []


def test_resolve_local_assets_skips_fragment_link(tmp_path: Path) -> None:
    """Fragment-only links (#section) are skipped."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    link = LinkNode(href="#introduction", children=(TextNode(text="intro"),))
    nodes = _wrap(link)
    _, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []


def test_resolve_local_assets_skips_md_fragment_link(tmp_path: Path) -> None:
    """Links like other.md#section are skipped."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    link = LinkNode(href="other.md#section", children=(TextNode(text="s"),))
    nodes = _wrap(link)
    _, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []


def test_resolve_local_assets_skips_bare_word_link(tmp_path: Path) -> None:
    """Bare word hrefs with no extension or slash are skipped."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    page_path = docs_dir / "index.md"
    link = LinkNode(href="somepage", children=(TextNode(text="page"),))
    nodes = _wrap(link)
    _, attachments = resolve_local_assets(nodes, page_path=page_path, docs_dir=docs_dir)
    assert attachments == []
