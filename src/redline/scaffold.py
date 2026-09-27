"""Scaffold a new playbook: YAML + sample/clean fixtures + test skeleton.

`redline new-playbook <name>` creates everything a new bundled playbook
needs, so adding one is filling in rules rather than copying boilerplate.
"""
from __future__ import annotations

import re
from pathlib import Path

_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

PLAYBOOK_TEMPLATE = """\
name: {name}
version: 1
description: {description}
# Rule schema:
#   id: snake-case unique id
#   title: short human title shown in the memo
#   severity: critical | high | medium | low
#   description / why / suggestion: plain-language text for the memo
#   fallback: quotable clause language for the --format diff view (recommended)
#   check.kind: requires_any | forbids_any | forbids_unless | max_value
#     requires_any: fires when NONE of the patterns match (something missing)
#     forbids_any: fires when ANY pattern matches (something forbidden present)
#     forbids_unless: fires when a pattern matches and none of unless_any match
#     max_value: fires when the captured (?P<value>\\d+) exceeds max
# Patterns are regexes (case-insensitive). Keep literal phrases short and
# whitespace-tolerant: extraction wraps lines, so prefer \\s+ over spaces in
# multi-word phrases (review_contract also normalizes whitespace for you).
rules:
  # EXAMPLE — replace with real rules. Delete this block when done.
  - id: example-missing-clause
    title: Example rule (requires_any)
    severity: medium
    description: Fires when the contract lacks an expected clause.
    why: Explain why its absence hurts the reviewer.
    suggestion: What to ask for instead.
    fallback: "Quotable replacement clause language goes here."
    check:
      kind: requires_any
      patterns:
        - expected clause phrase

  - id: example-forbidden-clause
    title: Example rule (forbids_any)
    severity: high
    description: Fires when a forbidden clause is present.
    why: Explain why its presence hurts the reviewer.
    suggestion: What to strike or narrow.
    fallback: "Quotable replacement clause language goes here."
    check:
      kind: forbids_any
      patterns:
        - forbidden clause phrase

  - id: example-carve-out
    title: Example rule (forbids_unless)
    severity: medium
    description: Fires when a broad clause lacks its safety carve-out.
    why: Explain what the missing carve-out costs the reviewer.
    suggestion: What carve-out to add.
    fallback: "Quotable replacement clause language goes here."
    check:
      kind: forbids_unless
      patterns:
        - broad clause phrase
      unless_any:
        - safety carve-out phrase
"""

SAMPLE_TEMPLATE = """\
# SAMPLE CONTRACT ({name})

<!-- TODO: replace with a realistic contract that is UNFAVORABLE to the
     reviewer. Aim for every rule in {playbook} to fire at least once. -->

This is a placeholder. Write the sample contract here, then run:

    redline validate {playbook} --sample {sample}
"""

CLEAN_TEMPLATE = """\
# SAMPLE CONTRACT, BALANCED ({name})

<!-- TODO: replace with a realistic, balanced contract on which ZERO rules
     in {playbook} should fire. Add it to the PAIRS list in
     tests/test_clean_docs.py. -->

This is a placeholder for the clean (no-findings) fixture.
"""

TEST_TEMPLATE = '''\
"""Tests for the {name} playbook."""
import os
import subprocess
import sys
from pathlib import Path

from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import review_contract

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = bundled_playbook_path("{name}")
SAMPLE = ROOT / "examples" / "{sample_file}"

# TODO: fill in the rule ids your sample contract fires.
EXPECTED_FIRED = set()  # type: set[str]


def test_playbook_loads_with_fallbacks():
    pb = load_playbook(PLAYBOOK)
    assert pb.name == "{name}"
    assert {{r.severity for r in pb.rules}} <= {{"critical", "high", "medium", "low"}}
    missing = [r.id for r in pb.rules if not r.fallback]
    assert not missing, f"rules missing fallback: {{missing}}"


def test_sample_fires_expected_rules():
    findings = review_contract(SAMPLE.read_text(encoding="utf-8"), load_playbook(PLAYBOOK))
    assert {{f.rule_id for f in findings}} == EXPECTED_FIRED


def test_cli_playbook_by_bundled_name():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "redline.cli", "review", str(SAMPLE),
         "--playbook", "{name}", "--format", "memo"],
        check=False,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
'''


def validate_name(name: str) -> str:
    """Return the name if it is a valid playbook slug, else raise ValueError."""
    if not _NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid playbook name {name!r}: use lowercase letters, digits, "
            "and hyphens (e.g. franchise-agreement)"
        )
    return name


def scaffold_playbook(root: Path, name: str, description: str) -> list[Path]:
    """Create the playbook YAML, fixtures, and test skeleton under root.

    Returns the created paths. Raises FileExistsError if any target exists,
    ValueError for a bad name.
    """
    validate_name(name)
    test_slug = name.replace("-", "_")
    targets = {
        Path("src/redline/playbooks") / f"{name}.yaml": PLAYBOOK_TEMPLATE.format(
            name=name, description=description
        ),
        Path("examples") / f"sample-{name}.md": SAMPLE_TEMPLATE.format(
            name=name, playbook=f"src/redline/playbooks/{name}.yaml",
            sample=f"examples/sample-{name}.md",
        ),
        Path("examples") / f"clean-{name}.md": CLEAN_TEMPLATE.format(
            name=name, playbook=f"src/redline/playbooks/{name}.yaml",
        ),
        Path("tests") / f"test_{test_slug}.py": TEST_TEMPLATE.format(
            name=name, sample_file=f"sample-{name}.md",
        ),
    }
    existing = [str(root / rel) for rel in targets if (root / rel).exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing files: " + ", ".join(existing)
        )
    created = []
    for rel, content in targets.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return created


NEXT_STEPS = """\
Next steps:
  1. Fill in real rules in the playbook YAML (delete the EXAMPLE block).
  2. Write the sample contract so every rule fires:
       redline validate {playbook} --sample {sample}
  3. Write the clean contract so zero rules fire, and add it to
     tests/test_clean_docs.py PAIRS.
  4. Fill in EXPECTED_FIRED in {test} and run: python -m pytest
"""
