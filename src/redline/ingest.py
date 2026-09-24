"""Contract ingestion: extract plain text from supported file formats.

Everything stays local — no network calls, no uploads. Supported inputs:

- ``.md`` / ``.txt`` — read as UTF-8 text
- ``.docx`` — text extracted with python-docx (paragraphs only)
- ``.pdf`` — text extracted page-by-page with pypdf

Scanned/image-only PDFs (no extractable text layer) are rejected with a clear
error instead of silently reviewing nothing. Pass ``ocr=True`` (``redline
review --ocr``) to run those pages through Tesseract OCR instead — requires
the ``tesseract`` and ``pdftoppm`` system binaries, no extra Python packages.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

SUPPORTED_SUFFIXES = (".md", ".txt", ".docx", ".pdf")


class IngestionError(ValueError):
    """The contract file could not be read or contains no usable text."""


def extract_text(path: str | Path, *, ocr: bool = False) -> str:
    """Extract contract text from *path*. Raises IngestionError on failure.

    With ``ocr=True``, PDF pages that have no extractable text layer are run
    through Tesseract OCR (requires the ``tesseract`` and ``pdftoppm``
    binaries on PATH).
    """
    p = Path(path)
    if not p.is_file():
        raise IngestionError(f"contract file not found: {p}")
    suffix = p.suffix.lower()
    if suffix in (".md", ".txt"):
        return _read_text_file(p)
    if suffix == ".docx":
        return _read_docx(p)
    if suffix == ".pdf":
        return _read_pdf(p, ocr=ocr)
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


def _ocr_pdf_page(p: Path, page_num: int) -> str:
    """OCR a single 1-based PDF page via pdftoppm + tesseract (both on PATH)."""
    missing = [b for b in ("pdftoppm", "tesseract") if shutil.which(b) is None]
    if missing:
        raise IngestionError(
            f"OCR requested but missing system bina{'ry' if len(missing) == 1 else 'ries'}: "
            f"{', '.join(missing)} — install tesseract-ocr and poppler-utils, or "
            "review a text-based PDF instead"
        )
    with tempfile.TemporaryDirectory(prefix="redline-ocr-") as tmp:
        prefix = str(Path(tmp) / "page")
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", "200", "-f", str(page_num), "-l", str(page_num),
                 str(p), prefix],
                check=True, capture_output=True, timeout=120,
            )
            img = f"{prefix}-{page_num}.png"
            proc = subprocess.run(
                ["tesseract", img, "stdout", "-l", "eng"],
                check=True, capture_output=True, text=True, timeout=180,
            )
        except subprocess.CalledProcessError as exc:
            raise IngestionError(f"OCR failed on {p} page {page_num}: {exc.stderr[:200]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise IngestionError(f"OCR timed out on {p} page {page_num}") from exc
    return proc.stdout.strip()


def _read_pdf(p: Path, *, ocr: bool = False) -> str:
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
    if ocr and blank_pages:
        # Fill text-less pages via OCR; keep page order intact.
        pages = [
            _ocr_pdf_page(p, i + 1) if not t.strip() else t
            for i, t in enumerate(pages)
        ]
        blank_pages = [i + 1 for i, t in enumerate(pages) if not t.strip()]
    text = "\n\n".join(t.strip() for t in pages if t.strip())
    if not text:
        hint = (
            " — retry with --ocr to run scanned pages through Tesseract"
            if not ocr else " even after OCR"
        )
        raise IngestionError(
            f"no extractable text in PDF {p} — it appears to be a scanned/image-only "
            f"document{hint}"
        )
    # Blank pages inside an otherwise readable PDF are worth knowing about:
    # a scanned exhibit or signature page would silently drop its content.
    if blank_pages:
        marker = (
            f"\n\n[redline note: no text extracted from PDF page(s) "
            f"{', '.join(map(str, blank_pages))} — page may be scanned"
            + ("; OCR found no text either" if ocr else "; retry with --ocr") + "]"
        )
        text += marker
    return text
