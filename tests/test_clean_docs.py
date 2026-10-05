"""Negative tests: clean documents must fire nothing on their intended playbook.

Guards against over-eager patterns (false positives) as playbooks evolve.
"""
from pathlib import Path

import pytest

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent

PAIRS = [
    ("saas-vendor", "clean-msa.md"),
    ("nda-recipient", "clean-nda.md"),
    ("contractor", "clean-contractor.md"),
    ("dpa", "clean-dpa.md"),
    ("consulting-msa", "clean-consulting-msa.md"),
    ("lease-tenant", "clean-lease.md"),
    ("consulting-vendor", "clean-vendor-msa.md"),
    ("loan-borrower", "clean-loan.md"),
    ("commercial-landlord", "clean-commercial-lease.md"),
    ("employment-agreement", "clean-employment.md"),
    ("nda-discloser", "clean-nda-discloser.md"),
    ("advisor-agreement", "clean-advisor.md"),
    ("franchise-agreement", "clean-franchise-agreement.md"),
    ("software-license", "clean-software-license.md"),
    ("distribution-agreement", "clean-distribution-agreement.md"),
    ("tos-user", "clean-tos-user.md"),
    ("privacy-policy", "clean-privacy-policy.md"),
    ("severance-agreement", "clean-severance-agreement.md"),
    ("equipment-lease", "clean-equipment-lease.md"),
    ("real-estate-purchase", "clean-real-estate-purchase.md"),
    ("partnership-agreement", "clean-partnership-agreement.md"),
    ("ip-assignment", "clean-ip-assignment.md"),
    ("website-development", "clean-website-development.md"),
    ("settlement-agreement", "clean-settlement-agreement.md"),
    ("homeowners-insurance", "clean-homeowners-insurance.md"),
    ("dpa-processor", "clean-dpa-processor.md"),
    ("reseller-agreement", "clean-reseller-agreement.md"),
    ("software-escrow", "clean-software-escrow.md"),
    ("data-license-agreement", "clean-data-license-agreement.md"),
    ("event-venue", "clean-event-venue.md"),
    ("term-sheet", "clean-term-sheet.md"),
    ("convertible-note", "clean-convertible-note.md"),
    ("construction-contract", "clean-construction-contract.md"),
    ("term-sheet-investor", "clean-term-sheet-investor.md"),
    ("saas-provider", "clean-saas-provider.md"),
    ("software-licensor", "clean-software-licensor.md"),
    ("commercial-tenant", "clean-commercial-tenant.md"),
    ("employment-employer", "clean-employment-employer.md"),
]


@pytest.mark.parametrize("playbook_name,example", PAIRS)
def test_clean_document_fires_nothing(playbook_name, example):
    pb = load_playbook(bundled_playbook_path(f"{playbook_name}.yaml"))
    text = (ROOT / "examples" / example).read_text(encoding="utf-8")
    findings = review_contract(text, pb)
    assert findings == [], [f.rule_id for f in findings]
