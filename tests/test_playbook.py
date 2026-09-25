from pathlib import Path

import pytest

from redline.playbook import PlaybookError, bundled_playbook_path, load_playbook

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK = bundled_playbook_path("saas-vendor")


def test_bundled_playbook_loads():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "saas-vendor"
    assert len(pb.rules) == 6
    assert {r.severity for r in pb.rules} <= {"critical", "high", "medium", "low"}


def test_missing_file(tmp_path):
    with pytest.raises(PlaybookError):
        load_playbook(tmp_path / "nope.yaml")


def test_rejects_bad_severity(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "name: x\nrules:\n"
        "  - id: r1\n    title: t\n    severity: extreme\n"
        "    check: {kind: requires_any, patterns: ['a']}\n"
    )
    with pytest.raises(PlaybookError, match="severity"):
        load_playbook(p)


def test_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "dup.yaml"
    p.write_text(
        "name: x\nrules:\n"
        "  - id: r1\n    title: t\n    severity: low\n"
        "    check: {kind: requires_any, patterns: ['a']}\n"
        "  - id: r1\n    title: t2\n    severity: low\n"
        "    check: {kind: requires_any, patterns: ['b']}\n"
    )
    with pytest.raises(PlaybookError, match="duplicate"):
        load_playbook(p)
