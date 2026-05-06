"""Map Confluence inlineOriginalSelection text to a source file line number."""

from __future__ import annotations

from pathlib import Path


def find_anchor_line(source_path: Path, selection_text: str) -> int | None:
    """Return the 1-based line number of the first line containing *selection_text*.

    Returns ``None`` when:
    - *selection_text* is empty
    - the file cannot be read
    - no line contains the text
    """
    if not selection_text:
        return None
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for i, line in enumerate(lines, start=1):
        if selection_text in line:
            return i
    return None
