"""Tests for `redline compare` — negotiation-round diffing."""
import json
import subprocess
import sys
from pathlib import Path

from redline.compare import (
    Comparison,
    TextChange,
    compare_contracts,
    diff_units,
    split_units,
)
from redline.memo import render_compare_json, render_compare_memo
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import Finding

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
EXAMPLES = ROOT / "examples"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _finding(rule_id="r1", title="Some rule", severity="high", excerpt="flagged",
             why="why", suggestion="suggestion", fallback="Quotable fallback."):
    return Finding(rule_id=rule_id, title=title, severity=severity, excerpt=excerpt,
                   why=why, suggestion=suggestion, fallback=fallback)


def _cmp(**kw) -> Comparison:
    base = dict(
        old_name="v1.md",
        new_name="v2.md",
        playbook_name="saas-vendor",
        changes=[TextChange("added", new="new paragraph")],
        findings_old=[_finding("r1"), _finding("r2")],
        findings_new=[_finding("r2"), _finding("r3")],
        gained=[_finding("r3", title="New risk")],
        resolved=[_finding("r1", title="Old risk")],
        reworded=[],
    )
    base.update(kw)
    return Comparison(**base)


# --- split_units ---

def test_split_units_blank_line_separated():
    assert split_units("para one\n\npara two\n\n\npara three") == [
        "para one", "para two", "para three",
    ]


def test_split_units_empty_text():
    assert split_units("") == []
    assert split_units("   \n\n  ") == []


def test_split_units_collapses_internal_whitespace_edges():
    units = split_units("  padded  \n\nsecond")
    assert units == ["padded", "second"]


# --- diff_units ---

def test_diff_identical_units_no_changes():
    assert diff_units(["a", "b"], ["a", "b"]) == []


def test_diff_whitespace_only_change_is_not_a_change():
    assert diff_units(["a  b"], ["a b"]) == []


def test_diff_added_and_removed():
    removed = diff_units(["keep", "gone"], ["keep"])
    assert [c.kind for c in removed] == ["removed"]
    assert removed[0].old == "gone"
    added = diff_units(["keep"], ["keep", "brand new"])
    assert [c.kind for c in added] == ["added"]
    assert added[0].new == "brand new"


def test_diff_single_word_edit_is_modified_not_added_removed():
    changes = diff_units(
        ["The term is twelve months."],
        ["The term is twelve (12) months."],
    )
    assert len(changes) == 1
    assert changes[0].kind == "modified"
    assert changes[0].old == "The term is twelve months."
    assert changes[0].new == "The term is twelve (12) months."


def test_diff_replace_block_pairs_positionally():
    changes = diff_units(["a1", "a2", "a3"], ["b1", "b2"])
    assert [c.kind for c in changes] == ["modified", "modified", "removed"]
    assert changes[2].old == "a3"


def test_diff_insert_block_extra_new_units_are_added():
    changes = diff_units(["a1"], ["b1", "b2"])
    assert [c.kind for c in changes] == ["modified", "added"]


# --- compare_contracts (gained / resolved / reworded) ---

def _playbook():
    return load_playbook(bundled_playbook_path("saas-vendor"))


def _text(*paragraphs: str) -> str:
    return "\n\n".join(paragraphs)


def test_compare_gained_resolved_on_saas_playbook():
    pb = _playbook()
    old = _text(
        "This Agreement has no limitation of liability.",
        "Customer shall indemnify Vendor against all claims.",
    )
    new = _text(
        "This Agreement has no limitation of liability.",
        "Customer shall indemnify Vendor against all claims.",
        "This Agreement shall automatically renew for successive terms.",
    )
    cmp = compare_contracts("v1", "v2", old, new, pb)
    assert [f.rule_id for f in cmp.gained] == ["auto-renewal"]
    assert cmp.resolved == []


def test_compare_resolved_when_clause_fixed():
    pb = _playbook()
    old = _text("Customer shall indemnify Vendor against all claims.")
    new = _text(
        "Each party shall indemnify the other. Vendor shall indemnify Customer "
        "for IP claims."
    )
    cmp = compare_contracts("v1", "v2", old, new, pb)
    assert [f.rule_id for f in cmp.resolved] == ["mutual-indemnification"]
    assert cmp.gained == []


def test_compare_reworded_when_clause_edited_but_still_flagged():
    pb = _playbook()
    old = _text("Customer shall indemnify Vendor against all claims.")
    new = _text(
        "Customer shall indemnify, defend and hold harmless Vendor against "
        "any and all third-party claims whatsoever."
    )
    cmp = compare_contracts("v1", "v2", old, new, pb)
    assert cmp.gained == [] and cmp.resolved == []
    assert len(cmp.reworded) == 1
    rw = cmp.reworded[0]
    assert rw.before.rule_id == rw.after.rule_id == "mutual-indemnification"
    assert rw.before.excerpt != rw.after.excerpt


def test_compare_missing_clause_rules_never_reworded():
    pb = _playbook()
    old = _text("Nothing about liability here.")
    new = _text("Still nothing about liability here.")
    cmp = compare_contracts("v1", "v2", old, new, pb)
    assert any(f.rule_id == "liability-cap" for f in cmp.findings_old)
    assert any(f.rule_id == "liability-cap" for f in cmp.findings_new)
    assert cmp.reworded == []  # both excerpts empty -> not "reworded"


