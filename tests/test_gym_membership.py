"""Tests for the gym-membership playbook (consumer side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("gym-membership")
SAMPLE = ROOT / "examples" / "sample-gym-membership.md"
CLEAN = ROOT / "examples" / "clean-gym-membership.md"

EXPECTED_FIRED = {
    "cancellation-gauntlet",
    "auto-renewal",
    "annual-fee",
    "freeze-restrictions",
    "training-contract",
    "initiation-fee",
    "liability-waiver",
    "dues-during-closure",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "gym-membership"
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
    assert by_sev["low"] == ["dues-during-closure"]


def test_clean_fires_nothing():
    findings = review_contract(CLEAN.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert findings == []


def test_narrowed_waiver_suppresses_liability_rule():
    pb = load_playbook(PLAYBOOK)
    findings = review_contract(
        "The liability waiver covers inherent exercise risks only and does "
        "not waive claims from the Club's negligence.",
        pb,
    )
    assert [f.rule_id for f in findings if f.rule_id == "liability-waiver"] == []


def test_cli_gym_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "gym-membership", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Cancellation requires an in-person visit" in proc.stdout
    assert "click-to-cancel" in proc.stdout
