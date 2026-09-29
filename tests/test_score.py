"""Tests for the risk score + letter grade feature."""
import json

from redline.compare import Comparison, TextChange
from redline.memo import (
    render_batch_json,
    render_batch_memo,
    render_compare_json,
    render_compare_memo,
    render_diff,
    render_json,
    render_memo,
)
from redline.review import Finding
from redline.score import (
    grade_worse_than,
    risk_grade,
    risk_label,
    risk_score,
    severity_counts,
)


def _finding(severity="high", rule_id="r1", title="Some rule"):
    return Finding(rule_id=rule_id, title=title, severity=severity,
                   excerpt="flagged text", why="why", suggestion="suggestion",
                   fallback="Quotable fallback.")


# --- score math ---

def test_empty_findings_score_100_grade_a():
    assert risk_score([]) == 100
    assert risk_grade(100) == "A"


def test_severity_weights():
    assert risk_score([_finding("critical")]) == 70
    assert risk_score([_finding("high")]) == 85
    assert risk_score([_finding("medium")]) == 93
    assert risk_score([_finding("low")]) == 97


def test_score_accumulates_and_floors_at_zero():
    findings = [_finding("critical") for _ in range(10)]
    assert risk_score(findings) == 0


def test_unknown_severity_contributes_nothing():
    assert risk_score([_finding("weird")]) == 100


def test_grade_bands():
    assert risk_grade(90) == "A"
    assert risk_grade(89) == "B"
    assert risk_grade(75) == "B"
    assert risk_grade(74) == "C"
    assert risk_grade(60) == "C"
    assert risk_grade(59) == "D"
    assert risk_grade(40) == "D"
    assert risk_grade(39) == "F"
    assert risk_grade(0) == "F"


def test_risk_label_format():
    findings = [_finding("critical"), _finding("high"), _finding("medium")]
    assert risk_label(findings) == "48/100 · Grade D"


def test_severity_counts():
    findings = [_finding("high"), _finding("high"), _finding("low")]
    assert severity_counts(findings) == {
        "critical": 0, "high": 2, "medium": 0, "low": 1}


# --- memo / diff / json renders ---

def test_memo_shows_risk_headline_with_rule_count():
    findings = [_finding("critical"), _finding("high")]
    md = render_memo("c.md", "saas-vendor", findings, rule_count=12)
    assert "Risk score: **55/100 · Grade D**" in md
    assert "1 critical, 1 high (12 rules checked)" in md


def test_memo_headline_without_rule_count():
    md = render_memo("c.md", "saas-vendor", [])
    assert "Risk score: **100/100 · Grade A** — no findings." in md


def test_memo_headline_optional_for_old_callers():
    # rule_count is optional: existing call sites keep working.
    md = render_memo("c.md", "saas-vendor", [_finding("low")])
    assert "Risk score: **97/100 · Grade A** — 1 low." in md


def test_diff_shows_risk_headline():
    md = render_diff("c.md", "saas-vendor", [_finding("high")], rule_count=10)
    assert "Risk score: **85/100 · Grade B**" in md


def test_json_has_risk_fields():
    findings = [_finding("critical"), _finding("low")]
    data = json.loads(render_json("c.md", "saas-vendor", findings))
    assert data["risk_score"] == 67
    assert data["risk_grade"] == "C"
    assert data["by_severity"] == {
        "critical": 1, "high": 0, "medium": 0, "low": 1}
    assert data["finding_count"] == 2


# --- batch renders ---

def test_batch_memo_has_risk_column():
    results = [("a.md", [_finding("high")], None),
               ("b.md", [], None),
               ("c.pdf", [], "unreadable")]
    md = render_batch_memo(results, "saas-vendor", rule_count=10)
    assert "| File | Risk |" in md
    assert "| a.md | 85 (B) |" in md
    assert "| b.md | 100 (A) |" in md
    assert "Risk score: **85/100 · Grade B**" in md  # per-file memo


def test_batch_json_has_per_contract_risk():
    results = [("a.md", [_finding("critical")], None)]
    data = json.loads(render_batch_json(results, "saas-vendor"))
    assert data["contracts"][0]["risk_score"] == 70
    assert data["contracts"][0]["risk_grade"] == "C"


# --- compare renders ---

def _cmp(old, new):
    return Comparison(old_name="v1.md", new_name="v2.md",
                      playbook_name="saas-vendor", changes=[],
                      findings_old=old, findings_new=new,
                      gained=[], resolved=[], reworded=[])


def test_compare_memo_shows_risk_delta_improved():
    cmp = _cmp([_finding("critical")], [_finding("low")])
    md = render_compare_memo(cmp)
    assert "- Risk: **C (70)** → **A (97)** — improved" in md


def test_compare_memo_shows_risk_delta_worsened():
    cmp = _cmp([], [_finding("critical"), _finding("critical")])
    md = render_compare_memo(cmp)
    assert "- Risk: **A (100)** → **D (40)** — worsened" in md


def test_compare_memo_shows_risk_delta_unchanged():
    cmp = _cmp([_finding("high")], [_finding("high")])
    md = render_compare_memo(cmp)
    assert "- Risk: **B (85)** → **B (85)** — unchanged" in md


def test_compare_json_has_risk_summary():
    cmp = _cmp([_finding("critical")], [])
    data = json.loads(render_compare_json(cmp))
    assert data["summary"]["risk_old"] == {"score": 70, "grade": "C"}
    assert data["summary"]["risk_new"] == {"score": 100, "grade": "A"}


# --- --fail-below gate ---

def test_grade_worse_than():
    assert grade_worse_than("C", "B")
    assert grade_worse_than("F", "A")
    assert not grade_worse_than("B", "B")
    assert not grade_worse_than("A", "C")
    assert not grade_worse_than("F", "F")


def test_cli_fail_below_gate():
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    sample = root / "examples" / "sample-settlement-agreement.md"  # Grade F
    clean = root / "examples" / "clean-settlement-agreement.md"    # Grade A

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "redline.cli", "review", *args],
            check=False, capture_output=True, text=True, env=env, timeout=30)

    r = run(str(sample), "--playbook", "settlement-agreement", "--fail-below", "F")
    assert r.returncode == 0, r.stderr  # F is not worse than F
    r = run(str(sample), "--playbook", "settlement-agreement", "--fail-below", "D")
    assert r.returncode == 1  # F is worse than D
    r = run(str(clean), "--playbook", "settlement-agreement", "--fail-below", "A")
    assert r.returncode == 0, r.stderr
