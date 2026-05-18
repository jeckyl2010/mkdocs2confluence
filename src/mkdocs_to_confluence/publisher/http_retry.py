"""HTTP retry helpers for Confluence API calls.

Handles 429 rate-limiting with ``Retry-After`` header support and
exponential backoff with jitter.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

import httpx

_MAX_RETRIES = 3
_RETRY_AFTER_CAP = 60.0  # seconds — cap Retry-After to avoid indefinite stalls


class ConfluenceError(RuntimeError):
    """Raised when the Confluence API returns an unexpected response."""


def http_request_with_retry(fn: Callable[[], httpx.Response], context: str) -> httpx.Response:
    """Call *fn* and retry up to ``_MAX_RETRIES`` times on HTTP 429.

    Respects the ``Retry-After`` response header (capped at
    ``_RETRY_AFTER_CAP`` seconds).  Falls back to exponential backoff with
    jitter when the header is absent or invalid.  Prints a warning on each
    retry.  Raises :class:`ConfluenceError` if all retries are exhausted.
    """
    for attempt in range(_MAX_RETRIES + 1):
        resp = fn()
        if resp.status_code != 429:
            return resp
        if attempt == _MAX_RETRIES:
            raise ConfluenceError(
                f"{context}: rate-limited after {_MAX_RETRIES} retries — giving up"
            )
        header = resp.headers.get("Retry-After", "")
        try:
            wait = min(float(header), _RETRY_AFTER_CAP)
        except ValueError:
            wait = min(2.0 ** attempt + random.uniform(0.0, 1.0), _RETRY_AFTER_CAP)
        print(
            f"  ⚠ rate-limited ({context}) — retrying in {wait:.1f}s"
            f" (attempt {attempt + 1}/{_MAX_RETRIES})",
            flush=True,
        )
        time.sleep(wait)
    raise ConfluenceError(f"{context}: rate-limited")  # unreachable
