"""Tests for the childcare-enrollment playbook (parent side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("childcare-enrollment")
SAMPLE = ROOT / "examples" / "sample-childcare-enrollment.md"
CLEAN = ROOT / "examples" / "clean-childcare-enrollment.md"

EXPECTED_FIRED = {
    "nonrefundable-deposit",
    "full-tuition-absences",
    "withdrawal-notice",
    "rate-increase",
    "no-closure-credits",
    "liability-waiver",
    "late-pickup-fees",
    "photo-release",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "childcare-enrollment"
    assert len(pb.rules) == 8
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_severity_mix():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    by_sev = {}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f.rule_id)
    assert len(by_sev["high"]) == 2
    assert len(by_sev["medium"]) == 5
    assert by_sev["low"] == ["photo-release"]


def test_clean_fires_nothing():
    findings = review_contract(CLEAN.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert findings == []


def test_reasonable_late_fee_suppressed():
    pb = load_playbook(PLAYBOOK)
    findings = review_contract(
        "Late pick-up is billed at $1 per minute after a 10-minute grace "
        "period, capped at $30 per occurrence.",
        pb,
    )
    assert [f.rule_id for f in findings if f.rule_id == "late-pickup-fees"] == []


def test_cli_childcare_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "childcare-enrollment", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Non-refundable deposit" in proc.stdout
    assert "60 days" in proc.stdout
