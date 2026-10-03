"""Tests for the term-sheet-investor playbook (investor side of startup financing term sheets)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("term-sheet-investor")
SAMPLE = ROOT / "examples" / "sample-term-sheet-investor.md"

# The sample is a founder-drafted common-stock term sheet with no investor
# protections — everything should fire.
EXPECTED_FIRED = {
    "no-pro-rata",
    "no-information-rights",
    "no-founder-vesting",
    "weak-liquidation-preference",
    "no-protective-provisions",
    "no-anti-dilution",
    "no-drag-along",
    "no-board-rights",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "term-sheet-investor"
    assert len(pb.rules) == 8
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_cli_investor_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "term-sheet-investor", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "No pro-rata" in proc.stdout
    assert "No founder vesting schedule" in proc.stdout
