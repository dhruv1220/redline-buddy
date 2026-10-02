"""Render findings as a self-contained HTML memo a human can actually share.

The whole point of a red-flag memo is to hand it to someone — usually an
attorney. A markdown wall of text in a terminal is not that. This module
emits a single HTML file with inline CSS, zero dependencies and zero
JavaScript: it opens offline, emails cleanly, and prints well (a print
stylesheet keeps findings on one page and drops nothing essential).

Everything derived from the contract or playbook is escaped — this file
may carry the reviewed party's hostile text, so markup injection gets
neutralized at render time.
"""

from __future__ import annotations

import html as _html

from .review import Finding
from .score import risk_grade, risk_score, severity_counts

_DISCLAIMER_HTML = (
    "<strong>Not legal advice.</strong> redline-buddy runs deterministic "
    "heuristic checks, not a lawyer's judgment. Treat this memo as a draft "
    "for attorney review before you sign anything."
)

_SEVERITY_BADGE: dict[str, tuple[str, str]] = {
    "critical": ("sev-critical", "🔴 CRITICAL"),
    "high": ("sev-high", "🟠 HIGH"),
    "medium": ("sev-medium", "🟡 MEDIUM"),
    "low": ("sev-low", "🟢 LOW"),
}


def _esc(text: str | None) -> str:
    return _html.escape(text or "", quote=True)


def _css() -> str:
    return """
body{font-family:system-ui,-apple-system,sans-serif;max-width:70ch;margin:2rem auto;
  padding:0 1rem;color:#1a1a1a;line-height:1.5}
h1{font-size:1.5rem} h2{font-size:1.2rem;margin-top:2rem} h3{font-size:1rem}
.risk{border-radius:8px;padding:0.75rem 1rem;margin:1.25rem 0;border:1px solid #ddd;
  border-left:6px solid #999;font-size:1.05rem}
.rA{border-left-color:#067647} .rB{border-left-color:#3d7a2e}
.rC{border-left-color:#b7791f} .rD{border-left-color:#b42318} .rF{border-left-color:#7a1f1f}
.gA{color:#067647;font-weight:bold} .gB{color:#3d7a2e;font-weight:bold}
.gC{color:#b7791f;font-weight:bold} .gD{color:#b42318;font-weight:bold}
.gF{color:#7a1f1f;font-weight:bold}
.disclaimer{background:#fff8e1;border:1px solid #e6c200;border-radius:8px;
  padding:0.75rem 1rem;font-size:0.9rem;margin:1rem 0}
.finding{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}
.badge{font-weight:bold;display:inline-block;margin-bottom:0.25rem}
.sev-critical{color:#7a1f1f} .sev-high{color:#b42318}
.sev-medium{color:#b7791f} .sev-low{color:#067647}
blockquote.excerpt{border-left:3px solid #ccc;margin:0.75rem 0;padding:0.25rem 0.75rem;
  color:#333;font-style:italic}
.fallback{background:#f6f8fa;border:1px solid #ddd;border-radius:6px;
  padding:0.75rem;font-family:ui-monospace,monospace;font-size:0.85rem;
  white-space:pre-wrap;word-wrap:break-word}
.ok{background:#f0fdf4;border:1px solid #067647;border-radius:8px;padding:1rem}
table.summary{border-collapse:collapse;width:100%;font-size:0.85rem;margin:1rem 0}
table.summary th,table.summary td{border:1px solid #ddd;padding:0.4rem 0.6rem;text-align:left}
table.summary th{background:#f6f8fa}
a{color:#1a56db}
footer{color:#666;font-size:0.8rem;margin-top:2rem}
.index{background:#f6f8fa;border:1px solid #ddd;border-radius:8px;padding:0.75rem 1rem}
@media print{
  body{max-width:none;margin:0;padding:0}
  .finding{break-inside:avoid}
  a{color:inherit;text-decoration:none}
}
"""


def _risk_banner(findings: list[Finding], rule_count: int | None = None) -> str:
    score = risk_score(findings)
    grade = risk_grade(score)
    counts = severity_counts(findings)
    breakdown = (
        ", ".join(f"{n} {sev}" for sev, n in counts.items() if n) or "no findings"
    )
    suffix = f" ({rule_count} rules checked)" if rule_count else ""
    return (
        f'<div class="risk r{grade}">Risk score: <b>{score}/100</b> &middot; '
        f'<span class="g{grade}">Grade {grade}</span> &mdash; '
        f"{_esc(breakdown)}{_esc(suffix)}.</div>"
    )


