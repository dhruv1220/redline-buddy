"""Tests for the consulting-msa playbook (client / hiring-company side)."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = ROOT / "playbooks" / "consulting-msa.yaml"
SAMPLE = ROOT / "examples" / "sample-consulting-msa.md"

# The sample is a vendor-favoring MSA with sane termination-notice,
# payment-terms, and governing-law language — everything else should fire.
EXPECTED_FIRED = {
    "ip-work-product",
    "ip-background-carveout",
    "liability-cap",
    "indemnity-mutual",
    "termination-convenience",
    "rate-increase-cap",
    "warranty",
    "acceptance",
    "auto-renewal",
    "confidentiality-mutual",
    "non-compete",
    "transition-assistance",
}


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "consulting-msa"
    assert len(pb.rules) == 15
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {missing}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {f.rule_id for f in findings} == EXPECTED_FIRED


def test_cli_msa_playbook_memo_and_diff():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    for fmt, marker in (("memo", "No IP assignment for work product"),
                        ("diff", "```diff")):
        proc = subprocess.run(
            [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
             "--playbook", "consulting-msa", "--format", fmt],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        assert marker in proc.stdout
