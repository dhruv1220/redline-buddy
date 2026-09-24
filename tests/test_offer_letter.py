"""Tests for the offer-letter playbook."""
import subprocess
import sys
from pathlib import Path

from redline.playbook import load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = ROOT / "playbooks" / "offer-letter.yaml"
SAMPLE = ROOT / "examples" / "sample-offer.md"


def _text():
    return SAMPLE.read_text(encoding="utf-8")


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "offer-letter"
    assert len(pb.rules) == 6
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_all_six_rules():
    findings = review_contract(_text(), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == {
        "equity-terms",
        "non-compete",
        "severance",
        "base-salary",
        "arbitration",
        "at-will",
    }


def test_clean_offer_fires_nothing():
    pb = load_playbook(PLAYBOOK)
    text = (
        "Offer: Senior Engineer. Base salary $200,000 per year, paid semi-monthly. "
        "Equity: 10,000 stock options, vesting over four years with a one year cliff. "
        "Severance: two weeks per year of service as separation pay on termination without cause."
    )
    findings = review_contract(text, pb)
    assert {f.rule_id for f in findings} == set()


def test_cli_offer_letter_playbook():
    import os

    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", str(PLAYBOOK), "--format", "diff"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Non-compete in the offer letter" in proc.stdout
    assert "```diff" in proc.stdout
    # the non-compete fallback is quotable replacement language
    assert "Strike the non-compete" in proc.stdout
