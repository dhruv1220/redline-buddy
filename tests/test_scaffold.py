"""Tests for `redline new-playbook` scaffolding."""
import subprocess
import sys
from pathlib import Path

import pytest

from redline.playbook import load_playbook
from redline.scaffold import scaffold_playbook, validate_name

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def test_scaffold_creates_all_files(tmp_path):
    created = scaffold_playbook(tmp_path, "franchise-agreement", "Test description.")
    rel = sorted(p.relative_to(tmp_path).as_posix() for p in created)
    assert rel == [
        "examples/clean-franchise-agreement.md",
        "examples/sample-franchise-agreement.md",
        "src/redline/playbooks/franchise-agreement.yaml",
        "tests/test_franchise_agreement.py",
    ]


def test_scaffolded_playbook_loads_and_validates(tmp_path):
    (created,) = [
        p for p in scaffold_playbook(tmp_path, "franchise-agreement", "D.")
        if p.suffix == ".yaml"
    ]
    pb = load_playbook(created)
    assert pb.name == "franchise-agreement"
    assert len(pb.rules) == 3
    assert {r.check.kind for r in pb.rules} == {
        "requires_any",
        "forbids_any",
        "forbids_unless",
    }


def test_scaffolded_test_file_is_valid_python(tmp_path):
    (created,) = [
        p for p in scaffold_playbook(tmp_path, "franchise-agreement", "D.")
        if p.name.startswith("test_")
    ]
    compile(created.read_text(encoding="utf-8"), str(created), "exec")


def test_scaffold_refuses_to_overwrite(tmp_path):
    scaffold_playbook(tmp_path, "franchise-agreement", "D.")
    with pytest.raises(FileExistsError):
        scaffold_playbook(tmp_path, "franchise-agreement", "D.")


def test_invalid_names_rejected():
    for bad in ["Franchise Agreement", "a/b", "", "UPPER", "has space", "-lead"]:
        with pytest.raises(ValueError):
            validate_name(bad)
    assert validate_name("franchise-agreement-2") == "franchise-agreement-2"


def test_cli_new_playbook(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "new-playbook", "demo-pb",
         "--root", str(tmp_path), "--description", "Demo."],
        check=False, capture_output=True, text=True,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "created: src/redline/playbooks/demo-pb.yaml" in proc.stdout
    assert "Next steps:" in proc.stdout


def test_cli_new_playbook_bad_name(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "new-playbook", "bad name",
         "--root", str(tmp_path)],
        check=False, capture_output=True, text=True,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    assert proc.returncode == 2
    assert "invalid playbook name" in proc.stderr
