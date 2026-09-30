"""Tests for the reseller-agreement playbook (reseller/channel-partner side)."""
from pathlib import Path

from redline.playbook import load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK = load_playbook(ROOT / "src" / "redline" / "playbooks" / "reseller-agreement.yaml")

EXPECTED_IDS = {
    "vendor-termination-for-convenience",
    "exclusivity-noncompete",
    "no-price-protection",
    "quotas-without-support",
    "no-deal-registration",
    "reseller-ip-indemnity-flowdown",
    "unilateral-agreement-changes",
    "no-transition-assistance",
}


def _review(name: str):
    text = (ROOT / "examples" / name).read_text(encoding="utf-8")
    return review_contract(text, PLAYBOOK)


def test_sample_fires_all_eight_rules():
    findings = _review("sample-reseller-agreement.md")
    assert {f.rule_id for f in findings} == EXPECTED_IDS


def test_clean_fixture_fires_nothing():
    assert _review("clean-reseller-agreement.md") == []


def test_each_rule_has_quotable_fallback():
    for rule in PLAYBOOK.rules:
        assert rule.fallback and len(rule.fallback) > 40, rule.id


def test_severity_mix():
    by_sev: dict[str, int] = {}
    for rule in PLAYBOOK.rules:
        by_sev[rule.severity] = by_sev.get(rule.severity, 0) + 1
    assert by_sev.get("high", 0) == 2
    assert by_sev.get("medium", 0) == 5
    assert by_sev.get("low", 0) == 1
