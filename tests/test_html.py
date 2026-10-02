"""Tests for the shareable HTML memo export (redline.html)."""

import subprocess
import sys
import tempfile
from pathlib import Path

from redline.html import render_batch_html_memo, render_html_memo
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import Finding, review_contract

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK = load_playbook(bundled_playbook_path("term-sheet"))


def _findings() -> list[Finding]:
    text = (ROOT / "examples" / "sample-term-sheet.md").read_text(encoding="utf-8")
    return review_contract(text, PLAYBOOK)


# --- escaping --------------------------------------------------------------


def test_contract_markup_is_escaped():
    hostile = Finding(
        rule_id="x",
        title="Evil <b>title</b>",
        severity="high",
        excerpt='<script>alert("pwn")</script>',
        why="why with <img src=x onerror=alert(1)> inside",
        suggestion="",
        fallback="Replace with <blink>safe</blink> text.",
    )
    out = render_html_memo("contract.md", "term-sheet", [hostile], 8)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;img" in out
    assert "&lt;blink&gt;" in out


def test_playbook_and_contract_names_are_escaped():
    out = render_html_memo('evil"><svg onload=x>.md', 'pb"><b>.md', [], 8)
    assert '"><svg' not in out
    assert "&quot;&gt;&lt;svg" in out


# --- structure -------------------------------------------------------------


def test_standalone_document_shape():
    out = render_html_memo("c.md", "term-sheet", _findings(), 8)
    assert out.startswith("<!doctype html>")
    assert out.rstrip().endswith("</html>")
    assert "<style>" in out
    assert "<script" not in out  # zero JS by design
    assert out.count("Not legal advice") >= 2  # disclaimer box + footer


def test_risk_banner_matches_score():
    findings = _findings()
    out = render_html_memo("c.md", "term-sheet", findings, 8)
    from redline.score import risk_grade, risk_score

    score, grade = risk_score(findings), risk_grade(risk_score(findings))
    assert f"Risk score: <b>{score}/100</b>" in out
    assert f"Grade {grade}" in out
    assert f'class="risk r{grade}"' in out


def test_findings_render_with_badges_and_fallbacks():
    findings = _findings()
    out = render_html_memo("c.md", "term-sheet", findings, 8)
    assert out.count('class="finding"') == len(findings)
    assert "sev-high" in out
    assert "Discount with no valuation cap" in out
    assert out.count('class="fallback"') >= 1
    assert "Rule <code>" in out


def test_no_findings_state():
    out = render_html_memo("clean.md", "term-sheet", [], 8)
    assert "No red flags" in out
    assert 'class="risk rA"' in out
    assert "Grade A" in out


def test_print_stylesheet_present():
    out = render_html_memo("c.md", "term-sheet", [], 8)
    assert "@media print" in out


# --- batch -----------------------------------------------------------------


def test_batch_html_summary_table_and_sections():
    results = [
        ("a.md", _findings(), None),
        ("clean.md", [], None),
        ("broken.md", [], "could not extract text"),
    ]
    out = render_batch_html_memo(results, "term-sheet", 8)
    assert out.startswith("<!doctype html>")
    assert 'class="summary"' in out
    assert "a.md" in out and "clean.md" in out
    assert 'id="file-0"' in out and 'id="file-2"' in out
    assert 'href="#file-0"' in out
    assert "could not extract text" in out
    assert out.count("Not legal advice") >= 2


def test_batch_html_per_file_playbooks_column():
    results = [("a.md", _findings(), None)]
    out = render_batch_html_memo(
        results, None, None, per_file_playbooks={"a.md": "term-sheet"}
    )
    assert "Playbook</th>" in out
    assert "term-sheet" in out


# --- CLI end to end --------------------------------------------------------


def _run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *argv],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
        env={"PYTHONPATH": str(ROOT / "src")},
    )


def test_cli_html_single_file():
    proc = _run_cli(
        "review",
        "examples/sample-term-sheet.md",
        "--playbook",
        "term-sheet",
        "--format",
        "html",
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("<!doctype html>")
    assert "Grade F" in proc.stdout


def test_cli_html_batch_directory():
    with tempfile.TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "note.md"
        p1.write_text((ROOT / "examples" / "sample-term-sheet.md").read_text())
        p2 = Path(tmp) / "nda.md"
        p2.write_text((ROOT / "examples" / "sample-nda.md").read_text())
        proc = _run_cli("review", tmp, "--format", "html")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("<!doctype html>")
    assert 'class="summary"' in proc.stdout
    assert "note.md" in proc.stdout and "nda.md" in proc.stdout


def test_cli_html_rejects_invalid_format():
    proc = _run_cli("review", "examples/sample-term-sheet.md", "--format", "pdf")
    assert proc.returncode != 0
