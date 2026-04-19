"""Shared fence-tracking utility for Markdown code-block detection.

Used by preprocessing passes that need to know whether a line falls inside a
fenced code block (`` ``` `` or ``~~~``) so that they skip processing for those
lines.
"""

from __future__ import annotations

import re

_FENCE_OPEN_RE = re.compile(r"^(?P<char>`{3,}|~{3,})")
_FENCE_CLOSE_RE = re.compile(r"^(?P<char>`{3,}|~{3,})\s*$")


class FenceTracker:
    """Tracks whether we are currently inside a fenced code block.

    Call :meth:`update` for each line (stripped of its trailing newline) in
    document order.  After the call, :attr:`in_fence` reflects the new state.

    Example::

        tracker = FenceTracker()
        for line in text.splitlines(keepends=True):
            was_in_fence = tracker.in_fence
            tracker.update(line.rstrip("\\n").rstrip("\\r"))
            now_in_fence = tracker.in_fence
            # was_in_fence / now_in_fence tell you about the transition
    """

    def __init__(self) -> None:
        self.in_fence: bool = False
        self._fence_char: str = ""
        self._fence_min_len: int = 0

    def update(self, stripped_line: str) -> None:
        """Update fence state from *stripped_line* (no trailing newline)."""
        if not self.in_fence:
            m = _FENCE_OPEN_RE.match(stripped_line)
            if m:
                marker = m.group("char")
                self._fence_char = marker[0]
                self._fence_min_len = len(marker)
                self.in_fence = True
        else:
            m = _FENCE_CLOSE_RE.match(stripped_line)
            if (
                m
                and m.group("char")[0] == self._fence_char
                and len(m.group("char")) >= self._fence_min_len
            ):
                self.in_fence = False
                self._fence_char = ""
                self._fence_min_len = 0
