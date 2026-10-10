"""Tests for `redline followup` — the round-2 follow-up letter generator."""
import io
import os
import subprocess
import sys
from pathlib import Path

from docx import Document

from redline.compare import Comparison, compare_contracts
from redline.letter import (
    classify_followup,
    render_followup,
    render_followup_docx,
)
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import Finding

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("solar-installation")
ROUND1 = ROOT / "examples" / "sample-solar-installation.md"
ROUND2 = ROOT / "examples" / "sample-solar-installation-round2.md"
CLEAN = ROOT / "examples" / "clean-solar-installation.md"


def _round2_cmp() -> Comparison:
    pb = load_playbook(PLAYBOOK)
    return compare_contracts(
        ROUND1.name,
        ROUND2.name,
        ROUND1.read_text(encoding="utf-8"),
        ROUND2.read_text(encoding="utf-8"),
        pb,
    )


def test_classify_followup():
    cmp = _round2_cmp()
    concessions, remaining = classify_followup(cmp)
    assert {f.rule_id for f in concessions} == {
        "annual-escalator",
        "roof-damage-disclaimed",
    }
    by_id = {f.rule_id: tag for f, tag in remaining}
    assert by_id == {
        # worst-severity-first ordering is checked separately
        **{rid: "outstanding" for rid in (
            "ucc1-lien-on-title",
            "removal-reinstall-at-homeowner-cost",
            "transfer-assumption-hurdles",
            "no-production-guarantee",
        )},
        "payments-during-downtime": "redrafted",
    }
    # worst severity first: the one high (ucc1) leads
    assert remaining[0][0].rule_id == "ucc1-lien-on-title"
    assert remaining[0][0].severity == "high"


def test_classify_min_severity_low_includes_sales_promises():
    _, remaining = classify_followup(_round2_cmp(), "low")
    assert {f.rule_id for f, _ in remaining} == {
        "ucc1-lien-on-title",
        "removal-reinstall-at-homeowner-cost",
        "transfer-assumption-hurdles",
        "no-production-guarantee",
        "sales-promises-disclaimed",
        "payments-during-downtime",
    }


def test_render_md_structure():
    letter = render_followup(_round2_cmp())
    assert letter.startswith("# Follow-up letter — sample-solar-installation-round2.md")
    assert "Dear [Counterparty name]," in letter
    # concessions section thanks them for the fixes
    assert "What's fixed — thank you" in letter
    assert "Annual payment escalator" in letter
    # remaining change requests, worst first, with status tags
    assert "Still open — 5 change requests" in letter
    assert "## 1. " in letter and "— HIGH · NOT ADDRESSED" in letter
    assert "STILL FLAGGED AFTER REDRAFTING" in letter
    assert letter.index("— HIGH") < letter.index("— MEDIUM")
    assert "The contract says:" in letter
    assert "Proposed language:" in letter
    assert "Best regards," in letter
    assert "Not legal advice." in letter


def test_render_no_concessions_section():
    # round 2 fixes nothing: the section is honest about it
    pb = load_playbook(PLAYBOOK)
    same = compare_contracts(
        ROUND1.name, ROUND1.name,
        ROUND1.read_text(encoding="utf-8"), ROUND1.read_text(encoding="utf-8"), pb,
    )
    letter = render_followup(same)
    assert "doesn't resolve any of the issues" in letter


def test_render_all_resolved_ready_to_sign():
    pb = load_playbook(PLAYBOOK)
    cmp = compare_contracts(
        ROUND1.name, CLEAN.name,
        ROUND1.read_text(encoding="utf-8"), CLEAN.read_text(encoding="utf-8"), pb,
    )
    letter = render_followup(cmp)
    assert "ready to move forward" in letter
    assert "Still open" not in letter


def test_render_gained_tagged_new():
    new_finding = Finding(
        rule_id="new-arbitration",
        title="Mandatory arbitration added",
        severity="high",
        excerpt="All disputes go to binding arbitration.",
        why="You lose the courtroom.",
        suggestion="Strike it.",
        fallback="Disputes go to court.",
    )
    cmp = Comparison(
        old_name="r1.md",
        new_name="r2.md",
        playbook_name="solar-installation",
        findings_new=[new_finding],
        gained=[new_finding],
    )
    letter = render_followup(cmp)
    assert "NEW IN THIS DRAFT" in letter
    assert "What's fixed — thank you" in letter


