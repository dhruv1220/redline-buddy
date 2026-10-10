"""Tests for `redline letter` — the draft negotiation letter generator."""
import io
import os
import subprocess
import sys
from pathlib import Path

from docx import Document

from redline.letter import render_letter, render_letter_docx, select_findings
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import Finding, review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("solar-installation")
SAMPLE = ROOT / "examples" / "sample-solar-installation.md"
CLEAN = ROOT / "examples" / "clean-solar-installation.md"


def _sample_findings() -> list[Finding]:
    return review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))


def test_select_orders_worst_first():
    findings = _sample_findings()
    assert len(findings) == 8
    selected = select_findings(findings, "medium")
    assert len(selected) == 7  # 3 high + 4 medium, low excluded
    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    assert [ranks[f.severity] for f in selected] == sorted(ranks[f.severity] for f in selected)


def test_select_min_severity_high():
    selected = select_findings(_sample_findings(), "high")
    assert {f.severity for f in selected} == {"high"}
    assert len(selected) == 3


def test_select_min_severity_low_includes_all():
    assert len(select_findings(_sample_findings(), "low")) == 8


def test_render_md_structure():
    letter = render_letter("sample-solar-installation.md", "solar-installation", _sample_findings())
    assert letter.startswith("# Draft negotiation letter — sample-solar-installation.md")
    assert "Dear [Counterparty name]," in letter
    # numbered change requests, worst severity first
    assert "## 1. " in letter and "— HIGH" in letter
    assert letter.index("— HIGH") < letter.index("— MEDIUM")
    # each finding quotes the contract, explains the concern, proposes a change
    assert "The contract says:" in letter
    assert "Our concern:" in letter
    assert "Our requested change:" in letter
    # fallback replacement language is quoted for rules that have it
    assert "Proposed language:" in letter
    assert "no annual escalator or automatic increase" in letter
    # signature + disclaimer
    assert "Best regards," in letter
    assert "Not legal advice." in letter


def test_render_personalization():
    letter = render_letter(
        "c.md", "solar-installation", _sample_findings(),
        recipient="SunRun Installers", sender="Alex Buyer",
    )
    assert "Dear SunRun Installers," in letter
    assert "Best regards,\nAlex Buyer" in letter
    assert "[Counterparty name]" not in letter
    assert "[Your name]" not in letter


def test_render_txt_has_no_markdown():
    letter = render_letter("c.md", "solar-installation", _sample_findings(), fmt="txt")
    for line in letter.splitlines():
        assert not line.startswith("#"), f"markdown heading leaked: {line!r}"
    assert "**" not in letter
    assert not any(line.startswith(">") for line in letter.splitlines())
    assert "Draft negotiation letter" in letter
    assert "Not legal advice." in letter


def test_render_no_findings():
    findings = review_contract(CLEAN.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert findings == []
    letter = render_letter("clean-solar-installation.md", "solar-installation", findings)
    assert "no material issues" in letter
    assert "## 1." not in letter
    assert "Not legal advice." in letter


def test_render_single_finding_pluralization():
    one = _sample_findings()[:1]
    letter = render_letter("c.md", "solar-installation", one)
    assert "the following 1 change before signing" in letter
    assert "## 2." not in letter


def _run_cli(*argv: str, cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *argv],
        capture_output=True, text=True, env=env, cwd=str(cwd or ROOT),
    )


def test_cli_letter_end_to_end():
    proc = _run_cli("letter", str(SAMPLE), "--playbook", "solar-installation",
                    "--to", "SunRun", "--from", "Alex")
    assert proc.returncode == 0, proc.stderr
    assert "Draft negotiation letter" in proc.stdout
    assert "Dear SunRun," in proc.stdout
    assert "Alex" in proc.stdout


def test_cli_letter_min_severity():
    proc = _run_cli("letter", str(SAMPLE), "--playbook", "solar-installation",
                    "--min-severity", "high")
    assert proc.returncode == 0, proc.stderr
    assert "## 1." in proc.stdout and "## 3." in proc.stdout
    assert "## 4." not in proc.stdout  # only the 3 highs


