"""Tests for the drafting-hygiene checker (`redline hygiene`)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from redline.hygiene import (
    extract_defined_terms,
    render_hygiene_json,
    render_hygiene_text,
    run_hygiene,
)

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "hygiene-sample.md"


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _by_check(findings):
    grouped: dict[str, list] = {}
    for f in findings:
        grouped.setdefault(f.check_id, []).append(f)
    return grouped


# ---------------------------------------------------------------------------
# Defined-term extraction
# ---------------------------------------------------------------------------


def test_extract_defined_terms_quote_means():
    text = '"Confidential Information" means any secret stuff.\n"Fees" shall mean the amounts.\n'
    defs = extract_defined_terms(text)
    assert [(d.term, d.line) for d in defs] == [
        ("Confidential Information", 1),
        ("Fees", 2),
    ]


def test_extract_defined_terms_paren_abbreviation():
    defs = extract_defined_terms('Acme Corporation ("Acme") agrees.\n')
    assert [(d.term, d.line) for d in defs] == [("Acme", 1)]


def test_extract_defined_terms_or_alternatives():
    defs = extract_defined_terms('("Term" or "Terms") means a period.\n')
    assert sorted(d.term for d in defs) == ["Term", "Terms"]


# ---------------------------------------------------------------------------
# Fixture: every check fires with the expected count and line
# ---------------------------------------------------------------------------


def test_fixture_finding_totals():
    findings = run_hygiene(_text())
    assert len(findings) == 10
    severities = [f.severity for f in findings]
    assert severities.count("medium") == 6
    assert severities.count("low") == 4
    assert "high" not in severities and "critical" not in severities


def test_fixture_dead_definitions():
    grouped = _by_check(run_hygiene(_text()))
    dead = grouped["dead-definition"]
    assert sorted((f.line, f.severity) for f in dead) == [(25, "low"), (27, "low")]
    assert any('"Dead Term"' in f.title for f in dead)


def test_fixture_defined_twice():
    grouped = _by_check(run_hygiene(_text()))
    dupes = grouped["defined-twice"]
    assert len(dupes) == 1
    assert dupes[0].line == 31 and dupes[0].severity == "medium"
    assert "29, 31" in dupes[0].detail


def test_fixture_used_before_defined():
    grouped = _by_check(run_hygiene(_text()))
    early = grouped["used-before-defined"]
    # Headings ("2. Fees") don't count as prose uses, so Fees lands on line 15.
    assert sorted((f.line, f.severity) for f in early) == [(6, "low"), (15, "low")]


def test_fixture_inconsistent_case():
    grouped = _by_check(run_hygiene(_text()))
    (finding,) = grouped["inconsistent-case"]
    assert finding.line == 21 and finding.severity == "medium"
    assert '"Agreement"' in finding.title


def test_fixture_undefined_terms():
    grouped = _by_check(run_hygiene(_text()))
    undefined = grouped["undefined-term"]
    assert sorted((f.line, f.severity) for f in undefined) == [
        (34, "medium"),
        (37, "medium"),
    ]
    titles = " ".join(f.title for f in undefined)
    assert "Support Services" in titles and "Licensed Software" in titles


def test_fixture_dangling_references():
    grouped = _by_check(run_hygiene(_text()))
    dangling = grouped["dangling-reference"]
    assert sorted((f.line, f.severity) for f in dangling) == [
        (40, "medium"),
        (41, "medium"),
    ]
    details = " ".join(f.detail for f in dangling)
    assert "Section 7.3" in details and "Exhibit B" in details


def test_findings_sorted_by_severity_then_line():
    findings = run_hygiene(_text())
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    keys = [(rank[f.severity], f.line or 0) for f in findings]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Negative / unit cases
# ---------------------------------------------------------------------------


def test_clean_text_produces_no_findings():
    text = (
        '"Services" means the work described in Section 1.\n'
        "\n"
        "1. Scope\n"
        "\n"
        "The provider shall perform the Services promptly.\n"
        "All Services are subject to Section 1.\n"
    )
    assert run_hygiene(text) == []


def test_boilerplate_phrases_are_not_flagged_undefined():
    text = (
        "This Agreement is effective as of the Effective Date. The Parties "
        "agree that This Agreement shall be governed by Applicable Law. The "
        "Parties further agree that This Agreement reflects their Mutual "
        "Agreement.\n"
    )
    assert "undefined-term" not in _by_check(run_hygiene(text))


def test_valid_cross_references_are_not_flagged():
    text = (
        "1. Term\n"
        "\n"
        "The term is described in Section 1.\n"
        "\n"
        "EXHIBIT A\n"
        "\n"
        "Fees are listed in Exhibit A.\n"
    )
    assert "dangling-reference" not in _by_check(run_hygiene(text))


def test_single_word_capitalized_phrase_not_flagged():
    text = "Provider shall deliver. Provider shall support. Provider shall invoice.\n"
    assert "undefined-term" not in _by_check(run_hygiene(text))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_text_shape():
    findings = run_hygiene(_text())
    out = render_hygiene_text("hygiene-sample.md", findings)
    assert "redline hygiene — hygiene-sample.md" in out
    assert "10 finding(s): 0 high, 6 medium, 4 low" in out
    assert "Not legal advice." in out


def test_render_text_clean():
    assert "No drafting-hygiene issues found." in render_hygiene_text("x.md", [])


def test_render_json_shape():
    findings = run_hygiene(_text())
    data = json.loads(render_hygiene_json("hygiene-sample.md", findings))
    assert data["contract"] == "hygiene-sample.md"
    assert data["finding_count"] == 10
    assert {f["check_id"] for f in data["findings"]} == {
        "dead-definition",
        "defined-twice",
        "used-before-defined",
        "inconsistent-case",
        "undefined-term",
        "dangling-reference",
    }
    for f in data["findings"]:
        assert set(f) == {"check_id", "severity", "title", "detail", "line"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_cli(*argv: str):
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *argv],
        cwd=Path(__file__).resolve().parent.parent,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        },
        capture_output=True,
        text=True,
    )


def test_cli_text_exit_zero():
    proc = _run_cli("hygiene", "examples/hygiene-sample.md")
    assert proc.returncode == 0, proc.stderr
    assert "10 finding(s)" in proc.stdout


def test_cli_json_parses():
    proc = _run_cli("hygiene", "examples/hygiene-sample.md", "--format", "json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["finding_count"] == 10


def test_cli_fail_on_medium_exits_one():
    proc = _run_cli(
        "hygiene", "examples/hygiene-sample.md", "--fail-on", "medium"
    )
    assert proc.returncode == 1


def test_cli_fail_on_high_passes():
    proc = _run_cli("hygiene", "examples/hygiene-sample.md", "--fail-on", "high")
    assert proc.returncode == 0


def test_cli_missing_file_exits_two():
    proc = _run_cli("hygiene", "examples/does-not-exist.md")
    assert proc.returncode == 2
    assert "error:" in proc.stderr


def test_cli_on_clean_example_exits_zero():
    proc = _run_cli("hygiene", "examples/clean-msa.md")
    assert proc.returncode == 0, proc.stderr
    # Valid output either way; the heuristic must not crash on real docs.
    assert "redline hygiene" in proc.stdout
