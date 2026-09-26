"""Render findings as a plain-language markdown memo or machine-readable JSON."""
from __future__ import annotations

import json
from dataclasses import asdict

from .compare import Comparison
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
        "# Batch red-flag review",
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


def _finding_block(f: Finding, num: int) -> list[str]:
    badge = _SEVERITY_BADGE.get(f.severity, f.severity.upper())
    lines = [f"### {num}. [{badge}] {f.title}", ""]
    if f.excerpt:
        lines += [f"> {f.excerpt}", ""]
    lines += [f"**Why it matters:** {f.why}", ""]
    fallback = f.fallback or f.suggestion
    if fallback:
        lines += [f"**Suggested fallback:** {fallback}", ""]
    return lines


def render_compare_memo(cmp: Comparison) -> str:
    """Markdown memo for a two-draft comparison: what changed, what risk changed."""
    added = sum(1 for c in cmp.changes if c.kind == "added")
    removed = sum(1 for c in cmp.changes if c.kind == "removed")
    modified = sum(1 for c in cmp.changes if c.kind == "modified")
    lines = [
        f"# Contract comparison: {cmp.old_name} → {cmp.new_name}",
        "",
        f"Playbook: `{cmp.playbook_name}`.",
        "",
        DISCLAIMER,
        "",
        "## Summary",
        "",
        (
            f"- Text changes: **{len(cmp.changes)}** "
            f"({added} added, {removed} removed, {modified} reworded)"
        ),
        (
            f"- Findings: **{len(cmp.findings_old)}** → **{len(cmp.findings_new)}** — "
            f"🚨 {len(cmp.gained)} new red flag(s), "
            f"✅ {len(cmp.resolved)} resolved, "
            f"🔁 {len(cmp.reworded)} reworded but still flagged"
        ),
        "",
    ]

    if cmp.gained:
        lines += ["## 🚨 New red flags introduced in this round", ""]
        for i, f in enumerate(cmp.gained, 1):
            lines += _finding_block(f, i)
    else:
        lines += ["## 🚨 New red flags introduced in this round", "",
                  "None — the new draft introduces no new playbook findings.", ""]

    if cmp.resolved:
        lines += ["## ✅ Resolved this round", ""]
        for f in cmp.resolved:
            badge = _SEVERITY_BADGE.get(f.severity, f.severity.upper())
            lines += [f"- [{badge}] {f.title}"]
        lines += [""]
    else:
        lines += ["## ✅ Resolved this round", "", "None.", ""]

    if cmp.reworded:
        lines += ["## 🔁 Reworded but still flagged", ""]
        for i, rw in enumerate(cmp.reworded, 1):
            badge = _SEVERITY_BADGE.get(rw.after.severity, rw.after.severity.upper())
            lines += [f"### {i}. [{badge}] {rw.after.title}", ""]
            lines += [f"- Before: {rw.before.excerpt or '(clause missing)'}", ""]
            lines += [f"- Now: {rw.after.excerpt or '(clause missing)'}", ""]
    else:
        lines += ["## 🔁 Reworded but still flagged", "", "None.", ""]

    if cmp.changes:
        lines += ["## 📝 Text changes", ""]
        for i, ch in enumerate(cmp.changes, 1):
            kind_label = {"added": "paragraph added",
                          "removed": "paragraph removed",
                          "modified": "paragraph reworded"}[ch.kind]
            lines += [f"### Change {i} — {kind_label}", "", "```diff"]
            if ch.kind in ("removed", "modified"):
                for ln in ch.old.splitlines():
                    lines += [f"- {ln}"]
            if ch.kind in ("added", "modified"):
                for ln in ch.new.splitlines():
                    lines += [f"+ {ln}"]
            lines += ["```", ""]
    else:
        lines += ["## 📝 Text changes", "",
                  "No text changes — the documents are identical.", ""]

    lines += ["", "---", "", DISCLAIMER, ""]
    return "\n".join(lines)


def render_compare_json(cmp: Comparison) -> str:
    """Machine-readable comparison, e.g. for CI gates on negotiation rounds."""
    return json.dumps(
        {
            "old": cmp.old_name,
            "new": cmp.new_name,
            "playbook": cmp.playbook_name,
            "summary": {
                "changes": {
                    "total": len(cmp.changes),
                    "added": sum(1 for c in cmp.changes if c.kind == "added"),
                    "removed": sum(1 for c in cmp.changes if c.kind == "removed"),
                    "modified": sum(1 for c in cmp.changes if c.kind == "modified"),
                },
                "findings_old": len(cmp.findings_old),
                "findings_new": len(cmp.findings_new),
                "gained": len(cmp.gained),
                "resolved": len(cmp.resolved),
                "reworded": len(cmp.reworded),
            },
            "gained": [asdict(f) for f in cmp.gained],
            "resolved": [asdict(f) for f in cmp.resolved],
            "reworded": [
                {"before": asdict(rw.before), "after": asdict(rw.after)}
                for rw in cmp.reworded
            ],
            "changes": [
                {"kind": c.kind, "old": c.old, "new": c.new} for c in cmp.changes
            ],
            "disclaimer": "Not legal advice. Heuristic checks only — draft for attorney review.",
        },
        indent=2,
    )
