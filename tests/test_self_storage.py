"""Tests for the self-storage playbook (renter side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("self-storage")
SAMPLE = ROOT / "examples" / "sample-self-storage.md"
CLEAN = ROOT / "examples" / "clean-self-storage.md"

EXPECTED_FIRED = {
    "lien-sale",
    "rent-hike",
    "no-liability",
    "late-fees",
    "forced-insurance",
    "access-restrictions",
    "lockout",
    "abandonment",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "self-storage"
    assert len(pb.rules) == 8
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_severity_mix():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    by_sev = {}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f.rule_id)
    assert len(by_sev["high"]) == 2
    assert len(by_sev["medium"]) == 4
    assert sorted(by_sev["low"]) == ["abandonment", "lockout"]


def test_clean_fires_nothing():
    findings = review_contract(CLEAN.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert findings == []


def test_grace_period_lockout_suppressed():
    pb = load_playbook(PLAYBOOK)
    findings = review_contract(
        "No lockout occurs until rent is at least 10 days past due and "
        "written notice has been sent.",
        pb,
    )
    assert [f.rule_id for f in findings if f.rule_id == "lockout"] == []


def test_cli_self_storage_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "self-storage", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "lien-sold" in proc.stdout or "lien sale" in proc.stdout.lower()
    assert "move-in rates" in proc.stdout