def test_compare_example_rounds_end_to_end():
    pb = _playbook()
    old = (EXAMPLES / "compare-round1.md").read_text()
    new = (EXAMPLES / "compare-round2.md").read_text()
    cmp = compare_contracts("round1", "round2", old, new, pb)
    assert [f.rule_id for f in cmp.gained] == ["auto-renewal"]
    assert sorted(f.rule_id for f in cmp.resolved) == [
        "confidentiality",
        "liability-cap",
        "mutual-indemnification",
        "termination-notice",
    ]
    assert cmp.reworded == []
    assert len(cmp.findings_old) == 5
    assert len(cmp.findings_new) == 2
    kinds = {c.kind for c in cmp.changes}
    assert kinds == {"added", "removed", "modified"}


# --- render_compare_memo ---

def test_compare_memo_sections():
    out = render_compare_memo(_cmp())
    assert "# Contract comparison: v1.md → v2.md" in out
    assert "🚨 New red flags introduced in this round" in out
    assert "✅ Resolved this round" in out
    assert "📝 Text changes" in out
    assert "New risk" in out
    assert "Old risk" in out
    assert "+ new paragraph" in out
    assert "Not legal advice" in out


def test_compare_memo_identical_documents():
    cmp = _cmp(changes=[], findings_old=[], findings_new=[],
               gained=[], resolved=[], reworded=[])
    out = render_compare_memo(cmp)
    assert "No text changes — the documents are identical." in out
    assert "None — the new draft introduces no new playbook findings." in out


def test_compare_memo_reworded_section():
    rw = _cmp(reworded=[type("R", (), {
        "before": _finding("r9", title="Sticky rule", excerpt="old wording"),
        "after": _finding("r9", title="Sticky rule", excerpt="new wording"),
    })()])
    out = render_compare_memo(rw)
    assert "🔁 Reworded but still flagged" in out
    assert "old wording" in out and "new wording" in out


# --- render_compare_json ---

def test_compare_json_structure():
    data = json.loads(render_compare_json(_cmp()))
    assert data["old"] == "v1.md" and data["new"] == "v2.md"
    assert data["summary"]["gained"] == 1
    assert data["summary"]["resolved"] == 1
    assert data["summary"]["changes"]["added"] == 1
    assert [f["rule_id"] for f in data["gained"]] == ["r3"]
    assert [f["rule_id"] for f in data["resolved"]] == ["r1"]
    assert data["changes"][0]["kind"] == "added"
    assert "Not legal advice" in data["disclaimer"]


# --- CLI ---

def test_cli_compare_memo(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Hello world.\n\nCustomer shall indemnify Vendor.")
    b.write_text("Hello world.\n\nCustomer shall indemnify Vendor.\n\nExtra para.")
    res = run_cli("compare", str(a), str(b), "--playbook", "saas-vendor")
    assert res.returncode == 0, res.stderr
    assert "Contract comparison:" in res.stdout
    assert "paragraph added" in res.stdout


def test_cli_compare_identical_exit_zero(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("Same text here.")
    res = run_cli("compare", str(a), str(a), "--playbook", "saas-vendor")
    assert res.returncode == 0, res.stderr
    assert "No text changes" in res.stdout


def test_cli_compare_fail_on_gain(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Customer shall indemnify Vendor against claims.")
    b.write_text(
        "Customer shall indemnify Vendor against claims.\n\n"
        "This Agreement shall automatically renew for successive terms."
    )
    res = run_cli("compare", str(a), str(b), "--playbook", "saas-vendor",
                  "--fail-on-gain", "medium")
    assert res.returncode == 1, res.stderr  # gained auto-renewal (medium) >= medium


def test_cli_compare_fail_on_gain_threshold(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Plain contract with no risky language at all.")
    b.write_text(
        "Plain contract with no risky language at all.\n\n"
        "Customer shall indemnify Vendor against all possible claims forever."
    )
    res = run_cli("compare", str(a), str(b), "--playbook", "saas-vendor",
                  "--fail-on-gain", "high")
    assert res.returncode == 1, res.stderr  # gained mutual-indemnification (high)


def test_cli_compare_fail_on_gain_not_triggered(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Plain contract with no risky language at all.")
    b.write_text(
        "Plain contract with no risky language at all.\n\n"
        "This Agreement shall automatically renew for successive terms."
    )
    res = run_cli("compare", str(a), str(b), "--playbook", "saas-vendor",
                  "--fail-on-gain", "high")
    assert res.returncode == 0, res.stderr  # gained medium < high threshold


def test_cli_compare_json_format(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("Hello.")
    res = run_cli("compare", str(a), str(a), "--playbook", "saas-vendor",
                  "--format", "json")
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    assert data["summary"]["changes"]["total"] == 0


def test_cli_compare_directory_rejected(tmp_path):
    res = run_cli("compare", str(tmp_path), str(tmp_path))
    assert res.returncode == 2
    assert "directories" in res.stderr


def test_cli_compare_missing_file(tmp_path):
    res = run_cli("compare", str(tmp_path / "nope.md"), str(tmp_path / "nope2.md"))
    assert res.returncode == 2
