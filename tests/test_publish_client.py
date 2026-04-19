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
    """Simple transport that returns a pre-configured response."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._response


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


# ── find_page ─────────────────────────────────────────────────────────────────


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


def test_update_page_error_raises() -> None:
    transport = _MockTransport(_json_response({"error": "conflict"}, status_code=409))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="409"):
            client.update_page("99", "Title", "<p/>", version=2)