def test_cli_letter_txt_format():
    proc = _run_cli("letter", str(SAMPLE), "--playbook", "solar-installation",
                    "--format", "txt")
    assert proc.returncode == 0, proc.stderr
    assert "**" not in proc.stdout
    assert not any(l.startswith("#") for l in proc.stdout.splitlines())


def test_cli_letter_out_file(tmp_path: Path):
    out = tmp_path / "letter.md"
    proc = _run_cli("letter", str(SAMPLE), "--playbook", "solar-installation",
                    "-o", str(out))
    assert proc.returncode == 0, proc.stderr
    assert f"wrote {out}" in proc.stdout
    assert "Draft negotiation letter" in out.read_text(encoding="utf-8")


def test_cli_letter_clean_contract():
    proc = _run_cli("letter", str(CLEAN), "--playbook", "solar-installation")
    assert proc.returncode == 0, proc.stderr
    assert "no material issues" in proc.stdout


def test_cli_letter_rejects_directory(tmp_path: Path):
    proc = _run_cli("letter", str(tmp_path))
    assert proc.returncode == 2
    assert "not a directory" in proc.stderr


def _doc_text(data: bytes) -> list[str]:
    doc = Document(io.BytesIO(data))
    return [p.text for p in doc.paragraphs]


def test_render_docx_structure():
    data = render_letter_docx("sample-solar-installation.md", "solar-installation", _sample_findings())
    texts = _doc_text(data)
    blob = "\n".join(texts)
    assert texts[0] == "Draft negotiation letter — sample-solar-installation.md"
    assert "Dear [Counterparty name]," in blob
    # numbered change requests, worst severity first
    assert any(t.startswith("1. ") and "HIGH" in t for t in texts)
    assert blob.index("HIGH") < blob.index("MEDIUM")
    # contract excerpts and fallback language are quoted blocks
    assert "no annual escalator or automatic increase" in blob
    assert "The contract says:" in blob
    assert "Our concern:" in blob
    assert "Our requested change:" in blob
    assert "Proposed language:" in blob
    assert "Best regards," in blob
    assert "Not legal advice." in blob


def test_render_docx_personalization():
    data = render_letter_docx(
        "c.md", "solar-installation", _sample_findings(),
        recipient="SunRun Installers", sender="Alex Buyer",
    )
    blob = "\n".join(_doc_text(data))
    assert "Dear SunRun Installers," in blob
    assert "Alex Buyer" in blob
    assert "[Counterparty name]" not in blob
    assert "[Your name]" not in blob


def test_render_docx_no_findings():
    findings = review_contract(CLEAN.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert findings == []
    blob = "\n".join(_doc_text(render_letter_docx("clean-solar-installation.md", "solar-installation", findings)))
    assert "no material issues" in blob
    assert "The contract says:" not in blob
    assert "Not legal advice." in blob


def test_render_docx_single_finding():
    blob = "\n".join(_doc_text(render_letter_docx("c.md", "solar-installation", _sample_findings()[:1])))
    assert "the following 1 change before signing" in blob


def test_cli_letter_docx_writes_file(tmp_path: Path):
    out = tmp_path / "letter.docx"
    proc = _run_cli("letter", str(SAMPLE), "--playbook", "solar-installation",
                    "--to", "SunRun", "--from", "Alex",
                    "--format", "docx", "-o", str(out))
    assert proc.returncode == 0, proc.stderr
    assert f"wrote {out}" in proc.stdout
    assert out.stat().st_size > 0
    blob = "\n".join(_doc_text(out.read_bytes()))
    assert "Draft negotiation letter" in blob
    assert "Dear SunRun," in blob
    assert "Alex" in blob


def test_cli_letter_docx_defaults_output_name(tmp_path: Path):
    proc = _run_cli("letter", str(SAMPLE), "--playbook", "solar-installation",
                    "--format", "docx", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "sample-solar-installation.letter.docx"
    assert out.exists()
    assert f"wrote {out}" in proc.stdout
    blob = "\n".join(_doc_text(out.read_bytes()))
    assert "Draft negotiation letter" in blob
