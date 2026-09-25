"""Render findings as a plain-language markdown memo or machine-readable JSON."""
from __future__ import annotations

import json
from dataclasses import asdict

from .review import Finding

DISCLAIMER = (
    "> **Not legal advice.** redline-buddy runs deterministic heuristic checks, "
    "not a lawyer's judgment. Treat this memo as a draft for attorney review "
    "before you sign anything."
)

_SEVERITY_BADGE = {
    "critical": "🔴 CRITICAL",
    "high": "🟠 HIGH",
    "medium": "🟡 MEDIUM",
    "low": "🟢 LOW",
}


def render_memo(contract_name: str, playbook_name: str, findings: list[Finding]) -> str:
    lines = [
        f"# Red-flag memo: {contract_name}",
        "",
        f"Playbook: `{playbook_name}` — {len(findings)} finding(s).",
        "",
        DISCLAIMER,
        "",
    ]
    if not findings:
        lines += ["## ✅ No red flags", "", "Nothing in the playbook fired on this document."]
    else:
        lines += ["## Findings", ""]
        for i, f in enumerate(findings, 1):
            badge = _SEVERITY_BADGE.get(f.severity, f.severity.upper())
            lines += [f"### {i}. [{badge}] {f.title}", ""]
            if f.excerpt:
                lines += [f"> {f.excerpt}", ""]
            lines += [f"**Why it matters:** {f.why}", ""]
            if f.suggestion:
                lines += [f"**Suggested fallback:** {f.suggestion}", ""]
    lines += ["", "---", "", DISCLAIMER, ""]
    return "\n".join(lines)


def render_diff(contract_name: str, playbook_name: str, findings: list[Finding]) -> str:
    """Redline-style diff view: each finding as a unified-diff hunk.

    `-` lines show the flagged contract language; `+` lines show the
    quotable fallback language to propose instead (or insert, when the
    rule flags a clause that is missing entirely).
    """
    lines = [
        f"# Redline: {contract_name}",
        "",
        f"Playbook: `{playbook_name}` — {len(findings)} finding(s).",
        "",
        DISCLAIMER,
        "",
    ]
    if not findings:
        lines += ["## ✅ No red flags — nothing to redline.", ""]
    else:
        lines += ["## Redline diff", ""]
        for i, f in enumerate(findings, 1):
            badge = _SEVERITY_BADGE.get(f.severity, f.severity.upper())
            lines += [f"### {i}. [{badge}] {f.title}", "", "```diff"]
            if f.excerpt:
                excerpt = f.excerpt.strip("…").strip()
                lines += [f"- {excerpt}"]
            else:
                lines += ["@@ clause missing from contract — proposed insertion @@"]
            fallback = f.fallback or f.suggestion
            if fallback:
                for fl in fallback.splitlines():
                    fl = fl.strip()
                    lines += [f"+ {fl}" if fl else "+"]
            else:
                lines += ["+ (no suggested language — see the memo for guidance)"]
            lines += ["```", ""]
    lines += ["", "---", "", DISCLAIMER, ""]
    return "\n".join(lines)


def render_json(contract_name: str, playbook_name: str, findings: list[Finding]) -> str:
    """Machine-readable findings, e.g. for CI gates: fail the build on findings."""
    return json.dumps(
        {
            "contract": contract_name,
            "playbook": playbook_name,
            "finding_count": len(findings),
            "disclaimer": "Not legal advice. Heuristic checks only — draft for attorney review.",
            "findings": [asdict(f) for f in findings],
        },
        indent=2,
    )


def _severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def render_batch_memo(
    results: list[tuple[str, list[Finding], str | None]], playbook_name: str
) -> str:
    """Summary table plus per-file memos for a directory review.

    Each result is (contract_name, findings, error); error is None on success.
    """
    lines = [
        f"# Batch red-flag review",
        "",
        f"Playbook: `{playbook_name}` — {len(results)} file(s).",
        "",
        DISCLAIMER,
        "",
        "## Summary",
        "",
        "| File | 🔴 Crit | 🟠 High | 🟡 Med | 🟢 Low | Total |",
        "|---|---|---|---|---|---|",
    ]
    for name, findings, error in results:
        if error:
            lines.append(f"| {name} | — | — | — | — | ⚠️ {error} |")
        else:
            c = _severity_counts(findings)
            lines.append(
                f"| {name} | {c['critical']} | {c['high']} | {c['medium']} "
                f"| {c['low']} | {len(findings)} |"
            )
    lines += ["", "---", ""]
    for name, findings, error in results:
        if error:
            lines += [f"# {name}", "", f"⚠️ Skipped: {error}", "", "---", ""]
        else:
            lines += [render_memo(name, playbook_name, findings), "---", ""]
    lines += [DISCLAIMER, ""]
    return "\n".join(lines)


def render_batch_json(
    results: list[tuple[str, list[Finding], str | None]], playbook_name: str
) -> str:
    """Machine-readable batch results with a per-severity summary."""
    total = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    contracts = []
    for name, findings, error in results:
        entry: dict = {"contract": name, "finding_count": len(findings)}
        if error:
            entry["error"] = error
        else:
            entry["findings"] = [asdict(f) for f in findings]
            for f in findings:
                total[f.severity] = total.get(f.severity, 0) + 1
        contracts.append(entry)
    return json.dumps(
        {
            "playbook": playbook_name,
            "file_count": len(results),
            "total_findings": sum(total.values()),
            "by_severity": total,
            "disclaimer": "Not legal advice. Heuristic checks only — draft for attorney review.",
            "contracts": contracts,
        },
        indent=2,
    )
