"""Tests for the auto-dealership playbook (buyer side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("auto-dealership")
SAMPLE = ROOT / "examples" / "sample-auto-dealership.md"
CLEAN = ROOT / "examples" / "clean-auto-dealership.md"

EXPECTED_FIRED = {
    "spot-delivery",
    "packed-addons",
    "binding-arbitration",
    "doc-fee",
    "service-contract-no-cancel",
    "negative-equity-roll",
    "kill-switch",
    "as-is-sale",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "auto-dealership"
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
    assert len(by_sev["high"]) == 3
    assert len(by_sev["medium"]) == 4
    assert by_sev["low"] == ["as-is-sale"]


def test_clean_fires_nothing():
    findings = review_contract(CLEAN.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert findings == []


def test_explicit_non_waiver_suppresses_arbitration():
    pb = load_playbook(PLAYBOOK)
    findings = review_contract(
        "Buyer does not waive the right to a jury trial or class action. "
        "No arbitration agreement here.",
        pb,
    )
    assert [f.rule_id for f in findings if f.rule_id == "binding-arbitration"] == []


def test_cli_auto_dealership_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "auto-dealership", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Spot delivery" in proc.stdout
    assert "yo-yo" in proc.stdout
