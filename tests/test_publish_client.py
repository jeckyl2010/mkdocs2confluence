"""Tests for ConfluenceClient using httpx mock transport."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_base_url_with_trailing_wiki_is_stripped() -> None:
    """base_url ending in /wiki must not produce double /wiki in requests."""
    payload = {"id": "999", "spaceId": "42", "title": "Parent Page"}
    transport = _MockTransport(_json_response(payload))
    config = ConfluenceConfig(
        base_url="https://example.atlassian.net/wiki",
        space_key="TECH",
        email="user@example.com",
        token="tok",
    )
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.get_space_id_from_page("999")
    url = str(transport.requests[0].url)
    assert "/wiki/wiki/" not in url
    assert url.endswith("/wiki/api/v2/pages/999")





# ── set_page_labels ───────────────────────────────────────────────────────────


def test_set_page_labels_posts_new_labels() -> None:
    """When page has no existing labels, POST the new ones."""
    transport = _MockTransport(
        _json_response({"results": []}),     # GET existing labels → empty
        _json_response([{"name": "arch"}]),  # POST new labels
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_page_labels("42", ("arch", "api"))
    assert transport.requests[0].method == "GET"
    post_body = json.loads(transport.requests[1].content)
    assert {"prefix": "global", "name": "arch"} in post_body
    assert {"prefix": "global", "name": "api"} in post_body


def test_set_page_labels_removes_old_labels_first() -> None:
    """Existing labels are deleted before new ones are applied."""
    transport = _MockTransport(
        _json_response({"results": [{"name": "old-tag"}]}),  # GET existing
        _json_response({}),   # DELETE old-tag
        _json_response([]),   # POST new labels
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_page_labels("42", ("new-tag",))
    assert transport.requests[1].method == "DELETE"
    assert "old-tag" in str(transport.requests[1].url)


def test_set_page_labels_skips_post_when_empty() -> None:
    """No POST is made when labels tuple is empty."""
    transport = _MockTransport(
        _json_response({"results": []}),  # GET existing → empty
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_page_labels("42", ())
    assert len(transport.requests) == 1  # only GET, no POST


# ── set_page_status ───────────────────────────────────────────────────────────


def test_set_page_status_sends_put() -> None:
    """set_page_status PUTs name-based body to the v1 /content/{id}/state endpoint."""
    transport = _MockTransport(httpx.Response(200, json={}))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_page_status("42", "in-progress")
    assert len(transport.requests) == 1
    req = transport.requests[0]
    assert req.method == "PUT"
    assert "/content/42/state" in str(req.url)
    import json
    body = json.loads(req.content)
    assert body == {"name": "In Progress"}


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


# ── get/set_content_hash ──────────────────────────────────────────────────────


def test_get_content_hash_returns_stored_value() -> None:
    prop = {"key": "mk2conf-content-hash", "value": "abc123", "version": {"number": 1}}
    transport = _MockTransport(_json_response(prop))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.get_content_hash("42")
    assert result == "abc123"
    assert "/content/42/property/mk2conf-content-hash" in transport.requests[0].url.path


def test_get_content_hash_returns_none_on_404() -> None:
    transport = _MockTransport(httpx.Response(404, text="not found"))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.get_content_hash("42")
    assert result is None


def test_get_content_hash_returns_none_on_error() -> None:
    transport = _MockTransport(httpx.Response(500, text="oops"))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.get_content_hash("42")
    assert result is None


def test_set_content_hash_creates_property_when_absent() -> None:
    responses = [
        httpx.Response(404, text="not found"),  # GET — absent
        httpx.Response(200, json={}),           # POST — create
    ]
    transport = _MockTransport(*responses)
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_content_hash("42", "deadbeef")
    assert transport.requests[0].method == "GET"
    assert transport.requests[1].method == "POST"
    body = json.loads(transport.requests[1].content)
    assert body["key"] == "mk2conf-content-hash"
    assert body["value"] == "deadbeef"
    assert body["version"]["number"] == 1


def test_set_content_hash_updates_property_when_present() -> None:
    existing = {"key": "mk2conf-content-hash", "value": "old", "version": {"number": 2}}
    responses = [
        httpx.Response(200, json=existing),  # GET — present
        httpx.Response(200, json={}),        # PUT — update
    ]
    transport = _MockTransport(*responses)
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.set_content_hash("42", "newdeadbeef")
    assert transport.requests[1].method == "PUT"
    body = json.loads(transport.requests[1].content)
    assert body["value"] == "newdeadbeef"
    assert body["version"]["number"] == 3


def test_find_page_returns_page_dict() -> None:
    page = {"id": "99", "spaceId": "42", "title": "My Page", "version": {"number": 3}}
    payload = {"results": [page]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_page("42", "My Page")
    assert result is not None
    assert result["id"] == "99"


def test_find_page_uses_space_scoped_endpoint() -> None:
    """find_page must use /spaces/{id}/pages so the API enforces space scope server-side."""
    payload = {"results": [{"id": "99", "title": "My Page", "version": {"number": 1}}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.find_page("42", "My Page")
    req = transport.requests[0]
    assert "/spaces/42/pages" in str(req.url)
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


def test_update_page_includes_id_in_body() -> None:
    """Confluence v2 PUT /pages/{id} requires id in the request body."""
    returned_page = {"id": "99", "title": "Updated", "version": {"number": 2}}
    transport = _MockTransport(_json_response(returned_page))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.update_page("99", "Updated", "<p>new</p>", version=2)
    body = json.loads(transport.requests[0].content)
    assert body["id"] == "99"


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
    # First response: list_attachments (empty), second: the upload itself
    transport = _MockTransport(
        _json_response({"results": []}),
        _json_response({"results": []}, status_code=200),
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.upload_attachment("99", img, "photo.png")
    req = transport.requests[1]  # second request is the upload
    content_type = req.headers.get("content-type", "")
    assert "multipart/form-data" in content_type, (
        f"Expected multipart/form-data but got: {content_type!r}"
    )


def test_upload_attachment_sends_no_check_token(tmp_path: Path) -> None:
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")
    transport = _MockTransport(
        _json_response({"results": []}),
        _json_response({"results": []}, status_code=200),
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.upload_attachment("99", img, "img.png")
    req = transport.requests[1]
    assert req.headers.get("x-atlassian-token") == "no-check"


def test_upload_attachment_updates_existing(tmp_path: Path) -> None:
    """When attachment already exists, PUT to the existing attachment's data endpoint."""
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")
    existing = {"results": [{"title": "img.png", "id": "att-42"}]}
    transport = _MockTransport(
        _json_response(existing),
        _json_response({"id": "att-42"}, status_code=200),
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.upload_attachment("99", img, "img.png")
    upload_req = transport.requests[1]
    assert "/attachment/att-42/data" in str(upload_req.url)


def test_upload_attachment_error_raises(tmp_path: Path) -> None:
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")
    transport = _MockTransport(
        _json_response({"results": []}),
        _json_response({"error": "forbidden"}, status_code=403),
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="403"):
            client.upload_attachment("99", img, "img.png")


# ── Orphan detection ───────────────────────────────────────────────────────────


def test_stamp_managed_posts_when_absent() -> None:
    transport = _MockTransport(
        httpx.Response(404, text="not found"),  # GET — absent
        httpx.Response(200, json={}),           # POST — create
    )
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.stamp_managed("42")
    assert transport.requests[0].method == "GET"
    assert "/properties/mk2conf-managed" in str(transport.requests[0].url)
    assert transport.requests[1].method == "POST"
    body = json.loads(transport.requests[1].content)
    assert body["key"] == "mk2conf-managed"
    assert body["value"] is True


def test_stamp_managed_skips_when_already_stamped() -> None:
    transport = _MockTransport(httpx.Response(200, json={"key": "mk2conf-managed", "value": True}))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.stamp_managed("42")
    assert len(transport.requests) == 1  # only the GET, no POST


def test_get_descendant_ids_returns_page_ids() -> None:
    payload = {
        "results": [
            {"id": "10", "type": "page"},
            {"id": "11", "type": "page"},
        ],
        "_links": {},
    }
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        ids = client.get_descendant_ids("99")
    assert ids == ["10", "11"]


def test_get_descendant_ids_paginates() -> None:
    page1 = {
        "results": [{"id": "10", "type": "page"}],
        "_links": {"next": "/wiki/api/v2/pages/99/descendants?cursor=abc&depth=all"},
    }
    page2 = {
        "results": [{"id": "11", "type": "page"}],
        "_links": {},
    }
    transport = _MockTransport(_json_response(page1), _json_response(page2))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        ids = client.get_descendant_ids("99")
    assert ids == ["10", "11"]
    assert len(transport.requests) == 2


def test_is_managed_returns_true_when_present() -> None:
    transport = _MockTransport(httpx.Response(200, json={"key": "mk2conf-managed", "value": True}))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        assert client.is_managed("42") is True


def test_is_managed_returns_false_when_absent() -> None:
    transport = _MockTransport(httpx.Response(404, text="not found"))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        assert client.is_managed("42") is False


def test_delete_page_sends_delete_request() -> None:
    transport = _MockTransport(httpx.Response(204, text=""))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.delete_page("42")
    assert transport.requests[0].method == "DELETE"
    assert "/pages/42" in str(transport.requests[0].url)


def test_delete_page_raises_on_error() -> None:
    transport = _MockTransport(httpx.Response(403, text="forbidden"))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError):
            client.delete_page("42")


