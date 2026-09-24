"""Deterministic rule engine: run playbook checks against contract text."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .playbook import Playbook, Rule

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Finding:
    rule_id: str
    title: str
    severity: str
    excerpt: str
    why: str
    suggestion: str
    fallback: str = ""


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]


_SENTENCE_END = re.compile(r"[.!?](\s|$)")

def _excerpt(text: str, match: re.Match, window: int = 120, max_len: int = 400) -> str:
    """Snippet around the match, snapped to sentence boundaries.

    The old fixed-char window cut excerpts mid-word ("r receipt of notice"),
    which reads badly in the memo and the diff view. We still cap length so
    a run-on sentence can't blow up the output.
    """
    start = match.start()
    back = text[max(0, start - window):start]
    ends = list(_SENTENCE_END.finditer(back))
    start = max(0, start - window) + (ends[-1].end() if ends else 0)

    end = match.end()
    fwd = text[end:end + window]
    m = _SENTENCE_END.search(fwd)
    end = end + (m.end() if m else len(fwd))

    snippet = text[start:end].replace("\n", " ").strip()
    if len(snippet) > max_len:
        snippet = snippet[:max_len].rsplit(" ", 1)[0].rstrip() + "…"
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def _check_rule(text: str, rule: Rule) -> Finding | None:
    check = rule.check
    patterns = _compile(check.patterns)

    if check.kind == "requires_any":
        if any(p.search(text) for p in patterns):
            return None
        return Finding(rule.id, rule.title, rule.severity, "", rule.why, rule.suggestion, rule.fallback)

    if check.kind == "forbids_any":
        for p in patterns:
            m = p.search(text)
            if m:
                return Finding(rule.id, rule.title, rule.severity, _excerpt(text, m), rule.why, rule.suggestion, rule.fallback)
        return None

    if check.kind == "forbids_unless":
        hit = None
        for p in patterns:
            m = p.search(text)
            if m:
                hit = m
                break
        if hit is None:
            return None
        for u in _compile(check.unless_any):
            if u.search(text):
                return None
        return Finding(rule.id, rule.title, rule.severity, _excerpt(text, hit), rule.why, rule.suggestion, rule.fallback)

    if check.kind == "max_value":
        if check.max is None:
            return None
        for p in patterns:
            for m in p.finditer(text):
                try:
                    value = float(m.group(check.group))
                except (IndexError, ValueError):
                    continue
                if value > check.max:
                    why = f"{rule.why} (found {m.group(check.group)}, limit is {check.max:g})"
                    return Finding(rule.id, rule.title, rule.severity, _excerpt(text, m), why, rule.suggestion, rule.fallback)
        return None

    return None  # unreachable: validated at load


def review_contract(text: str, playbook: Playbook) -> list[Finding]:
    """Run every rule; return findings sorted by severity."""
    findings = [f for rule in playbook.rules if (f := _check_rule(text, rule)) is not None]
    findings.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.rule_id))
    return findings
