"""Tests for the nda-discloser playbook (discloser side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("nda-discloser")
SAMPLE = ROOT / "examples" / "sample-nda-discloser.md"

# The sample is a recipient-favoring NDA: every rule should fire.
EXPECTED_FIRED = {
    "narrow-definition",
    "residuals-carve-out",
    "license-grant",
    "unbounded-affiliates",
    "no-return-or-destroy",
    "survival-too-short",
    "no-injunctive-relief",
    "vague-purpose",
    "no-term",
    "compelled-disclosure",
    "no-obligation-clause",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "nda-discloser"
    assert len(pb.rules) == 11
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_narrow_definition_is_high():
    pb = load_playbook(PLAYBOOK)
    sev = {r.id: r.severity for r in pb.rules}
    assert sev["narrow-definition"] == "high"
    assert sev["residuals-carve-out"] == "high"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_oral_disclosure_carve_out_does_not_fire():
    pb = load_playbook(PLAYBOOK)
    over = review_contract(
        "Confidential Information means only information marked 'Confidential' "
        "in writing.",
        pb,
    )
    assert "narrow-definition" in {f.rule_id for f in over}
    ok = review_contract(
        "Confidential Information means all non-public information, whether "
        "in writing, orally, or visually, whether or not marked.",
        pb,
    )
    assert "narrow-definition" not in {f.rule_id for f in ok}


def test_need_to_know_does_not_fire_affiliates():
    pb = load_playbook(PLAYBOOK)
    over = review_contract(
        "Recipient may disclose Confidential Information to its affiliates.",
        pb,
    )
    assert "unbounded-affiliates" in {f.rule_id for f in over}
    ok = review_contract(
        "Recipient may disclose only to representatives with a need to know "
        "who are bound by confidentiality obligations.",
        pb,
    )
    assert "unbounded-affiliates" not in {f.rule_id for f in ok}


def test_cli_discloser_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "nda-discloser", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "residual" in proc.stdout.lower()
