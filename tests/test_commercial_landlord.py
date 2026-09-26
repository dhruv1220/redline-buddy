"""Tests for the commercial-landlord playbook (landlord side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("commercial-landlord")
SAMPLE = ROOT / "examples" / "sample-commercial-lease.md"

# The sample is a tenant-favoring lease: every rule should fire.
EXPECTED_FIRED = {
    "cam-no-cap",
    "base-year-missing",
    "no-audit-right",
    "no-personal-guarantee",
    "holdover-no-premium",
    "assignment-no-consent",
    "exclusivity-grant",
    "casualty-no-termination",
    "unlimited-relocation",
    "no-env-indemnity",
    "ada-unallocated",
    "no-subrogation-waiver",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "commercial-landlord"
    assert len(pb.rules) == 12
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_capped_cam_does_not_fire():
    pb = load_playbook(PLAYBOOK)
    over = review_contract(
        "Tenant pays its share of CAM expenses, reconciled annually.",
        pb,
    )
    assert "cam-no-cap" in {f.rule_id for f in over}
    ok = review_contract(
        "Tenant pays its share of CAM expenses, capped at 5% annual growth "
        "with capital expenditures excluded.",
        pb,
    )
    assert "cam-no-cap" not in {f.rule_id for f in ok}


def test_cli_commercial_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "commercial-landlord", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Uncapped CAM" in proc.stdout
