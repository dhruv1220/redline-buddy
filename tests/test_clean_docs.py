"""Negative tests: clean documents must fire nothing on their intended playbook.

Guards against over-eager patterns (false positives) as playbooks evolve.
"""
from pathlib import Path

import pytest

from redline.playbook import load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent

PAIRS = [
    ("saas-vendor", "clean-msa.md"),
    ("nda-recipient", "clean-nda.md"),
    ("contractor", "clean-contractor.md"),
    ("dpa", "clean-dpa.md"),
]


@pytest.mark.parametrize("playbook_name,example", PAIRS)
def test_clean_document_fires_nothing(playbook_name, example):
    pb = load_playbook(ROOT / "playbooks" / f"{playbook_name}.yaml")
    text = (ROOT / "examples" / example).read_text(encoding="utf-8")
    findings = review_contract(text, pb)
    assert findings == [], [f.rule_id for f in findings]
