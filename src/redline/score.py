"""Risk score and letter grade for a review's findings.

Deterministic and easy to reason about: every finding contributes a
severity weight, and the score is 100 minus the total, floored at 0.
The letter grade follows ToS;DR-style bands (A–F) so a memo gets a
glanceable headline in addition to the finding list.
"""
from __future__ import annotations

from .review import Finding

SEVERITY_WEIGHT = {
    "critical": 30,
    "high": 15,
    "medium": 7,
    "low": 3,
}

# (minimum score for the grade, grade), checked in order.
_GRADE_BANDS = (
    (90, "A"),
    (75, "B"),
    (60, "C"),
    (40, "D"),
)


def risk_score(findings: list[Finding]) -> int:
    """Contract risk score, 0–100. Higher is safer."""
    total = sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in findings)
    return max(0, 100 - min(100, total))


def risk_grade(score: int) -> str:
    """Letter grade A–F for a risk score."""
    for minimum, grade in _GRADE_BANDS:
        if score >= minimum:
            return grade
    return "F"


def risk_label(findings: list[Finding]) -> str:
    """Compact headline, e.g. ``"63/100 · Grade C"``."""
    score = risk_score(findings)
    return f"{score}/100 · Grade {risk_grade(score)}"


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}


def grade_worse_than(grade: str, threshold: str) -> bool:
    """True when ``grade`` is a worse letter than ``threshold``.

    Used by the ``--fail-below`` CI gate: ``--fail-below B`` fails the run
    when the review grades out at C, D, or F.
    """
    return GRADE_RANK.get(grade, 4) > GRADE_RANK.get(threshold, 0)
