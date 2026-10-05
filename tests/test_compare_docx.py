"""Tests for the compare Word redline export (compare --format docx)."""

import io
import os
import re
import subprocess
import sys
import zipfile
from html import unescape
from pathlib import Path

from docx import Document

from redline.compare import compare_contracts
from redline.playbook import bundled_playbook_path, load_playbook
from redline.redline_docx import render_compare_docx

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = load_playbook(bundled_playbook_path("saas-vendor"))


def _comparison():
    old = (ROOT / "examples" / "compare-round1.md").read_text(encoding="utf-8")
    new = (ROOT / "examples" / "compare-round2.md").read_text(encoding="utf-8")
    cmp = compare_contracts("compare-round1.md", "compare-round2.md", old, new, PLAYBOOK)
    return cmp, new


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


def test_compare_docx_sections_present():
    cmp, new = _comparison()
    assert cmp.gained and cmp.resolved and cmp.changes  # fixture sanity
    xml = _document_xml(render_compare_docx(cmp, new, len(PLAYBOOK.rules)))
    for needle in (
        "Redline compare: compare-round1.md → compare-round2.md",
        "Risk:",
        "Round redline — new and reworded flags",
        "Concessions won — resolved flags",
        "Text changes",
        "Findings summary — new draft",
    ):
        assert needle in xml, needle


def test_compare_docx_marks_gained_flags_as_tracked_changes():
    cmp, new = _comparison()
    xml = _document_xml(render_compare_docx(cmp, new, len(PLAYBOOK.rules)))
    assert "<w:del " in xml and "<w:ins " in xml
    inss = _norm(_region_text(xml, "ins"))
    for finding in cmp.gained:
        fallback = _norm(finding.fallback or finding.suggestion)
        assert fallback and fallback in inss, finding.rule_id


def test_compare_docx_lists_resolved_flags():
    cmp, new = _comparison()
    xml = _document_xml(render_compare_docx(cmp, new, len(PLAYBOOK.rules)))
    for finding in cmp.resolved:
        assert finding.title in xml, finding.rule_id


def test_compare_docx_marks_text_changes():
    cmp, new = _comparison()
    xml = _document_xml(render_compare_docx(cmp, new, len(PLAYBOOK.rules)))
    kinds = {c.kind for c in cmp.changes}
    assert kinds  # fixture sanity
    for kind in kinds:
        assert f"[{kind}]" in xml, kind


def test_compare_docx_no_changes_renders_cleanly():
    text = (ROOT / "examples" / "compare-round1.md").read_text(encoding="utf-8")
    cmp = compare_contracts("a.md", "b.md", text, text, PLAYBOOK)
    assert not cmp.gained and not cmp.resolved and not cmp.changes
    data = render_compare_docx(cmp, text, len(PLAYBOOK.rules))
    xml = _document_xml(data)
    assert "no finding changes" in xml
    assert "<w:del " not in xml and "<w:ins " not in xml
    Document(io.BytesIO(data))


def test_cli_compare_docx_writes_file(tmp_path):
    proc = run_cli(
        "compare",
        str(ROOT / "examples" / "compare-round1.md"),
        str(ROOT / "examples" / "compare-round2.md"),
        "--format",
        "docx",
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "compare-round1-vs-compare-round2.redline.docx"
    assert out.exists(), proc.stdout
    assert f"wrote {out}" in proc.stdout
    xml = _document_xml(out.read_bytes())
    assert "Concessions won" in xml


def test_cli_compare_docx_respects_fail_on_gain(tmp_path):
    proc = run_cli(
        "compare",
        str(ROOT / "examples" / "compare-round1.md"),
        str(ROOT / "examples" / "compare-round2.md"),
        "--format",
        "docx",
        "--fail-on-gain",
        "low",
        cwd=tmp_path,
    )
    assert proc.returncode == 1  # medium auto-renewal gained
    assert (tmp_path / "compare-round1-vs-compare-round2.redline.docx").exists()
