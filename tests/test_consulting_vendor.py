"""Tests for the consulting-vendor playbook (vendor / consultant side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("consulting-vendor")
SAMPLE = ROOT / "examples" / "sample-vendor-msa.md"

# The sample is a client-favoring MSA with sane payment terms and termination
# notice — everything else should fire.
EXPECTED_FIRED = {
    "ip-assignment-scope",
    "liability-cap",
    "indemnity-mutual",
    "late-payment",
    "kill-fee",
    "non-compete",
    "non-solicitation-one-sided",
    "scope-change-process",
    "client-cooperation",
    "insurance-terms",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "consulting-vendor"
    assert len(pb.rules) == 12
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_cli_vendor_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "consulting-vendor", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Overbroad IP assignment" in proc.stdout
