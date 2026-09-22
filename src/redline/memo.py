"""Render findings as a plain-language markdown memo."""
from __future__ import annotations

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
