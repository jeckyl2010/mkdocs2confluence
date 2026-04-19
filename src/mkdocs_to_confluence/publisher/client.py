"""Confluence Cloud REST API client.

Uses the v2 API for page operations and the v1 REST API for attachments.
Authentication is HTTP Basic with email + API token.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from mkdocs_to_confluence.loader.config import ConfluenceConfig


class ConfluenceError(RuntimeError):
    """Raised when the Confluence API returns an unexpected response."""


class ConfluenceClient:
    """Thin HTTP wrapper around the Confluence Cloud REST API."""

    def __init__(self, config: ConfluenceConfig) -> None:
        self._config = config
        self._client: httpx.Client | None = None

    # ── Context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> ConfluenceClient:
        credentials = f"{self._config.email}:{self._config.token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self._client = httpx.Client(
            headers={
                "Authorization": f"Basic {encoded}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        return self

    def __exit__(self, *_: object) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ── Internal helpers ───────────────────────────────────────────────────────

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            raise RuntimeError("ConfluenceClient must be used as a context manager.")
        return self._client

    def _base(self) -> str:
        return self._config.base_url.rstrip("/")

    def _v2(self, path: str) -> str:
        return f"{self._base()}/wiki/api/v2{path}"

    def _v1(self, path: str) -> str:
        return f"{self._base()}/wiki/rest/api{path}"

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        if response.is_error:
            raise ConfluenceError(
                f"{context}: HTTP {response.status_code} — {response.text[:400]}"
            )

    # ── Space ──────────────────────────────────────────────────────────────────

    def get_space_id(self, space_key: str) -> str:
        """Return the numeric space ID for *space_key*.

        Raises :class:`ConfluenceError` when the space is not found.
        """
        url = self._v2("/spaces")
        resp = self._http.get(url, params={"keys": space_key, "limit": 1})
        self._raise_for_status(resp, f"get_space_id({space_key!r})")
        data = resp.json()
        results = data.get("results", [])
        if not results:
            raise ConfluenceError(f"Space with key {space_key!r} not found.")
        return str(results[0]["id"])

    # ── Pages ──────────────────────────────────────────────────────────────────

    def find_page(self, space_id: str, title: str) -> dict[str, Any] | None:
        """Return the page dict for *title* in *space_id*, or ``None``."""
        url = self._v2("/pages")
        resp = self._http.get(
            url,
            params={
                "spaceId": space_id,
                "title": title,
                "status": "current",
                "body-format": "storage",
                "limit": 1,
            },
        )
        self._raise_for_status(resp, f"find_page({title!r})")
        results: list[dict[str, Any]] = resp.json().get("results", [])
        return results[0] if results else None

    def create_page(
        self,
        space_id: str,
        title: str,
        body: str,
        *,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Confluence page and return the full page dict."""
        payload: dict[str, Any] = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body,
            },
        }
        if parent_id is not None:
            payload["parentId"] = parent_id

        resp = self._http.post(self._v2("/pages"), json=payload)
        self._raise_for_status(resp, f"create_page({title!r})")
        return resp.json()  # type: ignore[no-any-return]

    def update_page(self, page_id: str, title: str, body: str, version: int) -> dict[str, Any]:
        """Update an existing page to a new version and return the page dict."""
        payload: dict[str, Any] = {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body,
            },
            "version": {
                "number": version,
                "message": "Updated by mk2conf",
            },
        }
        resp = self._http.put(self._v2(f"/pages/{page_id}"), json=payload)
        self._raise_for_status(resp, f"update_page({page_id!r})")
        return resp.json()  # type: ignore[no-any-return]

    # ── Attachments ────────────────────────────────────────────────────────────

    def list_attachments(self, page_id: str) -> dict[str, dict[str, Any]]:
        """Return a ``{filename: metadata}`` mapping of all page attachments."""
        url = self._v1(f"/content/{page_id}/child/attachment")
        resp = self._http.get(url, params={"limit": 200})
        self._raise_for_status(resp, f"list_attachments({page_id!r})")
        results: list[dict[str, Any]] = resp.json().get("results", [])
        return {r["title"]: r for r in results}

    def upload_attachment(self, page_id: str, path: Path, filename: str) -> None:
        """Upload (or replace) a file attachment on *page_id*.

        Confluence requires the ``X-Atlassian-Token: no-check`` header to
        disable XSRF protection for attachment uploads.
        """
        url = self._v1(f"/content/{page_id}/child/attachment")
        with path.open("rb") as fh:
            content = fh.read()

        # Build multipart without the json Content-Type header
        files = {"file": (filename, content)}
        headers = {"X-Atlassian-Token": "no-check"}
        # Remove Content-Type so httpx sets it correctly for multipart
        upload_client = httpx.Client(
            headers={
                "Authorization": self._http.headers["Authorization"],
                "Accept": "application/json",
                "X-Atlassian-Token": "no-check",
            },
            timeout=60.0,
        )
        with upload_client:
            resp = upload_client.post(url, files=files)
        if resp.is_error:
            raise ConfluenceError(
                f"upload_attachment({filename!r}): HTTP {resp.status_code} — {resp.text[:400]}"
            )
