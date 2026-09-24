"""Tests for the client-sow playbook (freelancer / agency side)."""
import subprocess
import sys
from pathlib import Path

from redline.playbook import load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = ROOT / "playbooks" / "client-sow.yaml"
SAMPLE = ROOT / "examples" / "sample-sow.md"


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "client-sow"
    assert len(pb.rules) == 6
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_all_six_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == {
        "scope-change-process",
        "payment-terms",
        "late-payment",
        "kill-fee",
        "liability-cap",
        "non-compete",
    }


def test_clean_sow_fires_nothing():
    pb = load_playbook(PLAYBOOK)
    text = (
        "SOW: website redesign. Fee $10,000 fixed fee, invoiced monthly, net 15. "
        "Late fee 1.5% per month on overdue invoices. Kill fee 50% of remaining fees "
        "as a termination fee on early termination. Change order required for out-of-scope work. "
        "Limitation of liability: liability shall not exceed fees paid."
    )
    findings = review_contract(text, pb)
    assert {f.rule_id for f in findings} == set()


def test_cli_sow_playbook_diff():
    import os

    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", str(PLAYBOOK), "--format", "diff"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "No change-order process for scope changes" in proc.stdout
    assert "```diff" in proc.stdout
    assert "signed change order" in proc.stdout
