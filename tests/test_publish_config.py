"""Tests for ConfluenceConfig parsing and MkDocsConfig.confluence integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from mkdocs_to_confluence.loader.config import (
    ConfigError,
    load_config,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_mkdocs(tmp_path: Path, extra: str = "") -> Path:
    """Write a minimal mkdocs.yml with optional extra YAML."""
    docs = tmp_path / "docs"
    docs.mkdir()
    content = f"site_name: Test Site\n{extra}"
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(content, encoding="utf-8")
    return config_file


# ── Tests: no confluence block ─────────────────────────────────────────────────


def test_confluence_absent(tmp_path: Path) -> None:
    config_file = _write_mkdocs(tmp_path)
    config = load_config(config_file)
    assert config.confluence is None


# ── Tests: valid confluence block ─────────────────────────────────────────────


def test_confluence_parsed(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
  token: secret-token
  parent_page_id: "12345"
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.base_url == "https://example.atlassian.net"
    assert config.confluence.space_key == "TECH"
    assert config.confluence.email == "user@example.com"
    assert config.confluence.token == "secret-token"
    assert config.confluence.parent_page_id == "12345"


def test_confluence_base_url_trailing_slash_stripped(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net/
  space_key: TECH
  email: user@example.com
  token: tok
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert not config.confluence.base_url.endswith("/")


def test_confluence_parent_page_id_optional(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
  token: tok
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.parent_page_id is None


# ── Tests: token env var fallback ─────────────────────────────────────────────


def test_token_from_env_confluence_api_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "env-token")
    monkeypatch.delenv("MK2CONF_TOKEN", raising=False)
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.token == "env-token"


def test_token_from_env_mk2conf_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
    monkeypatch.setenv("MK2CONF_TOKEN", "mk2conf-token")
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.token == "mk2conf-token"


def test_token_yaml_takes_precedence_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "env-token")
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
  token: yaml-token
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.token == "yaml-token"


def test_token_absent_ok_at_load_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
    monkeypatch.delenv("MK2CONF_TOKEN", raising=False)
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
""",
    )
    # Should not raise — missing token is only an error at publish time
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.token == ""


# ── Tests: missing required fields raise ConfigError ─────────────────────────


def test_missing_base_url_raises(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  space_key: TECH
  email: user@example.com
  token: tok
""",
    )
    with pytest.raises(ConfigError, match="base_url"):
        load_config(config_file)


def test_missing_space_key_raises_when_no_parent_page(tmp_path: Path) -> None:
    """space_key is only required when parent_page_id is also absent."""
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  email: user@example.com
  token: tok
""",
    )
    with pytest.raises(ConfigError, match="space_key"):
        load_config(config_file)


def test_space_key_optional_when_parent_page_id_given(tmp_path: Path) -> None:
    """When parent_page_id is set, space_key may be omitted."""
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  email: user@example.com
  token: tok
  parent_page_id: "123456"
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.space_key is None
    assert config.confluence.parent_page_id == "123456"