def test_render_txt_has_no_markdown():
    letter = render_followup(_round2_cmp(), fmt="txt")
    for line in letter.splitlines():
        assert not line.startswith("#"), f"markdown heading leaked: {line!r}"
    assert "**" not in letter
    assert not any(line.startswith(">") for line in letter.splitlines())
    assert "Follow-up letter" in letter
    assert "NOT ADDRESSED" in letter


def test_render_personalization():
    letter = render_followup(
        _round2_cmp(), recipient="SunRun Installers", sender="Alex Buyer"
    )
    assert "Dear SunRun Installers," in letter
    assert "Best regards,\nAlex Buyer" in letter
    assert "[Counterparty name]" not in letter


def _doc_text(data: bytes) -> list[str]:
    return [p.text for p in Document(io.BytesIO(data)).paragraphs]


def test_render_docx_structure():
    blob = "\n".join(_doc_text(render_followup_docx(_round2_cmp())))
    assert "Follow-up letter — sample-solar-installation-round2.md" in blob
    assert "Dear [Counterparty name]," in blob
    assert "What's fixed — thank you" in blob
    assert "Still open — 5 change requests" in blob
    assert "NOT ADDRESSED" in blob
    assert "STILL FLAGGED AFTER REDRAFTING" in blob
    assert "Not legal advice." in blob


def test_render_docx_all_resolved():
    pb = load_playbook(PLAYBOOK)
    cmp = compare_contracts(
        ROUND1.name, CLEAN.name,
        ROUND1.read_text(encoding="utf-8"), CLEAN.read_text(encoding="utf-8"), pb,
    )
    blob = "\n".join(_doc_text(render_followup_docx(cmp)))
    assert "ready to move forward" in blob
    assert "Still open" not in blob


def _run_cli(*argv: str, cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *argv],
        capture_output=True, text=True, env=env, cwd=str(cwd or ROOT),
    )


def test_cli_followup_end_to_end():
    proc = _run_cli("followup", str(ROUND1), str(ROUND2),
                    "--playbook", "solar-installation",
                    "--to", "SunRun", "--from", "Alex")
    assert proc.returncode == 0, proc.stderr
    assert "Follow-up letter" in proc.stdout
    assert "Dear SunRun," in proc.stdout
    assert "What's fixed — thank you" in proc.stdout
    assert "STILL FLAGGED AFTER REDRAFTING" in proc.stdout


def test_cli_followup_txt_format():
    proc = _run_cli("followup", str(ROUND1), str(ROUND2),
                    "--playbook", "solar-installation", "--format", "txt")
    assert proc.returncode == 0, proc.stderr
    assert "**" not in proc.stdout
    assert not any(l.startswith("#") for l in proc.stdout.splitlines())


def test_cli_followup_docx_writes_file(tmp_path: Path):
    out = tmp_path / "followup.docx"
    proc = _run_cli("followup", str(ROUND1), str(ROUND2),
                    "--playbook", "solar-installation",
                    "--format", "docx", "-o", str(out))
    assert proc.returncode == 0, proc.stderr
    assert f"wrote {out}" in proc.stdout
    blob = "\n".join(_doc_text(out.read_bytes()))
    assert "Follow-up letter" in blob
    assert "NOT ADDRESSED" in blob


def test_cli_followup_docx_defaults_output_name(tmp_path: Path):
    proc = _run_cli("followup", str(ROUND1), str(ROUND2),
                    "--playbook", "solar-installation",
                    "--format", "docx", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "sample-solar-installation-round2.followup.docx"
    assert out.exists()
    assert f"wrote {out}" in proc.stdout


def test_cli_followup_rejects_directory(tmp_path: Path):
    proc = _run_cli("followup", str(tmp_path), str(ROUND2))
    assert proc.returncode == 2
    assert "not directories" in proc.stderr
