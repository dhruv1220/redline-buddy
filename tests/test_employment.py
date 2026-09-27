"""Tests for the employment-agreement playbook (employee side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("employment-agreement")
SAMPLE = ROOT / "examples" / "sample-employment.md"

# The sample is an employer-favoring agreement: every rule should fire.
EXPECTED_FIRED = {
    "non-compete",
    "ip-assignment-overbroad",
    "non-solicit",
    "confidentiality-overbroad",
    "mandatory-arbitration",
    "no-severance",
    "bonus-clawback",
    "equity-acceleration",
    "garden-leave",
    "moonlighting-ban",
    "termination-notice",
    "prior-inventions",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "employment-agreement"
    assert len(pb.rules) == 12
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_non_compete_is_critical():
    pb = load_playbook(PLAYBOOK)
    sev = {r.id: r.severity for r in pb.rules}
    assert sev["non-compete"] == "critical"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_section_2870_carve_out_does_not_fire():
    pb = load_playbook(PLAYBOOK)
    over = review_contract(
        "Employee hereby assigns to the Company all right, title and interest "
        "in all inventions, whether or not related to the Company's business.",
        pb,
    )
    assert "ip-assignment-overbroad" in {f.rule_id for f in over}
    ok = review_contract(
        "Employee assigns inventions made with Company resources. Inventions "
        "made entirely on Employee's own time with Employee's own equipment "
        "are excluded (Cal. Labor Code section 2870).",
        pb,
    )
    assert "ip-assignment-overbroad" not in {f.rule_id for f in ok}


def test_consent_carve_out_does_not_fire_moonlighting():
    pb = load_playbook(PLAYBOOK)
    over = review_contract(
        "Employee shall not engage in any other employment or business "
        "activity during the term.",
        pb,
    )
    assert "moonlighting-ban" in {f.rule_id for f in over}
    ok = review_contract(
        "Employee may engage in outside employment with the Company's prior "
        "written consent, not to be unreasonably withheld.",
        pb,
    )
    assert "moonlighting-ban" not in {f.rule_id for f in ok}


def test_termination_notice_value_boundary():
    pb = load_playbook(PLAYBOOK)
    long_notice = review_contract(
        "The Company may terminate employment without cause upon ninety (90) "
        "days' written notice.",
        pb,
    )
    assert "termination-notice" in {f.rule_id for f in long_notice}
    short_notice = review_contract(
        "Either party may terminate employment without cause on thirty (30) "
        "days' written notice.",
        pb,
    )
    assert "termination-notice" not in {f.rule_id for f in short_notice}


def test_cli_employment_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "employment-agreement", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "non-compete" in proc.stdout.lower()
