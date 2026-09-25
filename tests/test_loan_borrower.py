"""Tests for the loan-borrower playbook (borrower side of business term loans)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("loan-borrower")
SAMPLE = ROOT / "examples" / "sample-loan.md"

# The sample is a lender-favoring loan that states its rate and governing law —
# everything else should fire.
EXPECTED_FIRED = {
    "confession-of-judgment",
    "prepayment-penalty",
    "variable-rate-cap",
    "personal-guarantee",
    "blanket-lien",
    "default-cure",
    "late-fee",
    "arbitration",
    "assignment-lender",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "loan-borrower"
    assert len(pb.rules) == 11
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_confession_of_judgment_is_critical():
    pb = load_playbook(PLAYBOOK)
    sev = {r.id: r.severity for r in pb.rules}
    assert sev["confession-of-judgment"] == "critical"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_cli_loan_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "loan-borrower", "--format", "memo"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Confession of judgment" in proc.stdout