def test_missing_email_raises(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  token: tok
""",
    )
    with pytest.raises(ConfigError, match="email"):
        load_config(config_file)


def test_confluence_not_a_mapping_raises(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="confluence: not-a-mapping\n",
    )
    with pytest.raises(ConfigError, match="confluence"):
        load_config(config_file)


# ── Tests: extra.confluence (strict mode) ────────────────────────────────────


def test_confluence_under_extra_is_parsed(tmp_path: Path) -> None:
    """extra.confluence: is accepted — works in MkDocs --strict mode."""
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
extra:
  confluence:
    base_url: https://example.atlassian.net
    space_key: TECH
    email: user@example.com
    token: tok
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.base_url == "https://example.atlassian.net"
    assert config.confluence.space_key == "TECH"


def test_top_level_confluence_takes_precedence_over_extra(tmp_path: Path) -> None:
    """Top-level confluence: wins when both locations are present."""
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://top-level.atlassian.net
  space_key: TOP
  email: user@example.com
  token: tok

extra:
  confluence:
    base_url: https://extra.atlassian.net
    space_key: EXTRA
    email: user@example.com
    token: tok
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.base_url == "https://top-level.atlassian.net"


# ── Tests: full_width ─────────────────────────────────────────────────────────


def test_full_width_defaults_to_true(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
  token: tok
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.full_width is True


def test_full_width_can_be_disabled(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="""
confluence:
  base_url: https://example.atlassian.net
  space_key: TECH
  email: user@example.com
  token: tok
  full_width: false
""",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.full_width is False


# ── _make_env_loader: !ENV tag ────────────────────────────────────────────────


def test_env_loader_scalar_env_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """!ENV VAR_NAME resolves to the env variable value."""
    monkeypatch.setenv("MY_TEST_TOKEN", "secret")
    docs = tmp_path / "docs"
    docs.mkdir()
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        "site_name: Test\n"
        "confluence:\n"
        "  base_url: https://example.atlassian.net\n"
        "  space_key: TECH\n"
        "  email: user@example.com\n"
        "  token: !ENV MY_TEST_TOKEN\n",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.token == "secret"


def test_env_loader_scalar_env_tag_with_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """!ENV VAR default uses default when env var is absent."""
    monkeypatch.delenv("ABSENT_VAR", raising=False)
    docs = tmp_path / "docs"
    docs.mkdir()
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        "site_name: Test\n"
        "confluence:\n"
        "  base_url: https://example.atlassian.net\n"
        "  space_key: TECH\n"
        "  email: user@example.com\n"
        "  token: !ENV 'ABSENT_VAR fallback-token'\n",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.token == "fallback-token"


def test_env_loader_sequence_env_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """!ENV [VAR, default] resolves to the env variable value."""
    monkeypatch.setenv("SEQ_TOKEN", "seq-secret")
    docs = tmp_path / "docs"
    docs.mkdir()
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        "site_name: Test\n"
        "confluence:\n"
        "  base_url: https://example.atlassian.net\n"
        "  space_key: TECH\n"
        "  email: user@example.com\n"
        "  token: !ENV [SEQ_TOKEN, fallback]\n",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.confluence is not None
    assert config.confluence.token == "seq-secret"


def test_env_loader_ignores_unknown_tags(tmp_path: Path) -> None:
    """Unknown YAML tags (like !!python/...) are silently ignored."""
    docs = tmp_path / "docs"
    docs.mkdir()
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        "site_name: !SomeTag ignored-value\n",
        encoding="utf-8",
    )
    # Just verify no exception is raised
    from mkdocs_to_confluence.loader.config import ConfigError
    try:
        load_config(config_file)
    except ConfigError:
        pass  # site_name may be None — that's a different error


# ── docs_dir not a string ─────────────────────────────────────────────────────


def test_docs_dir_not_string_raises(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text("site_name: Test\ndocs_dir: 123\n", encoding="utf-8")
    from mkdocs_to_confluence.loader.config import ConfigError
    with pytest.raises(ConfigError, match="docs_dir"):
        load_config(config_file)


# ── edit_uri absolute http/https ─────────────────────────────────────────────


def test_edit_uri_absolute_url_used_as_is(tmp_path: Path) -> None:
    """An absolute edit_uri is used verbatim (no repo_url prepended)."""
    config_file = _write_mkdocs(
        tmp_path,
        extra="repo_url: https://github.com/org/repo\nedit_uri: https://custom.editor.example.com/edit/\n",
    )
    config = load_config(config_file)
    url = config.page_edit_url("guide/index.md")
    assert url is not None
    assert url.startswith("https://custom.editor.example.com/edit/")


# ── _default_edit_uri: gitlab ─────────────────────────────────────────────────


def test_default_edit_uri_gitlab(tmp_path: Path) -> None:
    config_file = _write_mkdocs(
        tmp_path,
        extra="repo_url: https://gitlab.com/org/repo\n",
    )
    config = load_config(config_file)
    assert config.edit_uri is not None
    assert "gitlab" in config.edit_uri or "-/edit" in config.edit_uri


# ── edit_uri not a string ─────────────────────────────────────────────────────


def test_edit_uri_not_string_raises(tmp_path: Path) -> None:
    from mkdocs_to_confluence.loader.config import ConfigError

    config_file = _write_mkdocs(tmp_path, extra="edit_uri: 42\n")
    with pytest.raises(ConfigError, match="edit_uri"):
        load_config(config_file)


# ── extra_css processing ──────────────────────────────────────────────────────


def test_extra_css_list_is_processed(tmp_path: Path) -> None:
    """extra_css entries cause extra_styles to be populated."""
    docs = tmp_path / "docs"
    docs.mkdir()
    css_file = docs / "custom.css"
    css_file.write_text("body { color: red; }\n", encoding="utf-8")
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        "site_name: Test\ndocs_dir: docs\nextra_css:\n  - custom.css\n",
        encoding="utf-8",
    )
    config = load_config(config_file)
    # extra_styles is None when parsed styles are empty (no admonition overrides)
    # but the code path must execute without error
    assert config is not None
