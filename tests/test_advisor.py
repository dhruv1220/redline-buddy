"""Tests for the advisor-agreement playbook (advisor side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("advisor-agreement")
SAMPLE = ROOT / "examples" / "sample-advisor.md"

# The sample is a company-favoring advisor agreement: every rule should fire.
EXPECTED_FIRED = {
    "no-vesting-schedule",
    "compensation-unstated",
    "ip-no-carveout",
    "no-termination-right",
    "non-compete",
    "no-confidentiality",
    "expenses-unaddressed",
    "term-too-long",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "advisor-agreement"
    assert len(pb.rules) == 8
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_compensation_header_alone_does_not_satisfy():
    # A "Compensation" heading with no concrete terms must still fire.
    pb = load_playbook(PLAYBOOK)
    vague = review_contract(
        "## Compensation\nAdvisor will be paid in stock at a later date.",
        pb,
    )
    assert "compensation-unstated" in {f.rule_id for f in vague}
    concrete = review_contract(
        "## Compensation\nAdvisor receives 0.25% of fully diluted equity.",
        pb,
    )
    assert "compensation-unstated" not in {f.rule_id for f in concrete}


def test_background_ip_carveout_does_not_fire():
    pb = load_playbook(PLAYBOOK)
    over = review_contract(
        "Advisor hereby assigns all intellectual property created under this "
        "agreement to the Company.",
        pb,
    )
    assert "ip-no-carveout" in {f.rule_id for f in over}
    ok = review_contract(
        "Advisor assigns work-product IP, retaining all rights to Advisor's "
        "background IP and pre-existing materials.",
        pb,
    )
    assert "ip-no-carveout" not in {f.rule_id for f in ok}


def test_term_boundary():
    pb = load_playbook(PLAYBOOK)
    long_term = review_contract(
        "The initial term of this agreement is three (3) years.",
        pb,
    )
    assert "term-too-long" in {f.rule_id for f in long_term}
    short_term = review_contract(
        "The initial term is one (1) year, renewable by mutual agreement.",
        pb,
    )
    assert "term-too-long" not in {f.rule_id for f in short_term}


def test_cli_advisor_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "advisor-agreement", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "vesting" in proc.stdout.lower()
