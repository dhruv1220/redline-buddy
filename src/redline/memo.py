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
