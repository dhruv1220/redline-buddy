"""Tests for the redline diff view (`redline review --format diff`)."""
import subprocess
import sys
from pathlib import Path

from redline.memo import render_diff
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import Finding, review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _finding(**kw) -> Finding:
    base = dict(
        rule_id="r1",
        title="Some rule",
        severity="high",
        excerpt="flagged contract language",
        why="why",
        suggestion="advice-style suggestion",
        fallback="Quotable fallback clause.",
    )
    base.update(kw)
    return Finding(**base)


def test_diff_renders_removal_and_addition_lines():
    out = render_diff("c.md", "pb", [_finding()])
    assert "```diff" in out
    assert "- flagged contract language" in out
    assert "+ Quotable fallback clause." in out
    assert "Not legal advice" in out


def test_diff_prefers_fallback_over_suggestion():
    out = render_diff("c.md", "pb", [_finding()])
    assert "+ Quotable fallback clause." in out
    assert "+ advice-style suggestion" not in out


def test_diff_falls_back_to_suggestion_when_no_fallback():
    out = render_diff("c.md", "pb", [_finding(fallback="")])
    assert "+ advice-style suggestion" in out


def test_diff_missing_clause_renders_insertion_hunk():
    out = render_diff("c.md", "pb", [_finding(excerpt="")])
    assert "@@ clause missing" in out
    fence = out.split("```diff")[1].split("```")[0]
    assert not any(line.startswith("- ") for line in fence.splitlines())
    assert "+ Quotable fallback clause." in out


def test_diff_no_findings():
    out = render_diff("c.md", "pb", [])
    assert "nothing to redline" in out
    assert "```diff" not in out


def test_diff_sorted_like_memo():
    findings = [
        _finding(rule_id="low-one", title="Low", severity="low", excerpt="a"),
        _finding(rule_id="crit-one", title="Crit", severity="critical", excerpt="b"),
    ]
    findings_sorted = sorted(findings, key=lambda f: ({"critical": 0, "low": 3}[f.severity], f.rule_id))
    out = render_diff("c.md", "pb", findings_sorted)
    assert out.index("Crit") < out.index("Low")


def test_bundled_playbooks_all_have_fallback():
    for pb in ["saas-vendor", "nda-recipient", "contractor", "dpa"]:
        playbook = load_playbook(bundled_playbook_path(f"{pb}.yaml"))
        missing = [r.id for r in playbook.rules if not r.fallback]
        assert not missing, f"{pb}: rules missing fallback: {missing}"


def test_cli_diff_format():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.md"), "--format", "diff")
    assert proc.returncode == 0, proc.stderr
    assert "```diff" in proc.stdout
    assert "- " in proc.stdout
    assert "+ " in proc.stdout
    assert "Redline:" in proc.stdout


def test_cli_diff_end_to_end_uses_rule_fallback():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.md"), "--format", "diff")
    assert proc.returncode == 0, proc.stderr
    # liability-cap fallback language should appear as an addition line
    assert "aggregate liability shall exceed the fees paid" in proc.stdout
