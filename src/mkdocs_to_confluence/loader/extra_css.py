"""Parse extra_css files from mkdocs.yml and extract styles applicable to Confluence.

Only a curated whitelist of selectors and properties is extracted — anything
Confluence storage format cannot express as inline ``style="..."`` attributes
is silently ignored (e.g. ``:hover``, ``@media``, ``pre code``).

Supported selectors (last significant token determines category):
  ``th``, ``thead th``          → applied to table header cells
  ``td``                        → applied to table body cells
  ``h1`` – ``h6``              → applied to headings
  ``code`` (not ``pre code``)  → applied to inline code spans

Supported properties:
  ``background-color``, ``color``, ``font-weight``, ``font-style``,
  ``font-size``, ``text-align``, ``border``

CSS custom properties (``var(--name)``) are resolved by a two-pass approach:
  1. All ``--name: value`` declarations are collected from the file.
  2. ``var(--name)`` references in whitelisted property values are substituted
     recursively.  Fallback syntax ``var(--name, fallback)`` is honoured.
     Properties whose value cannot be fully resolved are silently skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import tinycss2

_MAX_VAR_DEPTH = 10  # cycle / deep-chain guard

_ALLOWED_PROPS: frozenset[str] = frozenset(
    {
        "background-color",
        "color",
        "font-weight",
        "font-style",
        "font-size",
        "text-align",
        "border",
    }
)

# Headings we care about
_HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

# Matches a bare URL (we skip external CSS)
_URL_RE = re.compile(r"^https?://")


@dataclass
class ExtraStyles:
    """Collected inline styles to inject into the Confluence emitter."""

    th: dict[str, str] = field(default_factory=dict)
    td: dict[str, str] = field(default_factory=dict)
    headings: dict[str, dict[str, str]] = field(default_factory=dict)  # "h1" → {prop: val}
    code_inline: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.th or self.td or self.headings or self.code_inline)


def _collect_custom_props(css_text: str) -> dict[str, str]:
    """First pass: collect every ``--name: value`` declaration from *css_text*.

    All rules are scanned (not just ``:root``) so that Material for MkDocs
    theme-variant selectors like ``[data-md-color-scheme="slate"]`` are also
    picked up as best-effort fallbacks.
    """
    custom_props: dict[str, str] = {}
    rules = tinycss2.parse_stylesheet(css_text, skip_comments=True, skip_whitespace=True)
    for rule in rules:
        if rule.type != "qualified-rule":
            continue
        decls = tinycss2.parse_blocks_contents(rule.content, skip_whitespace=True)
        for decl in decls:
            if decl.type != "declaration":
                continue
            if decl.name.startswith("--"):
                value = tinycss2.serialize(decl.value).strip()
                if value:
                    custom_props[decl.name] = value
    return custom_props


def _resolve_var_call(arguments: list, custom_props: dict[str, str], depth: int) -> list | None:
    """Resolve a single ``var(--name[, fallback])`` token list.

    Returns a token list with the variable substituted, or ``None`` if the
    variable is not defined and there is no fallback.
    """
    var_name: str | None = None
    fallback_start: int | None = None

    for i, tok in enumerate(arguments):
        if tok.type == "whitespace":
            continue
        if tok.type == "ident" and tok.value.startswith("--"):
            var_name = tok.value
        elif tok.type == "literal" and tok.value == ",":
            fallback_start = i + 1
            break

    if var_name and var_name in custom_props:
        sub_tokens = [
            t for t in tinycss2.parse_component_value_list(custom_props[var_name])
            if t.type != "whitespace"
        ]
        return _resolve_var_tokens(sub_tokens, custom_props, depth + 1)

    if fallback_start is not None:
        return _resolve_var_tokens(arguments[fallback_start:], custom_props, depth + 1)

    return None  # unresolvable — caller must skip the property


def _resolve_var_tokens(
    tokens: list, custom_props: dict[str, str], depth: int = 0
) -> list | None:
    """Walk *tokens*, recursively resolving every ``var()`` call.

    Returns the resolved token list, or ``None`` if any ``var()`` is
    unresolvable (so the caller can skip the whole property).
    """
    if depth > _MAX_VAR_DEPTH:
        return None  # guard against cycles or very deep chains

    result: list = []
    for token in tokens:
        if token.type == "function" and token.lower_name == "var":
            resolved = _resolve_var_call(token.arguments, custom_props, depth)
            if resolved is None:
                return None
            result.extend(resolved)
        else:
            result.append(token)
    return result


def _parse_declarations(
    content: list[object], custom_props: dict[str, str] | None = None
) -> dict[str, str]:
    """Extract whitelisted property→value pairs from a rule's content tokens."""
    result: dict[str, str] = {}
    decls = tinycss2.parse_blocks_contents(content, skip_whitespace=True)
    for decl in decls:
        if decl.type != "declaration":
            continue
        name: str = decl.name.lower()
        if name not in _ALLOWED_PROPS:
            continue
        value_tokens = list(decl.value)
        if custom_props is not None:
            resolved = _resolve_var_tokens(value_tokens, custom_props)
            if resolved is None:
                continue  # unresolvable var — skip property
            value_tokens = resolved
        value: str = tinycss2.serialize(value_tokens).strip()
        if value:
            result[name] = value
    return result


