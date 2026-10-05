"""Word redline export: the reviewed contract as a .docx with tracked changes.

``--format docx`` turns a review into a counter-draft you can actually send:
the full contract text with each finding's flagged language struck through
(``w:del``) and the playbook's quotable fallback language inserted after it
(``w:ins``), so Word shows every proposed edit under Review → All Markup.
Findings the engine couldn't locate verbatim, plus missing-clause findings
that have no excerpt at all, land in a "Proposed additions" section as
insertions; every finding is also listed in a summary table at the end.

python-docx has no high-level tracked-changes API, so the ``w:ins``/``w:del``
elements are built directly with oxml. Insertions get underline + blue run
formatting and deletions get strikethrough so the markup reads even with
revision display off; the elements themselves carry the real revision
semantics (author ``redline-buddy``).
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .review import Finding
from .score import risk_label, severity_counts

if TYPE_CHECKING:
    from .compare import Comparison

REVISION_AUTHOR = "redline-buddy"

DISCLAIMER = (
    "Not legal advice. redline-buddy runs deterministic heuristic checks, "
    "not a lawyer's judgment. Treat this redline as a draft for attorney "
    "review before you sign anything."
)

_SEVERITY_LABEL = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}

_WS_RUN = re.compile(r"\s+")
_PARA_BREAK = re.compile(r"\n[ \t]*\n")


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to single spaces, keeping an index map.

    Returns ``(normalized, mapping)`` where ``mapping[i]`` is the offset in
    the original text of ``normalized[i]``. Lets us find an excerpt in the
    whitespace-tolerant normalized text and map the hit back to exact
    original offsets for the tracked-change markup.
    """
    out: list[str] = []
    mapping: list[int] = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            # One space stands in for the whole run (unless at an edge,
            # where _normalize-style stripping drops it entirely).
            j = i
            while j < n and text[j].isspace():
                j += 1
            if out and j < n:
                out.append(" ")
                mapping.append(i)
            i = j
        else:
            out.append(text[i])
            mapping.append(i)
            i += 1
    return "".join(out), mapping


def _locate_excerpt(text: str, excerpt: str) -> tuple[int, int] | None:
    """Original-text ``(start, end)`` offsets for a finding's excerpt.

    Excerpts come from the whitespace-normalized review text and are trimmed
    with "…" at the edges, so we normalize the same way, search, and map the
    hit back. Returns None when the language can't be located verbatim
    (e.g. truncated by the excerpt length cap).
    """
    core = excerpt.strip("…").strip()
    if not core:
        return None
    norm_text, mapping = _normalize_with_map(text)
    norm_core = _WS_RUN.sub(" ", core).strip()
    if not norm_core:
        return None
    at = norm_text.find(norm_core)
    if at < 0:
        return None
    start = mapping[at]
    end = mapping[at + len(norm_core) - 1] + 1
    return start, end


def _plan_edits(
    text: str, findings: list[Finding]
) -> tuple[list[tuple[int, int, Finding]], list[Finding], list[Finding]]:
    """Split findings into inline edits, missing-clause additions, and orphans.

    Returns ``(edits, additions, orphans)`` where edits are non-overlapping
    ``(start, end, finding)`` spans (findings arrive severity-sorted, so on
    overlap the more severe finding wins), additions are findings with no
    excerpt (missing clauses → proposed insertions), and orphans are findings
    whose excerpt couldn't be located verbatim (summary table only).
    """
    edits: list[tuple[int, int, Finding]] = []
    additions: list[Finding] = []
    orphans: list[Finding] = []
    for finding in findings:
        if not finding.excerpt.strip("…").strip():
            additions.append(finding)
            continue
        span = _locate_excerpt(text, finding.excerpt)
        if span is None:
            orphans.append(finding)
            continue
        start, end = span
        if any(start < e_end and e_start < end for e_start, e_end, _ in edits):
            orphans.append(finding)
            continue
        edits.append((start, end, finding))
    edits.sort(key=lambda e: e[0])
    return edits, additions, orphans


def _revision_element(tag: str, author: str, date: str) -> OxmlElement:
    rev = OxmlElement(f"w:{tag}")
    rev.set(qn("w:author"), author)
    rev.set(qn("w:date"), date)
    return rev


def _append_revision_run(
    paragraph: Paragraph, text: str, kind: str, author: str, date: str
) -> None:
    """Append ``text`` as a tracked-change run (``kind`` "ins" or "del")."""
    rev = _revision_element(kind, author, date)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    if kind == "del":
        strike = OxmlElement("w:strike")
        strike.set(qn("w:val"), "true")
        props.append(strike)
    else:
        underline = OxmlElement("w:u")
        underline.set(qn("w:val"), "single")
        props.append(underline)
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "0563C1")
        props.append(color)
    run.append(props)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    run.append(t)
    rev.append(run)
    paragraph._p.append(rev)


