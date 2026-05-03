"""Write a PDF file from combined HTML using WeasyPrint.

WeasyPrint is an optional dependency — install with::

    pip install mkdocs-to-confluence[pdf]
"""

from __future__ import annotations

from pathlib import Path


def write_pdf(html: str, out_path: Path) -> None:
    """Render *html* to a PDF file at *out_path*.

    Raises
    ------
    ImportError
        If WeasyPrint is not installed.
    """
    try:
        import weasyprint
    except ImportError as exc:
        raise ImportError(
            "PDF export requires WeasyPrint.\n"
            "Install it with:  pip install mkdocs-to-confluence[pdf]\n"
            "System packages also required (pango, cairo):\n"
            "  macOS:  brew install pango\n"
            "  Ubuntu: apt install libpango-1.0-0 libpangoft2-1.0-0"
        ) from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(str(out_path))
