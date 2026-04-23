"""Load and validate mkdocs.yml into a typed MkDocsConfig."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when mkdocs.yml is missing required fields or is malformed."""


@dataclass(frozen=True)
class ConfluenceConfig:
    """Confluence Cloud connection settings, parsed from the ``confluence:`` block."""

    base_url: str           # https://yourorg.atlassian.net or https://yourorg.atlassian.net/wiki
    email: str              # Basic auth user email
    token: str              # API token (may be empty — callers check truthiness)
    space_key: str | None = None          # e.g. "TECH" — optional if parent_page_id given
    parent_page_id: str | None = None  # optional root parent page
    full_width: bool = True  # set full-width layout on every published page
    nav_file: str = ".pages"  # awesome-pages filename (default: .pages, can be .nav etc.)


@dataclass(frozen=True)
class MkDocsConfig:
    """Typed representation of the fields we consume from mkdocs.yml."""

    site_name: str
    docs_dir: Path       # absolute path to the docs directory
    repo_url: str | None
    edit_uri: str | None  # e.g. "edit/main/docs/" — None means no edit link
    nav: list[Any] | None     # raw nav structure from YAML; None when using auto-nav plugins
    site_url: str | None = None  # e.g. "https://example.github.io/" — None means no published-page link
    confluence: ConfluenceConfig | None = None

    def page_edit_url(self, docs_path: str) -> str | None:
        """Return the full edit URL for *docs_path*, or ``None`` if not configured."""
        if not self.edit_uri:
            return None
        # Absolute edit_uri (e.g. a GitLab instance with custom domain)
        if self.edit_uri.startswith(("http://", "https://")):
            return self.edit_uri.rstrip("/") + "/" + docs_path
        # Relative edit_uri — prepend repo_url
        if not self.repo_url:
            return None
        return self.repo_url.rstrip("/") + "/" + self.edit_uri.rstrip("/") + "/" + docs_path

    def page_site_url(self, docs_path: str) -> str | None:
        """Return the rendered MkDocs URL for *docs_path*, or ``None`` if not configured.

        Converts e.g. ``guide/installation.md`` →
        ``https://example.github.io/guide/installation/`` following MkDocs'
        default ``use_directory_urls`` behaviour.
        """
        if not self.site_url:
            return None
        # Strip .md, collapse index pages, add trailing slash
        path = docs_path
        if path.endswith(".md"):
            path = path[:-3]
        # index pages collapse to their parent directory
        if path.endswith("/index") or path == "index":
            path = path[: -len("index")].rstrip("/")
        return self.site_url.rstrip("/") + "/" + path.lstrip("/") + ("/" if path else "")


_REPO_URL_RE = re.compile(r"^https?://")


