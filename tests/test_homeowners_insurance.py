"""Tests for the homeowners-insurance playbook."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("homeowners-insurance")
SAMPLE = ROOT / "examples" / "sample-homeowners-insurance.md"
CLEAN = ROOT / "examples" / "clean-homeowners-insurance.md"

# The sample is an insurer-favoring HO-3: every rule should fire.
EXPECTED_FIRED = {
    "anti-concurrent-causation",
    "dwelling-settled-at-acv",
    "percentage-wind-deductible",
    "mold-fungi-sublimit",
    "water-backup-excluded",
    "loss-of-use-cap-low",
    "insurer-right-to-repair",
    "no-ordinance-or-law-coverage",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "homeowners-insurance"
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_clean_fires_nothing():
    findings = review_contract(CLEAN.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert findings == []


def test_cli_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "homeowners-insurance", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Risk score:" in proc.stdout