# ── _http raises when not used as context manager ─────────────────────────────


def test_http_raises_when_not_context_manager() -> None:
    """Accessing _http outside a context manager must raise RuntimeError."""
    from mkdocs_to_confluence.publisher.client import ConfluenceClient
    config = _make_config()
    client = ConfluenceClient(config)
    with pytest.raises(RuntimeError, match="context manager"):
        _ = client._http


# ── get_space_id_from_page: 404 ───────────────────────────────────────────────


def test_get_space_id_from_page_raises_on_404() -> None:
    """HTTP 404 must raise ConfluenceError with a helpful message."""
    transport = _MockTransport(_json_response({"message": "Not Found"}, status_code=404))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        with pytest.raises(ConfluenceError, match="404"):
            client.get_space_id_from_page("999")


# ── update_page with parent_id ────────────────────────────────────────────────


def test_update_page_includes_parent_id_when_provided() -> None:
    """When parent_id is supplied it must appear in the request body."""
    returned_page = {"id": "99", "title": "Updated", "version": {"number": 2}}
    transport = _MockTransport(_json_response(returned_page))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        client.update_page("99", "Updated", "<p>new</p>", version=2, parent_id="77")
    body = json.loads(transport.requests[0].content)
    assert body["parentId"] == "77"


# ── find_folder_under ─────────────────────────────────────────────────────────