def _selector_category(selector: str) -> str | None:
    """Map a CSS selector string to one of: 'th', 'td', 'h1'–'h6', 'code', or None."""
    sel = selector.strip().lower()

    # Skip anything with pseudo-classes/elements or @-rules
    if ":" in sel or "@" in sel:
        return None

    # Skip ``pre code`` — that's a code block, not inline
    if re.search(r"\bpre\b.*\bcode\b", sel):
        return None

    # The last simple selector token (after any combinators/spaces)
    last = re.split(r"[\s>+~]+", sel)[-1]
    # Strip class/id/attribute suffixes to get the element name
    tag = re.split(r"[.#\[]", last)[0]

    if tag == "th":
        return "th"
    if tag == "td":
        return "td"
    if tag in _HEADING_TAGS:
        return tag
    if tag == "code":
        return "code"
    return None


def _merge(base: dict[str, str], additions: dict[str, str]) -> dict[str, str]:
    """Return base updated with additions (later rule wins, as in CSS)."""
    merged = dict(base)
    merged.update(additions)
    return merged


def load_extra_styles(docs_dir: Path, extra_css: list[str]) -> ExtraStyles:
    """Parse *extra_css* files and return an :class:`ExtraStyles` instance.

    Args:
        docs_dir: Absolute path to the MkDocs ``docs_dir``.
        extra_css: List of paths/URLs from the ``extra_css:`` key in mkdocs.yml.
                   Relative paths are resolved against *docs_dir*.
                   HTTP(S) URLs are silently skipped.

    Returns:
        An :class:`ExtraStyles` populated with whitelisted properties, or an
        empty instance if nothing applicable was found.
    """
    styles = ExtraStyles()

    for entry in extra_css:
        if _URL_RE.match(entry):
            continue  # external stylesheet — skip

        css_path = (docs_dir / entry).resolve()
        if not css_path.exists():
            continue

        css_text = css_path.read_text(encoding="utf-8")

        # First pass: collect custom properties for var() resolution
        custom_props = _collect_custom_props(css_text)

        rules = tinycss2.parse_stylesheet(css_text, skip_comments=True, skip_whitespace=True)

        for rule in rules:
            if rule.type != "qualified-rule":
                continue  # skip @media, @keyframes, etc.

            selector = tinycss2.serialize(rule.prelude).strip()
            # A single rule can have a comma-separated selector list
            for sel in selector.split(","):
                cat = _selector_category(sel)
                if cat is None:
                    continue

                props = _parse_declarations(rule.content, custom_props)
                if not props:
                    continue

                if cat == "th":
                    styles.th = _merge(styles.th, props)
                elif cat == "td":
                    styles.td = _merge(styles.td, props)
                elif cat == "code":
                    styles.code_inline = _merge(styles.code_inline, props)
                elif cat in _HEADING_TAGS:
                    existing = styles.headings.get(cat, {})
                    styles.headings[cat] = _merge(existing, props)

    return styles


def styles_to_attr(props: dict[str, str]) -> str:
    """Render a property dict as an inline ``style="..."`` attribute string.

    Returns an empty string when *props* is empty.
    """
    if not props:
        return ""
    inline = "; ".join(f"{k}: {v}" for k, v in props.items())
    return f' style="{inline}"'
