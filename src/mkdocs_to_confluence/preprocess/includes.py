"""Resolve ``--8<--`` (pymdownx.snippets) include directives in raw markdown.

Supported syntax
----------------
* ``--8<-- "path/to/file"``        — include the entire file
* ``--8<-- "path/to/file:N:M"``    — include lines N through M (1-based, inclusive)

Not yet supported (post-MVP)
-----------------------------
* Named section markers: ``--8<-- "file:section_name"``

Rules
-----
* Directives inside fenced code blocks (``` ``` ``` or ``~~~``) are **not** expanded.
* Path resolution order: ``docs_dir / path`` first, then ``source_path.parent / path``.
* Circular includes are detected and raise :class:`IncludeError`.
* Missing files raise :class:`IncludeError` with the source location.
"""

from __future__ import annotations

import re
from pathlib import Path


class IncludeError(Exception):
    """Raised when an include directive cannot be resolved.

    The message always contains the including file path and line number so that
    callers can surface a useful diagnostic without additional context.
    """


# Matches the opening characters of a fenced code block.
# A closing fence must be the same character with at least as many repetitions
# and nothing else on the line (trailing spaces allowed).
_FENCE_OPEN_RE = re.compile(r"^(?P<char>`{3,}|~{3,})")
_FENCE_CLOSE_RE = re.compile(r"^(?P<char>`{3,}|~{3,})\s*$")

# Matches a snippet directive that occupies its own line.
# The path argument is a quoted string immediately after ``--8<-- ``.
_SNIPPET_RE = re.compile(r'^--8<--\s+"(?P<path>[^"]+)"\s*$')


def preprocess_includes(
    text: str,
    source_path: Path,
    docs_dir: Path,
    *,
    _seen: frozenset[Path] | None = None,
) -> str:
    """Resolve all ``--8<--`` include directives in *text* and return the result.

    Args:
        text: Raw markdown content to preprocess.
        source_path: Absolute path of the file that contains *text*.
            Used for relative-path resolution and error messages.
        docs_dir: Absolute path to the MkDocs ``docs`` directory.
            Include paths are resolved here first.
        _seen: Internal — the set of already-open files on the current
            include chain, used for circular-include detection.

    Returns:
        The preprocessed markdown text with all includes expanded.

    Raises:
        IncludeError: If an included file is missing, unreadable, circularly
            referenced, or uses unsupported snippet syntax.
    """
    if _seen is None:
        _seen = frozenset()

    source_path = source_path.resolve()
    docs_dir = docs_dir.resolve()

    lines = text.splitlines(keepends=True)
    result: list[str] = []

    in_fence = False
    fence_char: str = ""
    fence_min_len: int = 0

    for lineno, line in enumerate(lines, start=1):
        stripped = line.rstrip("\n").rstrip("\r")

        # ── Fence tracking ──────────────────────────────────────────────────
        if not in_fence:
            m = _FENCE_OPEN_RE.match(stripped)
            if m:
                marker = m.group("char")
                fence_char = marker[0]
                fence_min_len = len(marker)
                in_fence = True
                result.append(line)
                continue
        else:
            m = _FENCE_CLOSE_RE.match(stripped)
            if (
                m
                and m.group("char")[0] == fence_char
                and len(m.group("char")) >= fence_min_len
            ):
                in_fence = False
                fence_char = ""
                fence_min_len = 0
            result.append(line)
            continue

        # ── Snippet directive ────────────────────────────────────────────────
        m = _SNIPPET_RE.match(stripped)
        if not m:
            result.append(line)
            continue

        raw_spec = m.group("path")
        rel_path, start_line, end_line = _parse_spec(raw_spec, source_path, lineno)

        included_path = _resolve_path(rel_path, source_path, docs_dir)
        if included_path is None:
            raise IncludeError(
                f"{source_path}:{lineno}: included file not found: {rel_path!r}\n"
                f"  Searched in: {docs_dir / rel_path}  (docs_dir)\n"
                f"             : {source_path.parent / rel_path}  (relative)"
            )

        if included_path in _seen:
            raise IncludeError(
                f"{source_path}:{lineno}: circular include detected.\n"
                f"  {included_path} is already open in the include chain:\n"
                + _format_chain(_seen, included_path)
            )

        try:
            included_text = included_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise IncludeError(
                f"{source_path}:{lineno}: cannot read included file "
                f"{included_path}: {exc}"
            ) from exc

        if start_line is not None and end_line is not None:
            all_lines = included_text.splitlines(keepends=True)
            included_text = "".join(all_lines[start_line - 1 : end_line])

        # Recurse: the included file may itself contain includes.
        included_text = preprocess_includes(
            included_text,
            source_path=included_path,
            docs_dir=docs_dir,
            _seen=_seen | {source_path},
        )

        # Ensure the included block ends with a newline so that subsequent
        # markdown content is not merged onto the same line.
        if included_text and not included_text.endswith("\n"):
            included_text += "\n"

        result.append(included_text)

    return "".join(result)


# ── Private helpers ──────────────────────────────────────────────────────────


def _parse_spec(
    raw_spec: str, source_path: Path, lineno: int
) -> tuple[str, int | None, int | None]:
    """Parse the path spec from a snippet directive.

    Returns ``(rel_path, start_line, end_line)``.  ``start_line`` and
    ``end_line`` are ``None`` for whole-file includes.

    Raises:
        IncludeError: For unrecognised or unsupported spec formats.
    """
    parts = raw_spec.split(":")

    if len(parts) == 1:
        return raw_spec, None, None

    if len(parts) == 2:
        # Two-segment spec: "file:something" where "something" is a named section.
        raise IncludeError(
            f"{source_path}:{lineno}: named-section includes are not yet "
            f"supported: {raw_spec!r}"
        )

    if len(parts) == 3:
        rel_path, raw_start, raw_end = parts
        try:
            start = int(raw_start)
            end = int(raw_end)
        except ValueError:
            # Non-integer second/third segment → likely a named section.
            raise IncludeError(
                f"{source_path}:{lineno}: named-section includes are not yet "
                f"supported: {raw_spec!r}"
            )
        if start < 1 or end < start:
            raise IncludeError(
                f"{source_path}:{lineno}: invalid line range {start}:{end} "
                f"in snippet {raw_spec!r} — start must be ≥ 1 and end ≥ start."
            )
        return rel_path, start, end

    raise IncludeError(
        f"{source_path}:{lineno}: unsupported snippet spec: {raw_spec!r}"
    )


def _resolve_path(rel_path: str, source_path: Path, docs_dir: Path) -> Path | None:
    """Resolve *rel_path* to an existing file.

    Resolution order:
    1. ``docs_dir / rel_path``          (pymdownx.snippets default)
    2. ``source_path.parent / rel_path``  (sibling-file relative)
    """
    for base in (docs_dir, source_path.parent):
        candidate = (base / rel_path).resolve()
        if candidate.is_file():
            return candidate
    return None


def _format_chain(seen: frozenset[Path], target: Path) -> str:
    """Format a human-readable include chain for error messages."""
    # seen is unordered; we just list the files involved.
    paths = sorted(seen | {target})
    return "\n".join(f"    {p}" for p in paths)
