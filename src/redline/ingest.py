"""Contract ingestion: extract plain text from supported file formats.

Everything stays local — no network calls, no uploads. Supported inputs:

- ``.md`` / ``.txt`` — read as UTF-8 text
- ``.docx`` — text extracted with python-docx (paragraphs only)
- ``.pdf`` — text extracted page-by-page with pypdf

Scanned/image-only PDFs (no extractable text layer) are rejected with a clear
error instead of silently reviewing nothing.
"""
from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = (".md", ".txt", ".docx", ".pdf")


class IngestionError(ValueError):
    """The contract file could not be read or contains no usable text."""


def extract_text(path: str | Path) -> str:
    """Extract contract text from *path*. Raises IngestionError on failure."""
    p = Path(path)
    if not p.is_file():
        raise IngestionError(f"contract file not found: {p}")
    suffix = p.suffix.lower()
    if suffix in (".md", ".txt"):
        return _read_text_file(p)
    if suffix == ".docx":
        return _read_docx(p)
    if suffix == ".pdf":
        return _read_pdf(p)
    raise IngestionError(
        f"unsupported file type {p.suffix!r} — supported: {', '.join(SUPPORTED_SUFFIXES)}"
    )


def _read_text_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError(f"could not decode {p} as UTF-8: {exc}") from exc
    except OSError as exc:
        raise IngestionError(f"could not read {p}: {exc}") from exc


def _read_docx(p: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise IngestionError("reading .docx requires the 'python-docx' package") from exc
    try:
        doc = Document(str(p))
    except Exception as exc:
        raise IngestionError(f"could not parse Word document {p}: {exc}") from exc
    text = "\n".join(par.text for par in doc.paragraphs).strip()
    if not text:
        raise IngestionError(f"no text found in Word document: {p}")
    return text


def _read_pdf(p: Path) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise IngestionError("reading .pdf requires the 'pypdf' package") from exc
    try:
        reader = PdfReader(str(p))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise IngestionError(f"could not parse PDF {p}: {exc}") from exc
    except Exception as exc:
        raise IngestionError(f"could not read PDF {p}: {exc}") from exc
    blank_pages = [i + 1 for i, t in enumerate(pages) if not t.strip()]
    text = "\n\n".join(t.strip() for t in pages if t.strip())
    if not text:
        raise IngestionError(
            f"no extractable text in PDF {p} — it appears to be a scanned/image-only "
            "document; OCR is not supported yet"
        )
    # Blank pages inside an otherwise readable PDF are worth knowing about:
    # a scanned exhibit or signature page would silently drop its content.
    if blank_pages:
        marker = (
            f"\n\n[redline note: no text extracted from PDF page(s) "
            f"{', '.join(map(str, blank_pages))} — page may be scanned]"
        )
        text += marker
    return text
