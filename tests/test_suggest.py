"""Tests for auto playbook suggestion (redline.suggest + `redline suggest`)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from redline.suggest import (
    AMBIGUITY_RATIO,
    FALLBACK_PLAYBOOK,
    MIN_SCORE,
    auto_select_playbook,
    suggest_playbooks,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# Fixtures whose intended playbook is unambiguous (each is the fixture its
# playbook's own test module reviews, or the clean-doc pairing).
STRICT_PAIRS = [
    ("sample-advisor.md", "advisor-agreement"),
    ("sample-commercial-lease.md", "commercial-landlord"),
    ("sample-consulting-msa.md", "consulting-msa"),
    ("sample-contractor.md", "contractor"),
    ("sample-distribution-agreement.md", "distribution-agreement"),
    ("sample-dpa.md", "dpa"),
    ("sample-dpa-processor.md", "dpa-processor"),
    ("sample-employment.md", "employment-agreement"),
    ("sample-equipment-lease.md", "equipment-lease"),
    ("sample-franchise-agreement.md", "franchise-agreement"),
    ("sample-homeowners-insurance.md", "homeowners-insurance"),
    ("sample-ip-assignment.md", "ip-assignment"),
    ("sample-lease.md", "lease-tenant"),
    ("sample-loan.md", "loan-borrower"),
    ("sample-nda-discloser.md", "nda-discloser"),
    ("sample-partnership-agreement.md", "partnership-agreement"),
    ("sample-privacy-policy.md", "privacy-policy"),
    ("sample-real-estate-purchase.md", "real-estate-purchase"),
    ("sample-reseller-agreement.md", "reseller-agreement"),
    ("sample-software-escrow.md", "software-escrow"),
    ("sample-data-license-agreement.md", "data-license-agreement"),
    ("sample-settlement-agreement.md", "settlement-agreement"),
    ("sample-severance-agreement.md", "severance-agreement"),
    ("sample-software-license.md", "software-license"),
    ("sample-sow.md", "client-sow"),
    ("sample-tos-user.md", "tos-user"),
    ("sample-website-development.md", "website-development"),
]

# Genuinely ambiguous fixtures: the intended playbook must rank in the top 3,
# but top-1 is not asserted.
AMBIGUOUS_PAIRS = [
    ("sample-msa.md", "saas-vendor"),
    ("sample-offer.md", "offer-letter"),
    ("sample-vendor-msa.md", "consulting-vendor"),
    ("sample-nda.md", "nda-recipient"),
]


@pytest.mark.parametrize("example,want", STRICT_PAIRS)
def test_suggest_top1_matches_fixture(example, want):
    text = (ROOT / "examples" / example).read_text(encoding="utf-8")
    top = suggest_playbooks(text, limit=1)[0]
    assert top.name == want, f"{example}: top={top.name} ({top.score}), want {want}"
    assert top.score >= MIN_SCORE


@pytest.mark.parametrize("example,want", AMBIGUOUS_PAIRS)
def test_suggest_top5_contains_intended_playbook(example, want):
    text = (ROOT / "examples" / example).read_text(encoding="utf-8")
    names = [m.name for m in suggest_playbooks(text, limit=5)]
    assert want in names, f"{example}: top5={names}, want {want} in top 5"


def test_auto_select_clear_winner():
    text = (ROOT / "examples" / "sample-settlement-agreement.md").read_text(encoding="utf-8")
    name, note = auto_select_playbook(text)
    assert name == "settlement-agreement"
    assert "auto-selected" in note


def test_auto_select_ambiguous_falls_back_to_default():
    text = (ROOT / "examples" / "sample-msa.md").read_text(encoding="utf-8")
    matches = suggest_playbooks(text, limit=2)
    assert matches[1].findings > 0  # test setup: rival is a real contender
    assert matches[1].score >= AMBIGUITY_RATIO * matches[0].score  # ...and close
    name, note = auto_select_playbook(text)
    assert name == FALLBACK_PLAYBOOK == "saas-vendor"
    assert "ambiguous" in note


def test_auto_select_mirror_rival_without_findings_is_not_ambiguous():
    # dpa-processor shares dpa's vocabulary and scores close, but its rules
    # don't fire on a controller-side DPA — so dpa is selected, not the
    # saas-vendor fallback.
    text = (ROOT / "examples" / "sample-dpa.md").read_text(encoding="utf-8")
    matches = suggest_playbooks(text, limit=2)
    assert matches[0].name == "dpa"
    assert matches[1].name == "dpa-processor"
    assert matches[1].findings == 0
    name, _ = auto_select_playbook(text)
    assert name == "dpa"


def test_auto_select_gibberish_falls_back_to_default():
    name, note = auto_select_playbook("lorem ipsum dolor sit amet consectetur adipiscing elit " * 20)
    assert name == FALLBACK_PLAYBOOK
    assert "no confident playbook match" in note


def test_suggest_is_deterministic():
    text = (ROOT / "examples" / "sample-dpa.md").read_text(encoding="utf-8")
    first = [(m.name, m.score) for m in suggest_playbooks(text)]
    second = [(m.name, m.score) for m in suggest_playbooks(text)]
    assert first == second


def _run_cli(*argv):
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *argv],
        check=False, capture_output=True, text=True, env=env, timeout=30,
    )


def test_cli_suggest_command():
    proc = _run_cli("suggest", str(ROOT / "examples" / "sample-settlement-agreement.md"))
    assert proc.returncode == 0, proc.stderr
    assert "settlement-agreement" in proc.stdout
    assert "redline review" in proc.stdout


def test_cli_suggest_limit():
    proc = _run_cli(
        "suggest", str(ROOT / "examples" / "sample-dpa.md"), "--limit", "1",
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("(score ") == 1


def test_cli_review_without_playbook_auto_selects_clear_winner():
    proc = _run_cli(
        "review", str(ROOT / "examples" / "sample-settlement-agreement.md"), "--format", "json",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["playbook"] == "settlement-agreement"
    assert "auto-selected" in proc.stderr


def test_cli_review_without_playbook_ambiguous_keeps_default():
    proc = _run_cli(
        "review", str(ROOT / "examples" / "sample-msa.md"), "--format", "json",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["playbook"] == "saas-vendor"
    assert "ambiguous" in proc.stderr