def _append_runs(
    paragraph: Paragraph, text: str, kind: str, author: str, date: str
) -> None:
    """Append ``text`` to a paragraph; newlines become line breaks."""
    for i, line in enumerate(text.split("\n")):
        if i:
            paragraph.add_run().add_break()
        if not line:
            continue
        if kind == "text":
            paragraph.add_run(line)
        else:
            _append_revision_run(paragraph, line, kind, author, date)


def _split_paragraphs(text: str) -> list[tuple[str, int]]:
    """Split on blank lines, keeping each paragraph's original offset."""
    paras: list[tuple[str, int]] = []
    pos = 0
    for m in _PARA_BREAK.finditer(text):
        paras.append((text[pos : m.start()], pos))
        pos = m.end()
    paras.append((text[pos:], pos))
    return paras


def _risk_line(findings: list[Finding], rule_count: int | None) -> str:
    counts = severity_counts(findings)
    parts = [f"{n} {sev}" for sev, n in counts.items() if n]
    breakdown = ", ".join(parts) if parts else "no findings"
    suffix = f" ({rule_count} rules checked)" if rule_count else ""
    return f"Risk score: {risk_label(findings)} — {breakdown}{suffix}."


def _add_finding_row(table, finding: Finding) -> None:
    cells = table.add_row().cells
    cells[0].text = _SEVERITY_LABEL.get(finding.severity, finding.severity.upper())
    cells[1].text = finding.title
    cells[2].text = finding.why
    fallback = finding.fallback or finding.suggestion
    cells[3].text = fallback or "(no suggested language — see above)"


_TRACKED_NOTE = (
    "Deletions are struck through; insertions are underlined. In Word, "
    "use Review → All Markup to accept or reject each edit."
)


def _render_tracked_body(
    doc: Document,
    text: str,
    findings: list[Finding],
    date: str,
    heading: str,
) -> tuple[list[Finding], list[Finding]]:
    """Render ``text`` with finding excerpts struck and fallbacks inserted.

    Returns ``(additions, orphans)`` for the caller to place in follow-on
    sections: findings with no excerpt (missing clauses) and findings whose
    excerpt couldn't be located verbatim.
    """
    edits, additions, orphans = _plan_edits(text, findings)
    doc.add_heading(heading, level=2)
    doc.add_paragraph(_TRACKED_NOTE)
    for para_text, para_offset in _split_paragraphs(text):
        para_end = para_offset + len(para_text)
        # An excerpt can span a blank line in the raw text (excerpts are
        # built from whitespace-normalized text), so intersect each edit
        # with this paragraph and emit the fallback insertion once, after
        # the edit's final chunk.
        events: list[tuple[int, int, str, Finding]] = []  # (start, end, kind, finding)
        for s, e, finding in edits:
            if e <= para_offset or s >= para_end:
                continue
            cs, ce = max(s, para_offset) - para_offset, min(e, para_end) - para_offset
            events.append((cs, ce, "del", finding))
            if e <= para_end:
                events.append((ce, ce, "ins", finding))
        events.sort(key=lambda ev: (ev[0], 0 if ev[2] == "del" else 1))
        p = doc.add_paragraph()
        cursor = 0
        for rs, re_, kind, finding in events:
            if rs > cursor:
                _append_runs(p, para_text[cursor:rs], "text", REVISION_AUTHOR, date)
            if kind == "del":
                _append_runs(p, para_text[rs:re_], "del", REVISION_AUTHOR, date)
            else:
                fallback = finding.fallback or finding.suggestion
                if fallback:
                    _append_runs(p, fallback, "ins", REVISION_AUTHOR, date)
            cursor = max(cursor, re_)
        if cursor < len(para_text):
            _append_runs(p, para_text[cursor:], "text", REVISION_AUTHOR, date)
    return additions, orphans


def _render_additions(doc: Document, additions: list[Finding], date: str) -> None:
    if not additions:
        return
    doc.add_heading("Proposed additions", level=2)
    doc.add_paragraph(
        "These clauses are missing from the contract. Each is inserted "
        "below as a tracked change — place it in the right section "
        "before sending."
    )
    for finding in additions:
        badge = _SEVERITY_LABEL.get(finding.severity, finding.severity.upper())
        doc.add_heading(f"[{badge}] {finding.title}", level=3)
        if finding.why:
            doc.add_paragraph(finding.why)
        fallback = finding.fallback or finding.suggestion
        p = doc.add_paragraph()
        if fallback:
            _append_runs(p, fallback, "ins", REVISION_AUTHOR, date)
        else:
            p.add_run("(no suggested language — see the summary table)")


