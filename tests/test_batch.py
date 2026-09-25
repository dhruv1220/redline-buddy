"""Tests for batch directory review: `redline review <dir>`."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _make_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="redline-batch-"))
    shutil.copy(ROOT / "examples" / "sample-lease.md", d / "bad-lease.md")
    shutil.copy(ROOT / "examples" / "clean-lease.md", d / "good-lease.md")
    (d / "notes.txt").write_text("not a contract, just notes\n")
    (d / "ignore.exe").write_bytes(b"MZ...")
    return d


def _run(*argv: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *argv],
        capture_output=True, text=True, env=env, timeout=60,
    )


def test_batch_memo_has_summary_table():
    d = _make_dir()
    try:
        proc = _run("review", str(d), "--playbook", "lease-tenant")
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout
        assert "# Batch red-flag review" in out
        assert "bad-lease.md" in out and "good-lease.md" in out
        # notes.txt is a supported suffix and gets reviewed (0 findings);
        # the .exe is skipped silently
        assert "ignore.exe" not in out
        assert "| File |" in out
        # per-file memo sections follow the summary
        assert "# Red-flag memo: bad-lease.md" in out
        assert "# Red-flag memo: good-lease.md" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_batch_json_summary_counts():
    d = _make_dir()
    try:
        proc = _run("review", str(d), "--playbook", "lease-tenant", "--format", "json")
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["playbook"] == "lease-tenant"
        assert data["file_count"] == 3  # 2 leases + notes.txt
        by_name = {c["contract"]: c for c in data["contracts"]}
        assert by_name["bad-lease.md"]["finding_count"] == 10
        assert by_name["good-lease.md"]["finding_count"] == 0
        assert by_name["notes.txt"]["finding_count"] >= 0
        assert data["total_findings"] == sum(
            c["finding_count"] for c in data["contracts"]
        )
        assert sum(data["by_severity"].values()) == data["total_findings"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_batch_fail_on():
    d = _make_dir()
    try:
        proc = _run("review", str(d), "--playbook", "lease-tenant", "--fail-on", "high")
        assert proc.returncode == 1, proc.stderr + proc.stdout
        proc2 = _run(
            "review", str(d), "--playbook", "lease-tenant",
            "--fail-on", "critical",
        )
        assert proc2.returncode == 0, proc2.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_batch_empty_dir_errors():
    d = Path(tempfile.mkdtemp(prefix="redline-empty-"))
    try:
        proc = _run("review", str(d), "--playbook", "lease-tenant")
        assert proc.returncode == 2
        assert "no supported contract files" in proc.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_batch_diff_concatenates_files():
    d = _make_dir()
    try:
        proc = _run(
            "review", str(d), "--playbook", "lease-tenant", "--format", "diff"
        )
        assert proc.returncode == 0, proc.stderr
        assert "# Redline: bad-lease.md" in proc.stdout
        assert "# Redline: good-lease.md" in proc.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)
