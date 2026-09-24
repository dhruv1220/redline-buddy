import subprocess
import sys
from pathlib import Path

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


def test_review_sample_msa():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.md"))
    assert proc.returncode == 0, proc.stderr
    assert "No limitation of liability" in proc.stdout
    assert "One-sided indemnification" in proc.stdout
    assert "Not legal advice" in proc.stdout


def test_review_missing_contract():
    proc = run_cli("review", str(ROOT / "examples" / "nope.md"))
    assert proc.returncode == 2
    assert "not found" in proc.stderr


def test_review_bad_playbook(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n")
    proc = run_cli(
        "review", str(ROOT / "examples" / "sample-msa.md"), "--playbook", str(bad)
    )
    assert proc.returncode == 2


def test_review_pdf():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.pdf"))
    assert proc.returncode == 0, proc.stderr
    assert "No limitation of liability" in proc.stdout
    assert "Auto-renewal without a clear opt-out" in proc.stdout


def test_review_dpa_playbook():
    proc = run_cli(
        "review",
        str(ROOT / "examples" / "sample-dpa.md"),
        "--playbook",
        str(ROOT / "playbooks" / "dpa.yaml"),
    )
    assert proc.returncode == 0, proc.stderr
    assert "No return-or-delete obligation at termination" in proc.stdout
    assert "No right to object to new subprocessors" in proc.stdout
    assert "No breach-notification timeline" in proc.stdout


def test_review_json_format():
    import json

    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.pdf"), "--format", "json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["contract"] == "sample-msa.pdf"
    assert data["playbook"] == "saas-vendor"
    assert data["finding_count"] == len(data["findings"]) == 6
    first = data["findings"][0]
    assert first["rule_id"] == "liability-cap"
    assert first["severity"] == "high"
    assert "Not legal advice" in data["disclaimer"]


def test_review_contractor_playbook():
    proc = run_cli(
        "review",
        str(ROOT / "examples" / "sample-contractor.md"),
        "--playbook",
        str(ROOT / "playbooks" / "contractor.yaml"),
    )
    assert proc.returncode == 0, proc.stderr
    assert "No IP / work-product assignment" in proc.stdout
    assert "Hidden non-compete in a contractor agreement" in proc.stdout
    assert "Expenses reimbursable without pre-approval" in proc.stdout


def test_review_unsupported_type(tmp_path):
    rtf = tmp_path / "contract.rtf"
    rtf.write_text("hello")
    proc = run_cli("review", str(rtf))
    assert proc.returncode == 2
    assert "unsupported" in proc.stderr


def test_review_docx(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("This Agreement shall automatically renew for successive terms.")
    p = tmp_path / "contract.docx"
    doc.save(str(p))
    proc = run_cli("review", str(p))
    assert proc.returncode == 0, proc.stderr
    assert "Auto-renewal without a clear opt-out" in proc.stdout


def test_fail_on_high_fails_on_high_findings():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.md"), "--fail-on", "high")
    assert proc.returncode == 1, proc.stderr


def test_fail_on_critical_passes_without_critical():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.md"), "--fail-on", "critical")
    assert proc.returncode == 0, proc.stderr


def test_fail_on_low_fails_on_any_finding():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.md"), "--fail-on", "low")
    assert proc.returncode == 1


def test_no_fail_on_flag_never_fails():
    proc = run_cli("review", str(ROOT / "examples" / "sample-msa.md"))
    assert proc.returncode == 0, proc.stderr


def test_validate_good_playbook():
    proc = run_cli("validate", str(ROOT / "playbooks" / "saas-vendor.yaml"))
    assert proc.returncode == 0, proc.stderr
    assert "valid:" in proc.stdout
    assert "rules: 6" in proc.stdout


def test_validate_bad_playbook(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n")
    proc = run_cli("validate", str(bad))
    assert proc.returncode == 2
    assert "invalid:" in proc.stderr


def test_validate_missing_file():
    proc = run_cli("validate", str(ROOT / "playbooks" / "nope.yaml"))
    assert proc.returncode == 2


def test_validate_with_sample_reports_coverage():
    proc = run_cli(
        "validate",
        str(ROOT / "playbooks" / "offer-letter.yaml"),
        "--sample",
        str(ROOT / "examples" / "sample-offer.md"),
    )
    assert proc.returncode == 0, proc.stderr
    assert "6/6 rules fired" in proc.stdout
    assert "non-compete [high] forbids_any +fallback FIRED" in proc.stdout


def test_validate_with_sample_shows_misses():
    proc = run_cli(
        "validate",
        str(ROOT / "playbooks" / "offer-letter.yaml"),
        "--sample",
        str(ROOT / "examples" / "clean-msa.md"),
    )
    assert proc.returncode == 0, proc.stderr
    assert "3/6 rules fired" in proc.stdout
    assert "at-will [low] forbids_any +fallback -" in proc.stdout


def test_validate_with_missing_sample():
    proc = run_cli(
        "validate",
        str(ROOT / "playbooks" / "offer-letter.yaml"),
        "--sample",
        str(ROOT / "examples" / "nope.md"),
    )
    assert proc.returncode == 2
