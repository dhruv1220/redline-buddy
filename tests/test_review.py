from pathlib import Path

from redline.memo import render_memo
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK = bundled_playbook_path("saas-vendor")
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


def test_nda_playbook_flags_sample():
    from redline.playbook import bundled_playbook_path, load_playbook

    pb = load_playbook(bundled_playbook_path("nda-recipient"))
    findings = review_contract((ROOT / "examples" / "sample-nda.md").read_text(), pb)
    ids = {f.rule_id for f in findings}
    assert {
        "hidden-non-compete",
        "survival-too-long",
        "no-standard-exclusions",
        "injunctive-relief",
        "return-or-destroy",
    } <= ids
    assert findings[0].severity == "high"


def test_memo_clean_contract():
    memo = render_memo("clean.md", "saas-vendor", [])
    assert "No red flags" in memo


def test_nda_playbook_loads():
    from redline.playbook import bundled_playbook_path, load_playbook

    pb = load_playbook(bundled_playbook_path("nda-recipient"))
    assert pb.name == "nda-recipient"
    assert len(pb.rules) == 5


def test_max_value_captures_full_number():
    # regression: greedy wildcards must not eat digits ("(10)" -> "0")
    from redline.playbook import Check, Rule
    from redline.review import _check_rule

    rule = Rule(
        id="x",
        title="x",
        severity="low",
        description="",
        why="",
        suggestion="",
        check=Check(
            kind="max_value",
            patterns=[r"surviv[^\d]{0,40}(?P<value>\d{1,2})\D{0,6}years"],
            group="value",
            max=5,
        ),
    )
    f = _check_rule("obligations shall survive for ten (10)\nyears", rule)
    assert f is not None
    assert "10" in f.why


def test_excerpt_snaps_to_sentence_boundaries():
    import re

    from redline.review import _excerpt

    text = (
        "This is the first sentence. Here is a second sentence with the TARGET "
        "phrase inside it. And a third sentence follows."
    )
    m = re.search(r"TARGET", text)
    excerpt = _excerpt(text, m)
    assert excerpt == "…Here is a second sentence with the TARGET phrase inside it.…"


def test_excerpt_at_text_start_has_no_leading_ellipsis():
    import re

    from redline.review import _excerpt

    text = "TARGET appears right at the start. Then more text follows here."
    m = re.search(r"TARGET", text)
    excerpt = _excerpt(text, m)
    assert not excerpt.startswith("…")
    assert excerpt.startswith("TARGET appears right at the start.")


def test_excerpt_caps_runaway_sentences():
    import re

    from redline.review import _excerpt

    text = "Start. " + "word " * 200 + "TARGET " + "word " * 200 + ". End."
    m = re.search(r"TARGET", text)
    excerpt = _excerpt(text, m)
    assert len(excerpt) <= 410
    assert excerpt.endswith("…")
