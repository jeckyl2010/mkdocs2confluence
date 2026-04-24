"""mkdocs-to-confluence: compile MkDocs markdown to Confluence storage format."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mkdocs-to-confluence")
except PackageNotFoundError:
    __version__ = "unknown"
