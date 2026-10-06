"""Drafting-hygiene checker: internal consistency of a contract's drafting.

Playbooks judge a contract's substance; this module judges its plumbing —
whether defined terms are used consistently and whether internal
cross-references actually point somewhere. Everything is deterministic and
local, like the rest of redline-buddy.

Checks performed:

- ``dead-definition`` (low) — a term is defined but never used again.
- ``undefined-term`` (medium) — a capitalized multi-word phrase is used
  three or more times but never defined anywhere.
- ``inconsistent-case`` (medium) — a defined term like ``Agreement`` also
  appears in lowercase (``agreement``), which usually means the writer
  sometimes forgot it was a defined term.
- ``defined-twice`` (medium) — the same term is defined more than once.
- ``dangling-reference`` (medium) — a ``Section X`` / ``Article X`` /
  ``Exhibit X`` / ``Schedule X`` / ``Appendix X`` reference points at a
  target that does not exist in the document.
- ``used-before-defined`` (low) — a defined term's first use comes before
  its definition.

All findings carry a 1-based line number where the evidence lives.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# ---------------------------------------------------------------------------
# Defined-term extraction
# ---------------------------------------------------------------------------

# `"Confidential Information" means ...` / `"Fees" shall mean ...` /
# `"Term" is defined as ...` / `"Duties" refers to ...`
_DEFINITION_RE = re.compile(
    r'"([^"\n]{1,80})"\s+'
    r"(?:shall\s+|will\s+)?"
    r"(?:means?|includes?|refers?\s+to|is\s+defined\s+as|shall\s+be\s+deemed\s+to\s+mean)"
)

# `Acme Corporation ("Acme")` / `("Term" or "Terms")` — quoted terms in
# parentheses count as defined. Any quoted term inside parens is treated as a
# definition; a heuristic, documented as such.
_PAREN_RE = re.compile(r"\(([^()\n]{1,170})\)")
_QUOTED_RE = re.compile(r'"([^"\n]{1,80})"')

# Cross-reference mentions: `Section 4.2`, `Article III`, `Exhibit A`, ...
_REFERENCE_RE = re.compile(
    r"\b(Section|Sections|Article|Articles|Exhibit|Schedule|Appendix)\s+"
    r"([A-Z0-9][A-Z0-9.\-]*)",
    re.IGNORECASE,
)

# Numbered section headings: `4.2 Fees`, `Section 1. Term`, ...
_HEADING_NUMBER_RE = re.compile(r"^\s*(?:section\s+)?(\d+(?:\.\d+)*)\b", re.IGNORECASE)

# Exhibit / Schedule / Appendix headings: `EXHIBIT A`, `Schedule 1: Fees`, ...
_HEADING_EXHIBIT_RE = re.compile(
    r"^\s*(exhibit|schedule|appendix)\s+([A-Z0-9][A-Z0-9.\-]*)", re.IGNORECASE
)

# Article headings with roman numerals: `Article III — Term`, `ARTICLE II`
_ARTICLE_HEADING_RE = re.compile(
    r"^\s*article\s+([IVXLCDM]+)\b", re.IGNORECASE
)

# Candidate undefined terms: two or more consecutive capitalized words.
_TITLE_PHRASE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")

# Boilerplate phrases that contracts routinely use without a formal
# definition; flagging them would be noise.
_COMMON_UNDEFINED_OK = {
    "This Agreement",
    "The Parties",
    "The Company",
    "Effective Date",
    "Business Day",
    "Business Days",
    "Applicable Law",
    "Force Majeure",
    "Good Faith",
    "Best Efforts",
    "Prior Written Consent",
    "Written Notice",
    "Mutual Agreement",
    "Ordinary Course",
}

_UNDEFINED_USES_THRESHOLD = 3
_LOWERCASE_USES_THRESHOLD = 3


@dataclass
class HygieneFinding:
    check_id: str
    severity: str
    title: str
    detail: str
    line: int | None = None


@dataclass
class _Definition:
    term: str
    line: int  # 1-based definition line


def _normalize_whitespace(term: str) -> str:
    return " ".join(term.split())


def extract_defined_terms(text: str) -> list[_Definition]:
    """Find defined terms with their 1-based definition line numbers."""
    definitions: list[_Definition] = []
    seen: set[tuple[str, int]] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        terms: list[str] = []
        for match in _DEFINITION_RE.finditer(line):
            terms.append(match.group(1))
        for paren in _PAREN_RE.finditer(line):
            terms.extend(m.group(1) for m in _QUOTED_RE.finditer(paren.group(1)))
        for raw in terms:
            term = _normalize_whitespace(raw)
            if not term or not re.search(r"[A-Za-z]", term):
                continue
            key = (term, lineno)
            if key not in seen:
                seen.add(key)
                definitions.append(_Definition(term=term, line=lineno))
    return definitions


def _term_occurrences(term: str, lines: list[str], *, skip_lines: set[int]) -> list[int]:
    """1-based line numbers where *term* appears, skipping definition lines."""
    pattern = re.compile(r"\b" + re.escape(term) + r"\b")
    hits: list[int] = []
    for lineno, line in enumerate(lines, start=1):
        if lineno in skip_lines:
            continue
        if pattern.search(line):
            hits.append(lineno)
    return hits


def _check_dead_definitions(
    definitions: list[_Definition], lines: list[str]
) -> list[HygieneFinding]:
    findings: list[HygieneFinding] = []
    by_term: dict[str, list[_Definition]] = {}
    for d in definitions:
        by_term.setdefault(d.term, []).append(d)
    for term, defs in sorted(by_term.items()):
        skip = {d.line for d in defs}
        uses = _term_occurrences(term, lines, skip_lines=skip)
        if not uses:
            findings.append(
                HygieneFinding(
                    check_id="dead-definition",
                    severity="low",
                    title=f'Defined term "{term}" is never used',
                    detail=(
                        f'"{term}" is defined on line {defs[0].line} but never '
                        "used anywhere else in the document. Remove the "
                        "definition or the defined term."
                    ),
                    line=defs[0].line,
                )
            )
    return findings


def _check_defined_twice(definitions: list[_Definition]) -> list[HygieneFinding]:
    findings: list[HygieneFinding] = []
    by_term: dict[str, list[int]] = {}
    for d in definitions:
        by_term.setdefault(d.term, []).append(d.line)
    for term in sorted(by_term):
        linenos = sorted(set(by_term[term]))
        if len(linenos) > 1:
            findings.append(
                HygieneFinding(
                    check_id="defined-twice",
                    severity="medium",
                    title=f'Term "{term}" is defined more than once',
                    detail=(
                        f'"{term}" is defined on lines '
                        f"{', '.join(str(n) for n in linenos)}. Duplicate "
                        "definitions risk conflicting meanings — keep one."
                    ),
                    line=linenos[1],
                )
            )
    return findings


def _heading_lines(lines: list[str]) -> set[int]:
    """1-based line numbers that are section/exhibit/article headings."""
    numbered = set()
    for lineno, line in enumerate(lines, start=1):
        if (
            _HEADING_NUMBER_RE.match(line)
            or _ARTICLE_HEADING_RE.match(line)
            or _HEADING_EXHIBIT_RE.match(line)
        ):
            numbered.add(lineno)
    return numbered


def _check_used_before_defined(
    definitions: list[_Definition], lines: list[str]
) -> list[HygieneFinding]:
    headings = _heading_lines(lines)
    findings: list[HygieneFinding] = []
    by_term: dict[str, list[_Definition]] = {}
    for d in definitions:
        by_term.setdefault(d.term, []).append(d)
    for term in sorted(by_term):
        defs = by_term[term]
        first_def_line = min(d.line for d in defs)
        skip = {d.line for d in defs} | headings
        uses = _term_occurrences(term, lines, skip_lines=skip)
        if uses and min(uses) < first_def_line:
            findings.append(
                HygieneFinding(
                    check_id="used-before-defined",
                    severity="low",
                    title=f'Term "{term}" is used before it is defined',
                    detail=(
                        f'"{term}" first appears on line {min(uses)} but is '
                        f"not defined until line {first_def_line}. Move the "
                        "definition earlier or introduce the term on first use."
                    ),
                    line=min(uses),
                )
            )
    return findings


def _check_inconsistent_case(
    definitions: list[_Definition], lines: list[str]
) -> list[HygieneFinding]:
    findings: list[HygieneFinding] = []
    seen: set[str] = set()
    for d in definitions:
        term = d.term
        if term in seen or term.lower() == term:
            continue
        seen.add(term)
        skip = {dd.line for dd in definitions if dd.term == term}
        lowered = _term_occurrences(term.lower(), lines, skip_lines=skip)
        if len(lowered) >= _LOWERCASE_USES_THRESHOLD:
            findings.append(
                HygieneFinding(
                    check_id="inconsistent-case",
                    severity="medium",
                    title=f'Defined term "{term}" is also used in lowercase',
                    detail=(
                        f'"{term}" is defined as a capitalized term, but the '
                        f'lowercase "{term.lower()}" appears {len(lowered)} '
                        f"times (first on line {lowered[0]}). Decide whether "
                        "each use means the defined term and capitalize it, "
                        "or use a different word."
                    ),
                    line=lowered[0],
                )
            )
    return findings


_ARTICLE_STRIP_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _check_undefined_terms(
    definitions: list[_Definition], lines: list[str]
) -> list[HygieneFinding]:
    defined = {d.term for d in definitions}
    # key: article-stripped phrase -> (display phrase, first-seen line, count)
    occurrences: dict[str, tuple[str, int, int]] = {}
    for lineno, line in enumerate(lines, start=1):
        for match in _TITLE_PHRASE_RE.finditer(line):
            phrase = _normalize_whitespace(match.group(1))
            if phrase in _COMMON_UNDEFINED_OK:
                continue
            key = _ARTICLE_STRIP_RE.sub("", phrase)
            if key in defined or key in _COMMON_UNDEFINED_OK:
                continue
            if key in occurrences:
                _, first, count = occurrences[key]
                occurrences[key] = (key, first, count + 1)
            else:
                occurrences[key] = (key, lineno, 1)
    findings: list[HygieneFinding] = []
    for key in sorted(occurrences):
        display, first_lineno, count = occurrences[key]
        if count >= _UNDEFINED_USES_THRESHOLD:
            findings.append(
                HygieneFinding(
                    check_id="undefined-term",
                    severity="medium",
                    title=f'Term "{display}" is used but never defined',
                    detail=(
                        f'"{display}" appears {count} times (first on line '
                        f"{first_lineno}) without a definition. Define it in "
                        "a definitions section or replace it with plain "
                        "language."
                    ),
                    line=first_lineno,
                )
            )
    return findings


def _collect_reference_targets(lines: list[str]) -> dict[str, set[str]]:
    """Map reference kind -> normalized set of existing targets.

    Kinds: ``section`` (numeric headings + roman-numeral articles),
    ``exhibit`` (exhibits, schedules, appendices).
    """
    targets: dict[str, set[str]] = {"section": set(), "exhibit": set()}
    for line in lines:
        match = _HEADING_NUMBER_RE.match(line)
        if match:
            targets["section"].add(match.group(1).rstrip("."))
        match = _ARTICLE_HEADING_RE.match(line)
        if match:
            targets["section"].add(match.group(1).upper())
        match = _HEADING_EXHIBIT_RE.match(line)
        if match:
            targets["exhibit"].add(match.group(2).upper())
    return targets


def _check_dangling_references(lines: list[str]) -> list[HygieneFinding]:
    targets = _collect_reference_targets(lines)
    seen: set[tuple[str, str]] = set()
    findings: list[HygieneFinding] = []
    for lineno, line in enumerate(lines, start=1):
        for match in _REFERENCE_RE.finditer(line):
            kind = match.group(1).lower().rstrip("s")
            raw_target = match.group(2).rstrip(".")
            bucket = "exhibit" if kind in ("exhibit", "schedule", "appendix") else "section"
            target = raw_target.upper()
            key = (bucket, target)
            if key in seen:
                continue
            seen.add(key)
            if target not in targets[bucket]:
                findings.append(
                    HygieneFinding(
                        check_id="dangling-reference",
                        severity="medium",
                        title=f"Reference to {match.group(1)} {raw_target} has no matching target",
                        detail=(
                            f"Line {lineno} refers to {match.group(1)} "
                            f"{raw_target}, but no such "
                            f"{'section' if bucket == 'section' else 'exhibit/schedule/appendix'} "
                            "heading exists in the document. Fix the number or "
                            "add the missing section."
                        ),
                        line=lineno,
                    )
                )
    return findings


def run_hygiene(text: str) -> list[HygieneFinding]:
    """Run every drafting-hygiene check over *text*.

    Returns findings sorted by severity (worst first), then line number.
    """
    lines = text.splitlines()
    definitions = extract_defined_terms(text)
    findings: list[HygieneFinding] = []
    findings.extend(_check_dead_definitions(definitions, lines))
    findings.extend(_check_defined_twice(definitions))
    findings.extend(_check_used_before_defined(definitions, lines))
    findings.extend(_check_inconsistent_case(definitions, lines))
    findings.extend(_check_undefined_terms(definitions, lines))
    findings.extend(_check_dangling_references(lines))
    findings.sort(
        key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.line or 0, f.check_id)
    )
    return findings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_hygiene_text(contract_name: str, findings: list[HygieneFinding]) -> str:
    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    out = [f"redline hygiene — {contract_name}"]
    if not findings:
        out.append("No drafting-hygiene issues found.")
        return "\n".join(out) + "\n"
    out.append(
        f"{len(findings)} finding(s): "
        f"{counts.get('high', 0)} high, {counts.get('medium', 0)} medium, "
        f"{counts.get('low', 0)} low\n"
    )
    for f in findings:
        where = f" (line {f.line})" if f.line else ""
        out.append(f"[{f.severity}] {f.check_id}{where}")
        out.append(f"  {f.title}.")
        out.append(f"  {f.detail}\n")
    out.append(
        "Hygiene checks are heuristic — review each finding in context. "
        "Not legal advice."
    )
    return "\n".join(out) + "\n"


def render_hygiene_json(contract_name: str, findings: list[HygieneFinding]) -> str:
    return (
        json.dumps(
            {
                "contract": contract_name,
                "finding_count": len(findings),
                "findings": [
                    {
                        "check_id": f.check_id,
                        "severity": f.severity,
                        "title": f.title,
                        "detail": f.detail,
                        "line": f.line,
                    }
                    for f in findings
                ],
            },
            indent=2,
        )
        + "\n"
    )


__all__ = [
    "HygieneFinding",
    "extract_defined_terms",
    "render_hygiene_json",
    "render_hygiene_text",
    "run_hygiene",
]
