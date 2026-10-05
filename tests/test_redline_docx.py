"""Tests for the Word redline export (redline.redline_docx, --format docx)."""

import io
import os
import re
import subprocess
import sys
import zipfile
from html import unescape
from pathlib import Path

from docx import Document

from redline.playbook import bundled_playbook_path, load_playbook
from redline.redline_docx import _plan_edits, render_redline_docx
from redline.review import Finding, review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = load_playbook(bundled_playbook_path("saas-vendor"))


def _review_sample() -> tuple[str, list[Finding]]:
    text = (ROOT / "examples" / "sample-msa.md").read_text(encoding="utf-8")
    return text, review_contract(text, PLAYBOOK)


def _document_xml(data: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")


def _region_text(xml: str, tag: str) -> str:
    parts = re.findall(rf"<w:{tag} .*?</w:{tag}>", xml, re.S)
    return unescape(re.sub(r"<[^>]+>", "", " ".join(parts)))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        cwd=cwd,
    )


# --- tracked-change markup -------------------------------------------------


def test_tracked_changes_markup_present():
    text, findings = _review_sample()
    assert findings, "sample contract should produce findings"
    xml = _document_xml(render_redline_docx("sample-msa.md", text, "saas-vendor", findings, 8))
    assert "<w:del " in xml
    assert "<w:ins " in xml
    assert 'w:author="redline-buddy"' in xml
    assert re.search(r'w:date="\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"', xml)


def test_located_excerpts_struck_and_fallbacks_inserted():
    text, findings = _review_sample()
    edits, additions, _ = _plan_edits(text, findings)
    assert edits, "expected at least one inline edit"
    xml = _document_xml(render_redline_docx("sample-msa.md", text, "saas-vendor", findings, 8))
    dels = _norm(_region_text(xml, "del"))
    inss = _norm(_region_text(xml, "ins"))
    for start, end, finding in edits:
        assert _norm(text[start:end]) in dels, finding.rule_id
        fallback = _norm(finding.fallback or finding.suggestion)
        assert fallback and fallback in inss, finding.rule_id


def test_missing_clause_findings_become_proposed_additions():
    missing = Finding(
        rule_id="liability-cap",
        title="No limitation of liability",
        severity="high",
        excerpt="",
        why="Uncapped liability is dangerous.",
        suggestion="",
        fallback="Liability is capped at fees paid in the prior 12 months.",
    )
    xml = _document_xml(render_redline_docx("c.md", "Some contract text.", "saas-vendor", [missing], 8))
    assert "Proposed additions" in xml
    assert "Liability is capped at fees paid" in _region_text(xml, "ins")
    assert "<w:del " not in xml


def test_unlocatable_excerpt_does_not_break_render():
    ghost = Finding(
        rule_id="ghost",
        title="Ghost clause",
        severity="medium",
        excerpt="…this exact phrase appears nowhere in the contract…",
        why="because",
        suggestion="",
        fallback="Replace it.",
    )
    data = render_redline_docx("c.md", "Some contract text.", "saas-vendor", [ghost], 8)
    xml = _document_xml(data)
    assert "Ghost clause" in xml  # still in the summary table
    Document(io.BytesIO(data))  # reopens cleanly


def test_overlapping_findings_keep_first_only():
    text = "The vendor may terminate this agreement at any time for any reason."
    findings = [
        Finding("a", "First", "high", "…terminate this agreement…", "why", "", "Fallback A."),
        Finding("b", "Second", "high", "…terminate this agreement at any time…", "why", "", "Fallback B."),
    ]
    edits, _, orphans = _plan_edits(text, findings)
    assert [f.rule_id for _, _, f in edits] == ["a"]
    assert [f.rule_id for f in orphans] == ["b"]
    xml = _document_xml(render_redline_docx("c.md", text, "pb", findings, 2))
    assert "Fallback A." in _region_text(xml, "ins")
    assert "Fallback B." not in _region_text(xml, "ins")


def test_no_findings_renders_cleanly():
    data = render_redline_docx("clean.md", "A perfectly fine contract.", "saas-vendor", [], 8)
    xml = _document_xml(data)
    assert "No red flags" in xml
    assert "<w:del " not in xml
    assert "<w:ins " not in xml
    Document(io.BytesIO(data))


def test_full_contract_text_preserved():
    text, findings = _review_sample()
    xml = _document_xml(render_redline_docx("sample-msa.md", text, "saas-vendor", findings, 8))
    body = _norm(unescape(re.sub(r"<[^>]+>", " ", xml)))
    for word in ["Agreement", "Vendor", "Customer"]:
        assert word in body


# --- CLI -------------------------------------------------------------------


def test_cli_docx_writes_file(tmp_path):
    proc = run_cli(
        "review",
        str(ROOT / "examples" / "sample-nda.md"),
        "--playbook",
        "nda-recipient",
        "--format",
        "docx",
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "sample-nda.redline.docx"
    assert out.exists(), proc.stdout
    assert f"wrote {out}" in proc.stdout
    xml = _document_xml(out.read_bytes())
    assert "<w:del " in xml or "<w:ins " in xml


def test_cli_docx_batch_writes_one_file_per_contract(tmp_path):
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    for name in ("sample-nda.md", "sample-msa.md"):
        (contracts / name).write_bytes((ROOT / "examples" / name).read_bytes())
    proc = run_cli("review", str(contracts), "--format", "docx", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "sample-nda.redline.docx").exists()
    assert (tmp_path / "sample-msa.redline.docx").exists()


def test_cli_docx_respects_fail_on(tmp_path):
    proc = run_cli(
        "review",
        str(ROOT / "examples" / "sample-msa.md"),
        "--format",
        "docx",
        "--fail-on",
        "high",
        cwd=tmp_path,
    )
    assert proc.returncode == 1
    assert (tmp_path / "sample-msa.redline.docx").exists()
