"""Tests for the opt-in OCR path (`redline review --ocr`)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from redline import ingest
from redline.ingest import IngestionError, extract_text

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCANNED = ROOT / "tests" / "fixtures" / "scanned-msa.pdf"

TESSERACT = shutil.which("tesseract") is not None
needs_tesseract = pytest.mark.skipif(not TESSERACT, reason="tesseract not installed")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_scanned_pdf_rejected_without_ocr_points_to_flag():
    with pytest.raises(IngestionError, match="--ocr"):
        extract_text(SCANNED)


def test_ocr_missing_binary_gives_clear_error(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(IngestionError, match="tesseract"):
        extract_text(SCANNED, ocr=True)


def test_ocr_fills_blank_pages(monkeypatch):
    monkeypatch.setattr(
        ingest, "_ocr_pdf_page", lambda path, page_num: f"canned ocr text page {page_num}"
    )
    text = extract_text(SCANNED, ocr=True)
    assert "canned ocr text page 1" in text


def test_ocr_keeps_readable_pages_untouched(monkeypatch):
    calls = []

    def fake_ocr(path, page_num):
        calls.append(page_num)
        return "ocr text"

    monkeypatch.setattr(ingest, "_ocr_pdf_page", fake_ocr)
    text = extract_text(ROOT / "examples" / "sample-msa.pdf", ocr=True)
    assert calls == [], "OCR must not run on pages that already have text"
    assert "Indemnification" in text


@needs_tesseract
def test_ocr_end_to_end_on_scanned_fixture():
    text = extract_text(SCANNED, ocr=True)
    assert len(text) > 200
    # sample-msa content should survive a round trip through raster + OCR
    assert "Indemnification" in text


def test_cli_ocr_flag_without_binary_errors_clearly():
    if TESSERACT:
        pytest.skip("tesseract is installed; covered by the e2e test")
    proc = run_cli("review", str(SCANNED), "--ocr")
    assert proc.returncode == 2
    assert "tesseract" in proc.stderr
