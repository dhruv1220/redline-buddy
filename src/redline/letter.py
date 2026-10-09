"""Draft a negotiation letter to the counterparty from review findings.

Deterministic and local-only: each finding's contract excerpt, plain-language
concern, requested change, and quotable fallback language becomes one numbered
change request. The output is a starting draft — not legal advice, not a
lawyer's judgment — meant for attorney review before anything is sent.
"""

from __future__ import annotations

from .review import SEVERITY_RANK, Finding

DISCLAIMER = (
    "Not legal advice. This is a machine-generated draft based on heuristic "
    "checks, not a lawyer's judgment. Have an attorney review it before you "
    "send anything."
)

_SEVERITY_LABEL = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}

_RECIPIENT_PLACEHOLDER = "[Counterparty name]"
_SENDER_PLACEHOLDER = "[Your name]"


def select_findings(
    findings: list[Finding], min_severity: str = "medium"
) -> list[Finding]:
    """Keep findings at or above ``min_severity``, ordered worst-first.

    ``review_contract`` already sorts this way, but letters built from
    hand-assembled finding lists should get the same ordering.
    """
    threshold = SEVERITY_RANK.get(min_severity, 2)
    kept = [f for f in findings if SEVERITY_RANK.get(f.severity, 9) <= threshold]
    kept.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.rule_id))
    return kept


def _h1(text: str, plain: bool) -> str:
    return text if plain else f"# {text}"


def _h2(text: str, plain: bool) -> str:
    return text if plain else f"## {text}"


def _bold(text: str, plain: bool) -> str:
    return text if plain else f"**{text}**"


def _quote(text: str, plain: bool) -> str:
    lines = text.strip().splitlines() or [""]
    if plain:
        return "\n".join(f"    {line}" for line in lines)
    return "\n".join(f"> {line}" if line.strip() else ">" for line in lines)


def _disclaimer(plain: bool) -> str:
    return DISCLAIMER if plain else f"> **Not legal advice.** {DISCLAIMER}"


def _render_no_findings(
    contract_name: str, playbook_name: str, plain: bool
) -> str:
    lines = [
        _h1(f"Draft negotiation letter — {contract_name}", plain),
        "",
        f"To: {_RECIPIENT_PLACEHOLDER} · From: {_SENDER_PLACEHOLDER}",
        "",
        f"Our review of the draft {contract_name} against the `{playbook_name}` "
        "playbook found no material issues. Subject to attorney review, we're "
        "prepared to move forward with the current draft.",
        "",
        _disclaimer(plain),
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_letter(
    contract_name: str,
    playbook_name: str,
    findings: list[Finding],
    *,
    recipient: str | None = None,
    sender: str | None = None,
    min_severity: str = "medium",
    fmt: str = "md",
) -> str:
    """Render a draft negotiation letter for ``findings``.

    ``fmt`` is ``"md"`` (default) or ``"txt"`` — plain text for pasting
    straight into an email. Findings below ``min_severity`` are omitted.
    """
    plain = fmt == "txt"
    who_to = recipient or _RECIPIENT_PLACEHOLDER
    who_from = sender or _SENDER_PLACEHOLDER
    selected = select_findings(findings, min_severity)

    if not selected:
        return _render_no_findings(contract_name, playbook_name, plain)

    n = len(selected)
    lines = [
        _h1(f"Draft negotiation letter — {contract_name}", plain),
        "",
        f"To: {who_to} · From: {who_from}",
        "",
        f"Dear {who_to},",
        "",
        f"We've reviewed the draft {contract_name} (checked against the "
        f"`{playbook_name}` playbook) and would like to request the following "
        f"{n} change{'s' if n != 1 else ''} before signing. Each one quotes "
        "the current language, explains our concern, and proposes "
        "specific replacement language where we have it.",
        "",
    ]
    for i, f in enumerate(selected, 1):
        label = _SEVERITY_LABEL.get(f.severity, f.severity.upper())
        lines += [
            _h2(f"{i}. {f.title} — {label}", plain),
            "",
            _bold("The contract says:", plain),
            "",
            _quote(f.excerpt, plain),
            "",
            _bold("Our concern:", plain),
            "",
            f.why.strip(),
            "",
            _bold("Our requested change:", plain),
            "",
            f.suggestion.strip(),
        ]
        if f.fallback.strip():
            lines += [
                "",
                _bold("Proposed language:", plain),
                "",
                _quote(f.fallback, plain),
            ]
        lines.append("")
    lines += [
        "---" if not plain else ("-" * 40),
        "",
        "We'd appreciate a revised draft reflecting these changes, and we're "
        "happy to discuss any of them.",
        "",
        f"Best regards,\n{who_from}",
        "",
        _disclaimer(plain),
    ]
    return "\n".join(lines).rstrip() + "\n"