def _render_summary_table(
    doc: Document,
    findings: list[Finding],
    orphans: list[Finding],
    heading: str = "Findings summary",
) -> None:
    doc.add_heading(heading, level=2)
    if not findings:
        doc.add_paragraph("No red flags — nothing to redline.")
    else:
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = (
            "Severity",
            "Finding",
            "Why it matters",
            "Proposed language",
        )
        for finding in findings:
            _add_finding_row(table, finding)
        if orphans:
            doc.add_paragraph(
                "Note: the flagged language for "
                + ", ".join(f'"{f.title}"' for f in orphans)
                + " could not be located verbatim in the extracted text, so "
                "it is not marked inline — see the proposed language above."
            )
def render_redline_docx(
    contract_name: str,
    text: str,
    playbook_name: str,
    findings: list[Finding],
    rule_count: int | None = None,
) -> bytes:
    """Build a tracked-changes Word redline of the reviewed contract.

    Returns the ``.docx`` file bytes; the caller decides where to write them.
    """
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = Document()
    doc.core_properties.title = f"Redline: {contract_name}"
    doc.core_properties.author = REVISION_AUTHOR

    doc.add_heading(f"Redline: {contract_name}", level=1)
    doc.add_paragraph(_risk_line(findings, rule_count))
    doc.add_paragraph(f"Playbook: {playbook_name} — {len(findings)} finding(s).")
    disclaimer = doc.add_paragraph()
    disclaimer.add_run(DISCLAIMER).italic = True

    additions, orphans = _render_tracked_body(
        doc, text, findings, date, "Redlined contract — tracked changes"
    )
    _render_additions(doc, additions, date)
    _render_summary_table(doc, findings, orphans)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_compare_docx(
    cmp: Comparison,
    new_text: str,
    rule_count: int | None = None,
) -> bytes:
    """Build a tracked-changes Word redline of a negotiation round.

    The new draft is rendered with gained and reworded findings as tracked
    changes (their round-2 language struck, fallback inserted), followed by
    the concessions won, the paragraph-level text changes, and the new
    draft's findings summary. Returns the ``.docx`` file bytes.
    """
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = Document()
    doc.core_properties.title = f"Redline compare: {cmp.old_name} → {cmp.new_name}"
    doc.core_properties.author = REVISION_AUTHOR

    doc.add_heading(f"Redline compare: {cmp.old_name} → {cmp.new_name}", level=1)
    movement = []
    if cmp.gained:
        movement.append(f"{len(cmp.gained)} new flag(s)")
    if cmp.resolved:
        movement.append(f"{len(cmp.resolved)} resolved")
    if cmp.reworded:
        movement.append(f"{len(cmp.reworded)} reworded")
    doc.add_paragraph(
        f"Risk: {risk_label(cmp.findings_old)} → {risk_label(cmp.findings_new)}"
        + (f" — {', '.join(movement)}." if movement else " — no finding changes.")
    )
    doc.add_paragraph(f"Playbook: {cmp.playbook_name}.")
    disclaimer = doc.add_paragraph()
    disclaimer.add_run(DISCLAIMER).italic = True

    flagged = list(cmp.gained) + [r.after for r in cmp.reworded]
    additions, orphans = _render_tracked_body(
        doc, new_text, flagged, date, "Round redline — new and reworded flags"
    )
    _render_additions(doc, additions, date)

    if cmp.resolved:
        doc.add_heading("Concessions won — resolved flags", level=2)
        doc.add_paragraph(
            "These fired on the earlier draft and no longer fire — "
            "their language was fixed or dropped."
        )
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text = (
            "Severity",
            "Finding",
            "Why it mattered",
        )
        for finding in cmp.resolved:
            cells = table.add_row().cells
            cells[0].text = _SEVERITY_LABEL.get(finding.severity, finding.severity.upper())
            cells[1].text = finding.title
            cells[2].text = finding.why

    if cmp.changes:
        doc.add_heading("Text changes", level=2)
        doc.add_paragraph(
            "Paragraph-level changes between the drafts, as tracked changes."
        )
        for change in cmp.changes:
            p = doc.add_paragraph()
            label = p.add_run(f"[{change.kind}] ")
            label.bold = True
            if change.kind == "added":
                _append_runs(p, change.new, "ins", REVISION_AUTHOR, date)
            elif change.kind == "removed":
                _append_runs(p, change.old, "del", REVISION_AUTHOR, date)
            else:
                _append_runs(p, change.old, "del", REVISION_AUTHOR, date)
                _append_runs(p, change.new, "ins", REVISION_AUTHOR, date)

    _render_summary_table(doc, cmp.findings_new, orphans, heading="Findings summary — new draft")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
