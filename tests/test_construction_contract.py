"""Tests for the construction-contract playbook (homeowner side of home-improvement contracts)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("construction-contract")
SAMPLE = ROOT / "examples" / "sample-construction-contract.md"

# The sample is a contractor-favoring remodel agreement: 50% deposit, T&M with
# no cap, no dates, no lien waivers, no written change orders, final payment
# before inspection — everything should fire.
EXPECTED_FIRED = {
    "large-upfront-deposit",
    "final-payment-before-completion",
    "no-written-change-orders",
    "no-start-completion-dates",
    "no-lien-waiver",
    "vague-scope",
    "binding-arbitration",
    "contractor-may-assign",
    "no-workmanship-warranty",
    "no-cancellation-right",
    "open-ended-pricing",
    "owner-pulls-permits",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "construction-contract"
    assert len(pb.rules) == 12
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_severities():
    pb = load_playbook(PLAYBOOK)
    sev = {r.id: r.severity for r in pb.rules}
    assert sev["large-upfront-deposit"] == "high"
    assert sev["no-lien-waiver"] == "high"
    assert sev["contractor-may-assign"] == "low"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_cli_construction_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "construction-contract", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Upfront deposit exceeds one-third" in proc.stdout
    assert "No lien-waiver protection" in proc.stdout
