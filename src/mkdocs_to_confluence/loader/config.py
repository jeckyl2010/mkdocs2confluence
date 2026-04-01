"""Load and validate mkdocs.yml into a typed MkDocsConfig."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """Raised when mkdocs.yml is missing required fields or is malformed."""


@dataclass(frozen=True)
class MkDocsConfig:
    """Typed representation of the fields we consume from mkdocs.yml."""

    site_name: str
    docs_dir: Path       # absolute path to the docs directory
    repo_url: str | None
    nav: list            # raw nav structure from YAML; traversed by nav.py


_REPO_URL_RE = re.compile(r"^https?://")


def load_config(mkdocs_yml: Path) -> MkDocsConfig:
    """Parse *mkdocs_yml* and return a validated :class:`MkDocsConfig`.

    Args:
        mkdocs_yml: Absolute (or CWD-relative) path to ``mkdocs.yml``.

    Raises:
        FileNotFoundError: If *mkdocs_yml* does not exist.
        ConfigError: If required fields are absent or have invalid values.
    """
    mkdocs_yml = Path(mkdocs_yml).resolve()

    if not mkdocs_yml.exists():
        raise FileNotFoundError(f"mkdocs.yml not found: {mkdocs_yml}")

    with mkdocs_yml.open(encoding="utf-8") as fh:
        raw: object = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ConfigError("mkdocs.yml must be a YAML mapping at the top level.")

    # --- site_name ---
    site_name = raw.get("site_name")
    if not isinstance(site_name, str) or not site_name.strip():
        raise ConfigError("mkdocs.yml: 'site_name' is required and must be a non-empty string.")

    # --- nav ---
    nav = raw.get("nav")
    if not isinstance(nav, list) or len(nav) == 0:
        raise ConfigError("mkdocs.yml: 'nav' is required and must be a non-empty list.")

    # --- docs_dir (optional; defaults to 'docs' relative to mkdocs.yml) ---
    raw_docs_dir = raw.get("docs_dir", "docs")
    if not isinstance(raw_docs_dir, str):
        raise ConfigError("mkdocs.yml: 'docs_dir' must be a string.")
    docs_dir = (mkdocs_yml.parent / raw_docs_dir).resolve()

    # --- repo_url (optional) ---
    repo_url: str | None = raw.get("repo_url")
    if repo_url is not None:
        if not isinstance(repo_url, str) or not _REPO_URL_RE.match(repo_url):
            raise ConfigError(
                "mkdocs.yml: 'repo_url' must be an http/https URL when provided."
            )

    return MkDocsConfig(
        site_name=site_name.strip(),
        docs_dir=docs_dir,
        repo_url=repo_url,
        nav=nav,
    )
