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


def test_review_docx(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("This Agreement shall automatically renew for successive terms.")
    p = tmp_path / "contract.docx"
    doc.save(str(p))
    proc = run_cli("review", str(p))
    assert proc.returncode == 0, proc.stderr
    assert "Auto-renewal without a clear opt-out" in proc.stdout