def test_find_folder_under_page_parent() -> None:
    """Uses /pages/{id}/direct-children when parent is a page."""
    payload = {"results": [{"type": "folder", "title": "Section", "id": "77"}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_folder_under("ROOT", "Section", parent_is_folder=False)
    assert result is not None
    assert result["id"] == "77"
    assert "/pages/ROOT/direct-children" in str(transport.requests[0].url)


def test_find_folder_under_folder_parent() -> None:
    """Uses /folders/{id}/direct-children when parent_is_folder=True."""
    payload = {"results": [{"type": "folder", "title": "Sub", "id": "88"}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_folder_under("FOLDERID", "Sub", parent_is_folder=True)
    assert result is not None
    assert result["id"] == "88"
    assert "/folders/FOLDERID/direct-children" in str(transport.requests[0].url)


def test_find_folder_under_returns_none_when_not_found() -> None:
    payload = {"results": [{"type": "page", "title": "Other", "id": "99"}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_folder_under("ROOT", "Missing", parent_is_folder=False)
    assert result is None


# ── find_folder_in_space ──────────────────────────────────────────────────────


def test_find_folder_in_space_returns_match() -> None:
    payload = {"results": [{"title": "Section", "id": "55"}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_folder_in_space("42", "Section")
    assert result is not None
    assert result["id"] == "55"


def test_find_folder_in_space_returns_none_when_no_space_key() -> None:
    """Returns None immediately when space_key is not configured."""
    from mkdocs_to_confluence.loader.config import ConfluenceConfig
    config = ConfluenceConfig(
        base_url="https://example.atlassian.net",
        space_key=None,
        email="user@example.com",
        token="tok",
        parent_page_id="999",
    )
    with ConfluenceClient(config) as client:
        client._client = httpx.Client()  # type: ignore[assignment]
        result = client.find_folder_in_space("42", "Section")
    assert result is None


def test_find_folder_in_space_returns_none_when_no_match() -> None:
    payload = {"results": [{"title": "OtherFolder", "id": "55"}]}
    transport = _MockTransport(_json_response(payload))
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.find_folder_in_space("42", "TargetFolder")
    assert result is None


# ── create_folder: 400 fallback ───────────────────────────────────────────────


def test_create_folder_returns_existing_on_400_duplicate() -> None:
    """When Confluence returns 400 'same title', falls back to find_folder_in_space."""
    bad_response = httpx.Response(
        400,
        content=b"folder exists with the same title",
        headers={"Content-Type": "text/plain"},
    )
    existing_folder_payload = {"results": [{"title": "MySection", "id": "77"}]}
    good_response = _json_response(existing_folder_payload)
    transport = _MockTransport(bad_response, good_response)
    config = _make_config()
    with ConfluenceClient(config) as client:
        client._client = httpx.Client(transport=transport)  # type: ignore[assignment]
        result = client.create_folder("42", "MySection")
    assert result["id"] == "77"
