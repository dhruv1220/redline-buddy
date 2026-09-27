"""Tests for the tos-user playbook."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("tos-user")
SAMPLE = ROOT / "examples" / "sample-tos-user.md"

# The sample is a platform-favoring ToS: every rule should fire.
EXPECTED_FIRED = {
    "mandatory-arbitration",
    "class-action-waiver",
    "unilateral-changes",
    "account-termination-any-reason",
    "data-sale-to-third-parties",
    "no-data-deletion",
    "perpetual-content-license",
    "no-easy-cancellation",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "tos-user"
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_cli_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "tos-user", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
