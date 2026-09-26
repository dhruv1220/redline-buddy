"""Tests for the lease-tenant playbook (tenant side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("lease-tenant")
SAMPLE = ROOT / "examples" / "sample-lease.md"

# The sample is a landlord-favoring lease that does spell out an early
# termination right — everything else should fire.
EXPECTED_FIRED = {
    "security-deposit-cap",
    "rent-escalation-cap",
    "repair-obligations",
    "personal-guarantee",
    "entry-notice",
    "subletting",
    "attorneys-fees",
    "auto-renewal",
    "utilities",
    "wear-and-tear",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "lease-tenant"
    assert len(pb.rules) == 11
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_deposit_max_value_fires_above_cap():
    pb = load_playbook(PLAYBOOK)
    over = review_contract(
        "Tenant shall pay 2 months' rent as a security deposit.", pb
    )
    assert "security-deposit-cap" in {f.rule_id for f in over}
    ok = review_contract(
        "Tenant shall pay 1 month's rent as a security deposit.", pb
    )
    assert "security-deposit-cap" not in {f.rule_id for f in ok}


def test_cli_lease_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "lease-tenant", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Security deposit exceeds one month" in proc.stdout
