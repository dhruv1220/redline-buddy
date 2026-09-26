"""Compare two drafts of a contract: what changed, and what risk changed.

Negotiations go in rounds — the other side sends "draft v2" and you need to
know what they quietly edited. This module diffs two contract texts at the
paragraph level and re-runs the playbook on both, so the memo can report:

- text changes (paragraphs added / removed / reworded),
- findings GAINED in the new draft (new red flags they introduced),
- findings RESOLVED in the new draft (concessions they made),
- findings still firing but on REWORDED language (re-drafted, still risky).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .playbook import Playbook
from .review import Finding, review_contract

_WS = re.compile(r"\s+")


def _norm(unit: str) -> str:
    return _WS.sub(" ", unit).strip().lower()


def split_units(text: str) -> list[str]:
    """Split contract text into paragraph-level units (blank-line separated)."""
    units = [u.strip() for u in re.split(r"\n\s*\n", text.strip())]
    return [u for u in units if u]


@dataclass
class TextChange:
    kind: str  # "added" | "removed" | "modified"
    old: str = ""
    new: str = ""


def diff_units(old_units: list[str], new_units: list[str]) -> list[TextChange]:
    """Classify paragraph-level changes between two unit lists.

    Matching is done on whitespace-normalized units; raw text is kept for
    display. A ``replace`` opcode pairs old/new units positionally as
    ``modified``; surplus units on either side become ``removed``/``added``.
    """
    sm = difflib.SequenceMatcher(
        a=[_norm(u) for u in old_units],
        b=[_norm(u) for u in new_units],
        autojunk=False,
    )
    changes: list[TextChange] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            changes.extend(TextChange("removed", old=u) for u in old_units[i1:i2])
        elif tag == "insert":
            changes.extend(TextChange("added", new=u) for u in new_units[j1:j2])
        else:  # replace
            old_seg, new_seg = old_units[i1:i2], new_units[j1:j2]
            for o, n in zip(old_seg, new_seg):
                changes.append(TextChange("modified", old=o, new=n))
            for o in old_seg[len(new_seg):]:
                changes.append(TextChange("removed", old=o))
            for n in new_seg[len(old_seg):]:
                changes.append(TextChange("added", new=n))
    return changes


@dataclass
class Reworded:
    before: Finding
    after: Finding


@dataclass
class Comparison:
    old_name: str
    new_name: str
    playbook_name: str
    changes: list[TextChange] = field(default_factory=list)
    findings_old: list[Finding] = field(default_factory=list)
    findings_new: list[Finding] = field(default_factory=list)
    gained: list[Finding] = field(default_factory=list)
    resolved: list[Finding] = field(default_factory=list)
    reworded: list[Reworded] = field(default_factory=list)


def compare_contracts(
    old_name: str, new_name: str, old_text: str, new_text: str, playbook: Playbook
) -> Comparison:
    """Diff two contract texts and classify the finding deltas between them.

    Findings are matched by rule id: a rule firing only in the new draft is
    *gained*, only in the old draft is *resolved*. A rule firing in both but
    with a different excerpt means the clause was reworded yet is still
    flagged (skipped when both excerpts are empty, e.g. missing-clause rules).
    """
    changes = diff_units(split_units(old_text), split_units(new_text))
    findings_old = review_contract(old_text, playbook)
    findings_new = review_contract(new_text, playbook)

    old_by_id = {f.rule_id: f for f in findings_old}
    new_by_id = {f.rule_id: f for f in findings_new}

    gained = [new_by_id[r] for r in new_by_id if r not in old_by_id]
    resolved = [old_by_id[r] for r in old_by_id if r not in new_by_id]
    reworded = [
        Reworded(old_by_id[r], new_by_id[r])
        for r in old_by_id
        if r in new_by_id
        and old_by_id[r].excerpt != new_by_id[r].excerpt
        and (old_by_id[r].excerpt or new_by_id[r].excerpt)
    ]
    return Comparison(
        old_name=old_name,
        new_name=new_name,
        playbook_name=playbook.name,
        changes=changes,
        findings_old=findings_old,
        findings_new=findings_new,
        gained=gained,
        resolved=resolved,
        reworded=reworded,
    )
