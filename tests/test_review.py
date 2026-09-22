from pathlib import Path

from redline.memo import render_memo
from redline.playbook import load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK = ROOT / "playbooks" / "saas-vendor.yaml"
SAMPLE = ROOT / "examples" / "sample-msa.md"


def test_sample_msa_raises_expected_flags():
    pb = load_playbook(PLAYBOOK)
    findings = review_contract(SAMPLE.read_text(), pb)
    ids = {f.rule_id for f in findings}
    assert {
        "liability-cap",
        "auto-renewal",
        "termination-convenience",
        "termination-notice",
        "mutual-indemnification",
        "confidentiality",
    } <= ids


def test_findings_sorted_by_severity():
    pb = load_playbook(PLAYBOOK)
    findings = review_contract(SAMPLE.read_text(), pb)
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ranks = [rank[f.severity] for f in findings]
    assert ranks == sorted(ranks)
    assert findings[0].severity == "high"  # liability-cap / mutual-indemnification first


def test_clean_contract_passes():
    pb = load_playbook(PLAYBOOK)
    text = (
        "LIMITATION OF LIABILITY. Neither party's liability shall not exceed fees paid. "
        "This agreement does not renew. Either party may terminate for convenience on "
        "30 days written notice. Indemnification is mutual: vendor shall indemnify "
        "customer and customer shall indemnify vendor. Confidential information shall "
        "be protected."
    )
    findings = review_contract(text, pb)
    assert findings == []


def test_memo_renders_findings_and_disclaimer():
    pb = load_playbook(PLAYBOOK)
    findings = review_contract(SAMPLE.read_text(), pb)
    memo = render_memo("sample-msa.md", pb.name, findings)
    assert "Not legal advice" in memo
    assert "No limitation of liability" in memo
    assert "Suggested fallback" in memo


def test_memo_clean_contract():
    memo = render_memo("clean.md", "saas-vendor", [])
    assert "No red flags" in memo
