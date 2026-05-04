"""Confluence Cloud REST API client.

Uses the v2 API for page operations and the v1 REST API for attachments.
Authentication is HTTP Basic with email + API token.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import httpx

from mkdocs_to_confluence.loader.config import ConfluenceConfig


def _extract_cursor(next_url: str) -> str:
    """Extract the ``cursor`` query parameter from a pagination ``next`` URL."""
    qs = parse_qs(urlparse(next_url).query)
    cursors = qs.get("cursor", [])
    return cursors[0] if cursors else ""


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
                # Content-Type is intentionally NOT set globally — httpx
                # sets it per-request (application/json for json=, multipart
                # for files=).  A global Content-Type would prevent httpx from
                # auto-setting the correct multipart boundary on uploads.
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
        # Strip trailing slash and any trailing /wiki so users can supply either
        # "https://org.atlassian.net" or "https://org.atlassian.net/wiki".
        url = self._config.base_url.rstrip("/")
        if url.endswith("/wiki"):
            url = url[: -len("/wiki")]
        return url

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

    def get_space_id_from_page(self, page_id: str) -> str:
        """Return the numeric space ID by inspecting *page_id*.

        Useful when ``space_key`` is not configured — the space is derived
        from the parent page the user already knows.

        Raises :class:`ConfluenceError` when the page is not found.
        """
        url = self._v2(f"/pages/{page_id}")
        resp = self._http.get(url)
        if resp.status_code == 404:
            raise ConfluenceError(
                f"Parent page {page_id!r} not found (HTTP 404). "
                "Check that the page ID is correct (it is the number in the Confluence URL: "
                "/wiki/spaces/SPACE/pages/<ID>/...) and that your API token has access to it."
            )
        self._raise_for_status(resp, f"get_space_id_from_page({page_id!r})")
        data = resp.json()
        space_id = data.get("spaceId")
        if not space_id:
            raise ConfluenceError(f"Could not determine spaceId from page {page_id!r}.")
        return str(space_id)

    # ── Folders ────────────────────────────────────────────────────────────────

    def find_folder_under(
        self,
        parent_id: str,
        title: str,
        *,
        parent_is_folder: bool = False,
    ) -> dict[str, Any] | None:
        """Return the folder dict matching *title* under *parent_id*, or ``None``.

        Uses ``GET /folders/{id}/direct-children`` when the parent is itself a
        folder, otherwise ``GET /pages/{id}/direct-children``.  Both endpoints
        return mixed content types; we filter to ``type == "folder"``.
        """
        if parent_is_folder:
            url = self._v2(f"/folders/{parent_id}/direct-children")
        else:
            url = self._v2(f"/pages/{parent_id}/direct-children")

        resp = self._http.get(url, params={"limit": 250})
        self._raise_for_status(resp, f"find_folder_under({title!r})")
        for item in resp.json().get("results", []):
            if item.get("type") == "folder" and item.get("title") == title:
                return cast(dict[str, Any], item)
        return None

    def find_folder_in_space(self, space_id: str, title: str) -> dict[str, Any] | None:
        """Return a folder matching *title* anywhere in the space, or ``None``.

        Used as a fallback when a folder cannot be located via its parent
        (e.g. space-root folders created without a parentId).

        Uses the v1 CQL search API (``/rest/api/content/search``) which
        reliably supports folder type + title filtering, unlike the v2
        ``/folders`` endpoint which does not support query parameters.
        """
        space_key = self._config.space_key
        if not space_key:
            return None
        cql = f'type=folder AND title="{title}" AND space="{space_key}"'
        resp = self._http.get(
            self._v1("/content/search"),
            params={"cql": cql, "limit": 10},
        )
        self._raise_for_status(resp, f"find_folder_in_space({title!r})")
        for item in resp.json().get("results", []):
            if item.get("title") == title:
                return cast(dict[str, Any], item)
        return None

    def create_folder(
        self,
        space_id: str,
        title: str,
        *,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a native Confluence folder and return the response dict.

        If Confluence reports that a folder with the same title already exists
        in the space (HTTP 400), we fall back to a space-wide lookup and return
        the existing folder so callers can treat this as an idempotent operation.
        """
        payload: dict[str, Any] = {"spaceId": space_id, "title": title}
        if parent_id is not None:
            payload["parentId"] = parent_id
        resp = self._http.post(self._v2("/folders"), json=payload)
        if resp.status_code == 400:
            body = resp.text
            if "folder exists with the same title" in body.lower() or "same title" in body.lower():
                existing = self.find_folder_in_space(space_id, title)
                if existing is not None:
                    return existing
        self._raise_for_status(resp, f"create_folder({title!r})")
        return resp.json()  # type: ignore[no-any-return]

    # ── Pages ──────────────────────────────────────────────────────────────────

    def find_page(self, space_id: str, title: str) -> dict[str, Any] | None:
        """Return the page dict for *title* in *space_id*, or ``None``.

        Uses ``GET /spaces/{id}/pages`` (space ID in path) so that Confluence
        enforces the space scope server-side.  ``GET /pages?spaceId=...`` is
        undocumented and unreliable — it ignores the spaceId filter and may
        return pages from other spaces.
        """
        url = self._v2(f"/spaces/{space_id}/pages")
        resp = self._http.get(
            url,
            params={"title": title, "status": "current", "limit": 10},
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

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        version: int,
        *,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing page to a new version and return the page dict.

        ``minorEdit`` is set so Confluence does not notify all page watchers
        on every automated CI/CD publish.

        If *parent_id* is supplied the page is moved to that parent (re-parented).
        """
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
                "minorEdit": True,
            },
        }
        if parent_id is not None:
            payload["parentId"] = parent_id
        resp = self._http.put(self._v2(f"/pages/{page_id}"), json=payload)
        self._raise_for_status(resp, f"update_page({page_id!r})")
        return resp.json()  # type: ignore[no-any-return]

    def set_page_full_width(self, page_id: str) -> None:
        """Set the page layout to full-width via the content properties API.

        Uses the v1 ``content-appearance-published`` property.  Creates the
        property if it does not exist; updates it (with correct version bump)
        when it already does.
        """
        key = "content-appearance-published"
        prop_url = self._v1(f"/content/{page_id}/property/{key}")
        get_resp = self._http.get(prop_url)

        if get_resp.status_code == 200:
            current_version = get_resp.json().get("version", {}).get("number", 1)
            self._http.put(
                prop_url,
                json={"key": key, "value": "full-width", "version": {"number": current_version + 1}},
            )
        else:
            self._http.post(
                self._v1(f"/content/{page_id}/property"),
                json={"key": key, "value": "full-width", "version": {"number": 1}},
            )

    def get_content_hash(self, page_id: str) -> str | None:
        """Return the stored mk2conf content hash for *page_id*, or ``None``.

        Returns ``None`` on any error (property absent, API failure) so callers
        can safely treat a missing hash as "unknown — must update".
        """
        url = self._v1(f"/content/{page_id}/property/mk2conf-content-hash")
        resp = self._http.get(url)
        if resp.is_error:
            return None
        value = resp.json().get("value", "")
        return str(value) if value else None

    def set_content_hash(self, page_id: str, hash_str: str) -> None:
        """Store *hash_str* as the mk2conf content hash property on *page_id*.

        Creates the property on first publish; updates it (with version bump)
        on subsequent runs.  Errors are swallowed — this is a best-effort
        optimisation and must never block a publish.
        """
        key = "mk2conf-content-hash"
        prop_url = self._v1(f"/content/{page_id}/property/{key}")
        get_resp = self._http.get(prop_url)
        if get_resp.status_code == 200:
            current_version = get_resp.json().get("version", {}).get("number", 1)
            self._http.put(
                prop_url,
                json={"key": key, "value": hash_str, "version": {"number": current_version + 1}},
            )
        else:
            self._http.post(
                self._v1(f"/content/{page_id}/property"),
                json={"key": key, "value": hash_str, "version": {"number": 1}},
            )

    def set_page_labels(self, page_id: str, labels: tuple[str, ...]) -> None:
        """Replace all labels on *page_id* with *labels*.

        Existing labels are removed first so stale tags don't accumulate.
        Uses the v1 ``/content/{id}/label`` endpoint.
        """
        label_url = self._v1(f"/content/{page_id}/label")

        # Remove all existing labels
        existing_resp = self._http.get(label_url)
        if existing_resp.status_code == 200:
            for lbl in existing_resp.json().get("results", []):
                name = lbl.get("name", "")
                if name:
                    self._http.delete(label_url, params={"name": name})

        # Apply new labels (if any)
        if labels:
            payload = [{"prefix": "global", "name": lbl} for lbl in labels]
            resp = self._http.post(label_url, json=payload)
            self._raise_for_status(resp, f"set_page_labels({page_id!r})")

    def set_page_status(self, page_id: str, status_key: str) -> None:
        """Set the Confluence page status (e.g. ``rough-draft``, ``in-progress``).

        Uses the v1 ``PUT /content/{id}/state`` endpoint.  The *status_key*
        must match a state key configured in the Confluence space.
        """
        url = self._v1(f"/content/{page_id}/state")
        resp = self._http.put(url, json={"state": {"key": status_key}})
        self._raise_for_status(resp, f"set_page_status({page_id!r}, {status_key!r})")

    def list_attachments(self, page_id: str) -> dict[str, dict[str, Any]]:
        """Return a ``{filename: metadata}`` mapping of all page attachments.

        Uses the v2 ``GET /pages/{id}/attachments`` endpoint.
        """
        url = self._v2(f"/pages/{page_id}/attachments")
        resp = self._http.get(url, params={"limit": 250})
        self._raise_for_status(resp, f"list_attachments({page_id!r})")
        results: list[dict[str, Any]] = resp.json().get("results", [])
        return {r["title"]: r for r in results}

    def upload_attachment(
        self,
        page_id: str,
        path: Path,
        filename: str,
        existing: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Upload or update a file attachment on *page_id*.

        If an attachment with *filename* already exists on the page, its data
        is replaced via the v1 update endpoint.  Otherwise a new attachment is
        created.

        *existing* is the pre-fetched ``{filename: metadata}`` mapping from
        :meth:`list_attachments`.  Pass it to avoid a redundant API call when
        uploading multiple attachments for the same page.  If ``None``,
        :meth:`list_attachments` is called automatically.

        Confluence requires the ``X-Atlassian-Token: no-check`` header to
        disable XSRF protection for attachment uploads.  The v2 API has no
        upload endpoint, so v1 is used here.
        """
        with path.open("rb") as fh:
            content = fh.read()

        # Use pre-fetched listing when available to avoid a race condition when
        # uploading multiple attachments in parallel (all threads would otherwise
        # call list_attachments simultaneously, see the page as empty, and all
        # attempt to CREATE the same file — triggering a 500 from Confluence).
        if existing is None:
            existing = self.list_attachments(page_id)
        existing_meta = existing.get(filename)

        if existing_meta:
            attachment_id = existing_meta["id"]
            url = self._v1(f"/content/{page_id}/child/attachment/{attachment_id}/data")
        else:
            url = self._v1(f"/content/{page_id}/child/attachment")

        resp = self._http.post(
            url,
            files={"file": (filename, content)},
            headers={"X-Atlassian-Token": "no-check"},
        )
        self._raise_for_status(resp, f"upload_attachment({filename!r})")

    # ── Orphan detection ───────────────────────────────────────────────────────

    def stamp_managed(self, page_id: str) -> None:
        """Mark *page_id* as managed by mk2conf via a v2 content property.

        The property ``mk2conf-managed`` is set to ``true`` on first publish and
        never updated.  It is used by :meth:`is_managed` to distinguish pages
        created by mk2conf from manually-created Confluence pages.

        Errors are swallowed — this is a best-effort stamp and must never block
        a publish.
        """
        url = self._v2(f"/pages/{page_id}/properties/mk2conf-managed")
        get_resp = self._http.get(url)
        if get_resp.status_code == 200:
            return  # already stamped
        self._http.post(
            self._v2(f"/pages/{page_id}/properties"),
            json={"key": "mk2conf-managed", "value": True},
        )

    def get_descendant_ids(self, page_id: str) -> list[str]:
        """Return all descendant page IDs under *page_id* at all depths.

        Uses ``GET /wiki/api/v2/pages/{id}/descendants?depth=all``.
        Paginates automatically via cursor.  Returns page IDs only — callers
        that need to filter by managed status use :meth:`is_managed`.
        """
        ids: list[str] = []
        url = self._v2(f"/pages/{page_id}/descendants")
        params: dict[str, str | int] = {"depth": "all", "limit": 250}
        while True:
            resp = self._http.get(url, params=params)
            self._raise_for_status(resp, f"get_descendant_ids({page_id!r})")
            data = resp.json()
            for item in data.get("results", []):
                if item.get("type") == "page":
                    ids.append(str(item["id"]))
            next_url = data.get("_links", {}).get("next")
            if not next_url:
                break
            # next_url is an absolute path — extract cursor and re-request
            url = self._v2(f"/pages/{page_id}/descendants")
            params = {"depth": "all", "limit": 250, "cursor": _extract_cursor(next_url)}
        return ids

    def is_managed(self, page_id: str) -> bool:
        """Return ``True`` if *page_id* has the ``mk2conf-managed`` property."""
        resp = self._http.get(self._v2(f"/pages/{page_id}/properties/mk2conf-managed"))
        return resp.status_code == 200

    def delete_page(self, page_id: str) -> None:
        """Permanently delete *page_id* from Confluence."""
        resp = self._http.delete(self._v2(f"/pages/{page_id}"))
        self._raise_for_status(resp, f"delete_page({page_id!r})")
