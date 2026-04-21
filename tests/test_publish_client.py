"""Tests for ConfluenceClient using httpx mock transport."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mkdocs_to_confluence.loader.config import ConfluenceConfig
from mkdocs_to_confluence.publisher.client import ConfluenceClient, ConfluenceError


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_config(token: str = "test-token") -> ConfluenceConfig:
    return ConfluenceConfig(
        base_url="https://example.atlassian.net",
        space_key="TECH",
        email="user@example.com",
        token=token,
    )


def _json_response(data: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )


class _MockTransport(httpx.BaseTransport):
    """Simple transport that returns pre-configured responses in order."""

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self._responses) == 1:
            return self._responses[0]
        return self._responses[len(self.requests) - 1]


# ── get_space_id ──────────────────────────────────────────────────────────────


def test_get_space_id_returns_id() -> None:
    payload = {"results": [{"id": "42", "key": "TECH"}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        space_id = client.get_space_id("TECH")
    assert space_id == "42"


def test_get_space_id_not_found_raises() -> None:
    payload = {"results": []}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="TECH"):
            client.get_space_id("TECH")


def test_get_space_id_error_response_raises() -> None:
    transport = _MockTransport(_json_response({"message": "Unauthorized"}, status_code=401))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="401"):
            client.get_space_id("TECH")


def test_get_space_id_from_page_returns_id() -> None:
    payload = {"id": "999", "spaceId": "42", "title": "Parent Page"}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        space_id = client.get_space_id_from_page("999")
    assert space_id == "42"


def test_get_space_id_from_page_missing_raises() -> None:
    payload = {"id": "999", "title": "Parent Page"}  # no spaceId field
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="spaceId"):
            client.get_space_id_from_page("999")


# ── set_page_full_width ───────────────────────────────────────────────────────


def test_set_page_full_width_creates_property_when_absent() -> None:
    """When GET returns 404, a POST is made to create the property."""
    responses = [
        httpx.Response(404, text="not found"),  # GET — property doesn't exist
        httpx.Response(200, json={}),            # POST — create property
    ]
    transport = _MockTransport(*responses)
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_page_full_width("42")
    assert transport.requests[0].method == "GET"
    assert transport.requests[1].method == "POST"


def test_set_page_full_width_updates_property_when_present() -> None:
    """When GET returns 200, a PUT is made with version + 1."""
    existing = {"key": "content-appearance-published", "value": "default", "version": {"number": 3}}
    responses = [
        httpx.Response(200, json=existing),  # GET — property exists
        httpx.Response(200, json={}),        # PUT — update property
    ]
    transport = _MockTransport(*responses)
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_page_full_width("42")
    assert transport.requests[1].method == "PUT"
    import json
    body = json.loads(transport.requests[1].content)
    assert body["version"]["number"] == 4


def test_find_page_returns_page_dict() -> None:
    page = {"id": "99", "title": "My Page", "version": {"number": 3}}
    payload = {"results": [page]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_page("42", "My Page")
    assert result is not None
    assert result["id"] == "99"


def test_find_page_does_not_request_body() -> None:
    """find_page should not include body-format — we only need metadata."""
    payload = {"results": [{"id": "99", "title": "My Page", "version": {"number": 1}}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.find_page("42", "My Page")
    req = transport.requests[0]
    assert "body-format" not in str(req.url)


def test_find_page_returns_none_on_empty_results() -> None:
    payload = {"results": []}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_page("42", "Nonexistent")
    assert result is None


# ── create_page ───────────────────────────────────────────────────────────────


def test_create_page_sends_correct_body() -> None:
    returned_page = {"id": "101", "title": "New Page", "version": {"number": 1}}
    transport = _MockTransport(_json_response(returned_page, status_code=200))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.create_page("42", "New Page", "<p>Hello</p>")
    assert result["id"] == "101"
    req = transport.requests[0]
    body = json.loads(req.content)
    assert body["title"] == "New Page"
    assert body["spaceId"] == "42"
    assert body["body"]["representation"] == "storage"
    assert body["body"]["value"] == "<p>Hello</p>"


def test_create_page_with_parent_id() -> None:
    returned_page = {"id": "102", "title": "Child", "version": {"number": 1}}
    transport = _MockTransport(_json_response(returned_page))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.create_page("42", "Child", "<p>body</p>", parent_id="77")
    req = transport.requests[0]
    body = json.loads(req.content)
    assert body["parentId"] == "77"


def test_create_page_error_raises() -> None:
    transport = _MockTransport(_json_response({"error": "bad"}, status_code=400))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="400"):
            client.create_page("42", "Fail", "<p/>")


# ── update_page ───────────────────────────────────────────────────────────────


def test_update_page_sends_correct_version() -> None:
    returned_page = {"id": "99", "title": "Updated", "version": {"number": 4}}
    transport = _MockTransport(_json_response(returned_page))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.update_page("99", "Updated", "<p>new</p>", version=4)
    assert result["version"]["number"] == 4
    req = transport.requests[0]
    body = json.loads(req.content)
    assert body["version"]["number"] == 4
    assert body["title"] == "Updated"


def test_update_page_sets_minor_edit() -> None:
    """minorEdit=True prevents Confluence from spamming page watchers."""
    returned_page = {"id": "99", "title": "Updated", "version": {"number": 2}}
    transport = _MockTransport(_json_response(returned_page))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.update_page("99", "Updated", "<p>new</p>", version=2)
    body = json.loads(transport.requests[0].content)
    assert body["version"]["minorEdit"] is True


def test_update_page_does_not_include_id_in_body() -> None:
    """Page ID belongs in the URL path only — not in the PUT request body."""
    returned_page = {"id": "99", "title": "Updated", "version": {"number": 2}}
    transport = _MockTransport(_json_response(returned_page))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.update_page("99", "Updated", "<p>new</p>", version=2)
    body = json.loads(transport.requests[0].content)
    assert "id" not in body


def test_update_page_error_raises() -> None:
    transport = _MockTransport(_json_response({"error": "conflict"}, status_code=409))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="409"):
            client.update_page("99", "Title", "<p/>", version=2)


# ── list_attachments ──────────────────────────────────────────────────────────


def test_list_attachments_uses_v2_endpoint() -> None:
    """list_attachments must call the v2 /pages/{id}/attachments endpoint."""
    payload = {"results": [{"title": "diagram.png", "id": "att1"}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.list_attachments("99")
    req = transport.requests[0]
    assert "/wiki/api/v2/pages/99/attachments" in str(req.url)
    assert result == {"diagram.png": {"title": "diagram.png", "id": "att1"}}


def test_list_attachments_returns_name_map() -> None:
    payload = {
        "results": [
            {"title": "image.png", "id": "a1"},
            {"title": "chart.svg", "id": "a2"},
        ]
    }
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.list_attachments("99")
    assert set(result.keys()) == {"image.png", "chart.svg"}


# ── upload_attachment ─────────────────────────────────────────────────────────


def test_upload_attachment_uses_multipart_content_type(tmp_path: Path) -> None:
    """The upload request must use multipart/form-data, not application/json."""
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n")
    transport = _MockTransport(_json_response({"results": []}, status_code=200))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.upload_attachment("99", img, "photo.png")
    req = transport.requests[0]
    content_type = req.headers.get("content-type", "")
    assert "multipart/form-data" in content_type, (
        f"Expected multipart/form-data but got: {content_type!r}"
    )


def test_upload_attachment_sends_no_check_token(tmp_path: Path) -> None:
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")
    transport = _MockTransport(_json_response({"results": []}, status_code=200))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.upload_attachment("99", img, "img.png")
    req = transport.requests[0]
    assert req.headers.get("x-atlassian-token") == "no-check"


def test_upload_attachment_error_raises(tmp_path: Path) -> None:
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")
    transport = _MockTransport(_json_response({"error": "forbidden"}, status_code=403))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="403"):
            client.upload_attachment("99", img, "img.png")
