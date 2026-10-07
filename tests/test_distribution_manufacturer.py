"""Tests for the distribution-manufacturer playbook (manufacturer / supplier side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("distribution-manufacturer")
SAMPLE = ROOT / "examples" / "sample-distribution-manufacturer.md"

EXPECTED_FIRED = {
    "exclusivity-no-minimums",
    "trademark-misuse",
    "distributor-owns-adaptations",
    "post-term-non-compete-manufacturer",
    "distributor-termination-convenience",
    "most-favored-distributor",
    "no-sales-audit-right",
    "no-diligence-standard",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "distribution-manufacturer"
    assert len(pb.rules) == 8
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_cli_manufacturer_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "distribution-manufacturer", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Exclusivity with no minimum purchase commitments" in proc.stdout