def _finding_section(f: Finding, num: int) -> str:
    sev_class, badge = _SEVERITY_BADGE.get(f.severity, ("", f.severity.upper()))
    parts = [
        '<div class="finding">',
        (
            f'<div class="badge {sev_class}">{_esc(badge)} &mdash; '
            f"Rule <code>{_esc(f.rule_id)}</code></div>"
        ),
        f"<h3>{num}. {_esc(f.title)}</h3>",
    ]
    if f.excerpt:
        parts.append(f'<blockquote class="excerpt">{_esc(f.excerpt)}</blockquote>')
    parts.append(f"<p><strong>Why it matters:</strong> {_esc(f.why)}</p>")
    fallback = f.fallback or f.suggestion
    if fallback:
        parts.append("<p><strong>Suggested fallback language:</strong></p>")
        parts.append(f'<div class="fallback">{_esc(fallback)}</div>')
    parts.append("</div>")
    return "\n".join(parts)


def _memo_body(
    contract_name: str,
    playbook_name: str,
    findings: list[Finding],
    rule_count: int | None = None,
) -> str:
    """Inner HTML shared by the single-review document and batch sections."""
    parts = [
        f"<h1>Red-flag memo: {_esc(contract_name)}</h1>",
        _risk_banner(findings, rule_count),
        (
            f"<p>Playbook: <code>{_esc(playbook_name)}</code> &mdash; "
            f"{len(findings)} finding(s).</p>"
        ),
        f'<div class="disclaimer">{_DISCLAIMER_HTML}</div>',
    ]
    if not findings:
        parts += [
            (
                '<div class="ok"><strong>✅ No red flags.</strong> '
                "Nothing in the playbook fired on this document.</div>"
            )
        ]
    else:
        parts.append("<h2>Findings</h2>")
        for i, f in enumerate(findings, 1):
            parts.append(_finding_section(f, i))
    return "\n".join(parts)


def _document(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f"<style>{_css()}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        f'<footer><div class="disclaimer">{_DISCLAIMER_HTML}</div>'
        "<p>Generated by redline-buddy — a local-first, deterministic "
        "contract red-flag checker. No data left your machine.</p></footer>\n"
        "</body>\n</html>\n"
    )


def render_html_memo(
    contract_name: str,
    playbook_name: str,
    findings: list[Finding],
    rule_count: int | None = None,
) -> str:
    """Standalone HTML memo for a single contract review."""
    title = f"Red-flag memo: {contract_name}"
    return _document(
        title, _memo_body(contract_name, playbook_name, findings, rule_count)
    )


def render_batch_html_memo(
    results: list[tuple[str, list[Finding], str | None]],
    playbook_name: str | None,
    rule_count: int | None = None,
    per_file_playbooks: dict[str, str] | None = None,
) -> str:
    """Standalone HTML for a directory review: summary table plus per-file memos."""
    if per_file_playbooks:
        header = (
            f"Playbooks auto-selected per file &mdash; {len(results)} file(s), "
            f"{len(set(per_file_playbooks.values()))} playbook(s)."
        )
        cols = ["File", "Playbook", "Risk", "🔴", "🟠", "🟡", "🟢", "Total"]
    else:
        header = f"Playbook: <code>{_esc(playbook_name or '')}</code> &mdash; {len(results)} file(s)."
        cols = ["File", "Risk", "🔴", "🟠", "🟡", "🟢", "Total"]

    rows = []
    for i, (name, findings, error) in enumerate(results):
        cells = [f'<a href="#file-{i}">{_esc(name)}</a>']
        if per_file_playbooks:
            cells.append(f"<code>{_esc(per_file_playbooks.get(name, '—'))}</code>")
        if error:
            cells += ["—", "—", "—", "—", "—", f"⚠️ {_esc(error)}"]
        else:
            counts = severity_counts(findings)
            score = risk_score(findings)
            cells += [
                f'<span class="g{risk_grade(score)}"><b>{score} ({risk_grade(score)})</b></span>',
                str(counts.get("critical", 0)),
                str(counts.get("high", 0)),
                str(counts.get("medium", 0)),
                str(counts.get("low", 0)),
                str(len(findings)),
            ]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")

    table_head = (
        '<table class="summary"><thead><tr>'
        + "".join(f"<th>{c}</th>" for c in cols)
        + "</tr></thead><tbody>"
    )
    parts = [
        "<h1>Batch red-flag review</h1>",
        f"<p>{header}</p>",
        f'<div class="disclaimer">{_DISCLAIMER_HTML}</div>',
        "<h2>Summary</h2>",
        table_head,
        *rows,
        "</tbody></table>",
    ]
    for i, (name, findings, error) in enumerate(results):
        pb = per_file_playbooks.get(name) if per_file_playbooks else playbook_name
        parts.append(f'<section id="file-{i}">')
        if error:
            parts.append(f"<h2>{_esc(name)}</h2><p>⚠️ Skipped: {_esc(error)}</p>")
        else:
            parts.append(_memo_body(name, pb or "", findings, rule_count))
        parts.append("</section>")
    return _document("Batch red-flag review", "\n".join(parts))