def _make_env_loader() -> type[yaml.SafeLoader]:
    """Return a SafeLoader subclass that handles MkDocs ``!ENV`` tags.

    ``!ENV VAR_NAME`` and ``!ENV [VAR_NAME, default]`` are resolved against
    the process environment.  Unknown variables resolve to ``None`` (or the
    supplied default) so the loader never crashes on missing env vars.
    """
    class _Loader(yaml.SafeLoader):
        pass

    def _env_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> str | None:
        # Scalar form:  !ENV MY_VAR  or  !ENV "MY_VAR default_value"
        if isinstance(node, yaml.ScalarNode):
            parts = loader.construct_scalar(node).split()
            var = parts[0]
            default = parts[1] if len(parts) > 1 else None
            return os.environ.get(var, default)
        # Sequence form:  !ENV [MY_VAR, default]
        if isinstance(node, yaml.SequenceNode):
            items = loader.construct_sequence(node)
            var = str(items[0]) if items else ""
            default = str(items[1]) if len(items) > 1 else None
            return os.environ.get(var, default)
        return None

    _Loader.add_constructor("!ENV", _env_constructor)

    # Catch-all: any other unknown tag (e.g. !!python/name:... used by
    # MkDocs Material) is silently ignored — we only care about nav/site_name.
    def _ignore(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> None:
        return None

    _Loader.add_multi_constructor("", _ignore)  # type: ignore[no-untyped-call]
    return _Loader


def _default_edit_uri(repo_url: str | None) -> str | None:
    """Return a sensible default ``edit_uri`` based on the hosting platform."""
    if not repo_url:
        return None
    if "github.com" in repo_url:
        return "edit/main/docs/"
    if "gitlab.com" in repo_url or "gitlab." in repo_url:
        return "-/edit/master/docs/"
    return None


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
        raw: object = yaml.load(fh, Loader=_make_env_loader())

    if not isinstance(raw, dict):
        raise ConfigError("mkdocs.yml must be a YAML mapping at the top level.")

    # --- site_name ---
    site_name = raw.get("site_name")
    if not isinstance(site_name, str) or not site_name.strip():
        raise ConfigError("mkdocs.yml: 'site_name' is required and must be a non-empty string.")

    # --- nav (optional — some projects use awesome-pages or literate-nav plugins) ---
    nav = raw.get("nav")
    if nav is not None and (not isinstance(nav, list) or len(nav) == 0):
        raise ConfigError("mkdocs.yml: 'nav' must be a non-empty list when present.")

    # --- docs_dir (optional; defaults to 'docs' relative to mkdocs.yml) ---
    raw_docs_dir = raw.get("docs_dir", "docs")
    if not isinstance(raw_docs_dir, str):
        raise ConfigError("mkdocs.yml: 'docs_dir' must be a string.")
    docs_dir = (mkdocs_yml.parent / raw_docs_dir).resolve()

    # --- site_url (optional) ---
    raw_site_url = raw.get("site_url")
    site_url: str | None = str(raw_site_url).rstrip("/") + "/" if isinstance(raw_site_url, str) and raw_site_url.strip() else None

    # --- repo_url (optional) ---
    repo_url: str | None = raw.get("repo_url")
    if repo_url is not None:
        if not isinstance(repo_url, str) or not _REPO_URL_RE.match(repo_url):
            raise ConfigError(
                "mkdocs.yml: 'repo_url' must be an http/https URL when provided."
            )

    # --- edit_uri (optional; sensible defaults for GitHub/GitLab) ---
    _raw_edit_uri = raw.get("edit_uri", _default_edit_uri(repo_url))
    if _raw_edit_uri is not None and not isinstance(_raw_edit_uri, str):
        raise ConfigError("mkdocs.yml: 'edit_uri' must be a string when provided.")
    edit_uri: str | None = _raw_edit_uri or None

    # --- confluence (optional) ---
    # Supports two locations:
    #   confluence:          (top-level, simpler but rejected by MkDocs --strict)
    #   extra.confluence:    (under extra:, accepted by MkDocs in any mode)
    # Top-level takes precedence when both are present.
    confluence: ConfluenceConfig | None = None
    raw_conf = raw.get("confluence")
    if raw_conf is None:
        extra = raw.get("extra")
        if isinstance(extra, dict):
            raw_conf = extra.get("confluence")
    if raw_conf is not None:
        if not isinstance(raw_conf, dict):
            raise ConfigError("mkdocs.yml: 'confluence' must be a mapping when present.")

        base_url = raw_conf.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ConfigError("mkdocs.yml: 'confluence.base_url' is required and must be a non-empty string.")

        space_key: str | None = raw_conf.get("space_key") or None
        if space_key:
            space_key = space_key.strip() or None

        parent_page_id: str | None = None
        raw_parent = raw_conf.get("parent_page_id")
        if raw_parent is not None:
            parent_page_id = str(raw_parent)

        if not space_key and not parent_page_id:
            raise ConfigError(
                "mkdocs.yml: 'confluence.space_key' or 'confluence.parent_page_id' is required. "
                "Provide at least one so the publisher can locate the target space."
            )

        email = raw_conf.get("email")
        if not isinstance(email, str) or not email.strip():
            raise ConfigError("mkdocs.yml: 'confluence.email' is required and must be a non-empty string.")

        # Token lookup order: YAML value → CONFLUENCE_API_TOKEN env → MK2CONF_TOKEN env
        token: str = raw_conf.get("token") or ""
        if not token:
            token = os.environ.get("CONFLUENCE_API_TOKEN", "")
        if not token:
            token = os.environ.get("MK2CONF_TOKEN", "")

        confluence = ConfluenceConfig(
            base_url=base_url.rstrip("/"),
            space_key=space_key,
            email=email.strip(),
            token=token,
            parent_page_id=parent_page_id,
            full_width=bool(raw_conf.get("full_width", True)),
            nav_file=str(raw_conf.get("nav_file", ".pages")),
        )

    return MkDocsConfig(
        site_name=site_name.strip(),
        docs_dir=docs_dir,
        repo_url=repo_url,
        edit_uri=edit_uri,
        site_url=site_url,
        nav=nav,
        confluence=confluence,
    )
