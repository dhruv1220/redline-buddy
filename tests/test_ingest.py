from pathlib import Path

import pytest

from redline.ingest import IngestionError, extract_text
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "examples" / "sample-msa.pdf"
MD = ROOT / "examples" / "sample-msa.md"
PLAYBOOK = bundled_playbook_path("saas-vendor")


def _blank_pdf(path: Path) -> None:
    """A 'scanned' PDF: valid file, no text layer."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as f:
        writer.write(f)


def test_pdf_review_matches_markdown_review():
    """The headline guarantee: same contract, same findings, whatever the format."""
    playbook = load_playbook(PLAYBOOK)
    from_md = [f.rule_id for f in review_contract(MD.read_text(), playbook)]
    from_pdf = [f.rule_id for f in review_contract(extract_text(PDF), playbook)]
    assert from_pdf == from_md
    assert from_pdf  # the sample is deliberately risky


def test_pdf_extracts_readable_text():
    text = extract_text(PDF)
    assert "MASTER SERVICES AGREEMENT" in text
    assert "automatically renew" in text


def test_scanned_pdf_rejected_with_clear_message(tmp_path):
    scanned = tmp_path / "scan.pdf"
    _blank_pdf(scanned)
    with pytest.raises(IngestionError, match="scanned"):
        extract_text(scanned)


def test_corrupt_pdf_rejected(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not a real pdf")
    with pytest.raises(IngestionError):
        extract_text(bad)


def test_unsupported_suffix_rejected(tmp_path):
    rtf = tmp_path / "contract.rtf"
    rtf.write_text("{\\rtf1 hello}")
    with pytest.raises(IngestionError, match="unsupported"):
        extract_text(rtf)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(IngestionError, match="not found"):
        extract_text(tmp_path / "nope.pdf")


def test_docx_tables_are_extracted():
    text = extract_text(ROOT / "tests" / "fixtures" / "sow-table.docx")
    assert "Milestone | Fee" in text
    assert "Design | $5,000" in text
    # table content feeds the rule engine: payment terms now detected
    playbook = load_playbook(bundled_playbook_path("client-sow"))
    ids = {f.rule_id for f in review_contract(text, playbook)}
    assert "payment-terms" not in ids
