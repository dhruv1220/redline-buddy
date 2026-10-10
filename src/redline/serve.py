"""Minimal local web UI: paste or upload a contract, pick a playbook, get the memo.

    redline serve [--port 8000]

Stdlib only (http.server) — no new dependencies. Binds to 127.0.0.1 by
default: everything still stays on your machine.
"""
from __future__ import annotations

import html
import http.server
import re
import urllib.parse
from pathlib import Path

from .compare import compare_contracts
from .hygiene import run_hygiene
from .ingest import IngestionError, extract_text
from .letter import (
    render_followup,
    render_followup_docx,
    render_letter,
    render_letter_docx,
)
from .memo import render_diff
from .playbook import PlaybookError, bundled_playbooks_dir, load_playbook
from .redline_docx import render_redline_docx
from .review import review_contract
from .score import risk_grade, risk_label, risk_score, severity_counts

PLAYBOOKS_DIR = bundled_playbooks_dir()

# The most recent successful review, so GET /download.docx can serve it.
# The most recent successful letter draft, so GET /letter.docx can serve it.
# The most recent successful follow-up draft, so GET /followup.docx can serve it.
# Single-user local server: one slot is enough.
_last_review: dict = {}
_last_letter: dict = {}
_last_followup: dict = {}

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>redline-buddy</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:70ch;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
textarea{{width:100%;height:14rem;font:0.85rem/1.4 monospace}}
pre.diff{{background:#f6f8fa;padding:1rem;overflow-x:auto;font-size:0.8rem}}
pre.diff .del{{color:#b42318}} pre.diff .add{{color:#067647}}
.finding{{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}}
.checkid{{color:#666;font-size:0.85rem}}
.sevfilter{{margin:1rem 0}}.sevfilter label{{margin-right:1rem}}
.risk{{border-radius:8px;padding:0.75rem 1rem;margin:1rem 0;border:1px solid #ddd;border-left:6px solid #999;font-size:1.05rem}}
.risk .gA{{color:#067647;font-weight:bold}} .risk .gB{{color:#3d7a2e;font-weight:bold}}
.risk .gC{{color:#b7791f;font-weight:bold}} .risk .gD{{color:#b42318;font-weight:bold}}
.risk .gF{{color:#7a1f1f;font-weight:bold}}
.risk.rA{{border-left-color:#067647}} .risk.rB{{border-left-color:#3d7a2e}}
.risk.rC{{border-left-color:#b7791f}} .risk.rD{{border-left-color:#b42318}}
.risk.rF{{border-left-color:#7a1f1f}}
button{{cursor:pointer}}
.badge{{font-weight:bold}} .warn{{background:#fff8e1;border:1px solid #e6c200;border-radius:8px;padding:1rem}}
footer{{color:#666;font-size:0.8rem;margin-top:2rem}}
</style></head>
<body>
<h1>redline-buddy</h1>
<p>Local-first contract red-flag checker. Nothing leaves your machine.</p>
<form method="post" action="/review" enctype="multipart/form-data">
<label>Contract text (paste):<br><textarea name="text"></textarea></label><br><br>
<label>…or upload a file: <input type="file" name="contract_file"></label><br><br>
<label>Mode: <select name="mode">
<option value="review">red-flag review</option>
<option value="hygiene">drafting hygiene</option>
<option value="letter">negotiation letter</option>
<option value="followup">round-2 follow-up letter</option>
</select></label>
<label>Earlier draft (follow-up mode — paste):<br><textarea name="text_old" style="height:6rem"></textarea></label><br><br>
<label>…or upload the earlier draft: <input type="file" name="contract_file_old"></label><br><br>
<label>Playbook: <select name="playbook">{options}</select></label>
<label>To (letter): <input type="text" name="recipient" size="18" placeholder="Counterparty"></label>
<label>From (letter): <input type="text" name="sender" size="18" placeholder="Your name"></label>
<label>View: <select name="format">
<option value="memo">memo</option><option value="diff">redline diff</option>
</select></label>
<label><input type="checkbox" name="ocr" value="1"> OCR scanned PDFs</label>
<button type="submit">Review</button>
</form>
<hr>{result}
<footer>Not legal advice. Heuristic checks only &mdash; a draft for attorney review.</footer>
</body></html>"""

_SEV = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}


def _playbook_options(selected: str = "saas-vendor") -> str:
    opts = []
    for p in sorted(PLAYBOOKS_DIR.glob("*.yaml")):
        try:
            desc = load_playbook(p).description.strip()
        except PlaybookError:
            desc = ""
        label = p.stem if not desc else f"{p.stem} — {desc[:80]}"
        sel = " selected" if p.stem == selected else ""
        opts.append(f'<option value="{p.stem}"{sel}>{html.escape(label)}</option>')
    return "\n".join(opts)


_RESULT_JS = """<script>
function copyFb(id, btn){var t=document.getElementById(id);if(!t||!t.value)return;
navigator.clipboard.writeText(t.value).then(function(){var old=btn.textContent;
btn.textContent='Copied \\u2713';setTimeout(function(){btn.textContent=old;},1500);});}
document.querySelectorAll('[data-sev-toggle]').forEach(function(cb){
cb.addEventListener('change',function(){var sev=cb.getAttribute('data-sev-toggle');
document.querySelectorAll('.finding[data-sev="'+sev+'"]').forEach(function(el){
el.style.display=cb.checked?'':'none';});});});
</script>"""


def _render_result_html(contract_name: str, playbook: str, findings, fmt: str,
                          rule_count: int | None = None) -> str:
    if fmt == "diff":
        md = render_diff(contract_name, playbook, findings, rule_count)
        out = []
        for line in md.splitlines():
            esc = html.escape(line)
            if line.startswith("- "):
                out.append(f'<div class="del">{esc}</div>')
            elif line.startswith("+ "):
                out.append(f'<div class="add">{esc}</div>')
            elif line.startswith("```"):
                continue
            elif line.startswith("### "):
                out.append(f"<h3>{esc[4:]}</h3>")
            elif line.startswith("## "):
                out.append(f"<h2>{esc[3:]}</h2>")
            elif line.startswith("# "):
                out.append(f"<h2>{esc[2:]}</h2>")
            elif line.startswith("> "):
                out.append(f"<blockquote>{esc[2:]}</blockquote>")
            elif esc.strip():
                out.append(f"<p>{esc}</p>")
        return '<pre class="diff">' + "\n".join(out) + "</pre>"
    score = risk_score(findings)
    grade = risk_grade(score)
    counts = severity_counts(findings)
    breakdown = ", ".join(
        f"{n} {sev}" for sev, n in counts.items() if n
    ) or "no findings"
    banner = (
        f'<div class="risk r{grade}">Risk score: <b>{score}/100</b> &middot; '
        f'<span class="g{grade}">Grade {grade}</span> &mdash; '
        f"{html.escape(breakdown)}</div>"
    )
    blocks = [(f"<h2>Red-flag memo: {html.escape(contract_name)} "
               f"— {len(findings)} finding(s) ({html.escape(playbook)})</h2>"),
              banner]
    if not findings:
        blocks.append('<div class="finding">✅ <b>No red flags.</b></div>')
    else:
        sevs = list(dict.fromkeys(f.severity for f in findings))
        toggles = " ".join(
            f'<label><input type="checkbox" data-sev-toggle="{html.escape(s)}" checked> '
            f"{html.escape(s)}</label>"
            for s in sevs
        )
        blocks.append(f'<div class="sevfilter">Show: {toggles}</div>')
    for i, f in enumerate(findings):
        badge = _SEV.get(f.severity, f.severity.upper())
        copy_btn = ""
        if f.fallback:
            # Fallback text lives HTML-escaped in a hidden textarea: reading
            # .value gives the raw clause back, and quotes can't break out.
            copy_btn = (
                f'<textarea id="fb-{i}" hidden>{html.escape(f.fallback)}</textarea>'
                f'<button type="button" onclick="copyFb(\'fb-{i}\', this)">'
                "Copy fallback</button>"
            )
        blocks.append(
            f'<div class="finding" data-sev="{html.escape(f.severity)}">'
            f'<span class="badge">{badge}</span> '
            f"<b>{html.escape(f.title)}</b>"
            + (f"<blockquote>{html.escape(f.excerpt)}</blockquote>" if f.excerpt else "")
            + f"<p><b>Why it matters:</b> {html.escape(f.why)}</p>"
            + (f"<p><b>Suggested fallback:</b> {html.escape(f.fallback or f.suggestion)}</p>"
               if (f.fallback or f.suggestion) else "")
            + copy_btn
            + "</div>"
        )
    blocks.append(_RESULT_JS)
    return "\n".join(blocks)


def review_to_html(
    text: str, playbook_name: str, fmt: str, contract_name: str = "pasted contract"
) -> str:
    """Run a review and render the result fragment. Raises ValueError on bad input."""
    pb_path = PLAYBOOKS_DIR / f"{playbook_name}.yaml"
    try:
        playbook = load_playbook(pb_path)
    except PlaybookError as exc:
        raise ValueError(f"bad playbook: {exc}") from exc
    if not text.strip():
        raise ValueError("paste some contract text or upload a file first")
    findings = review_contract(text, playbook)
    return _render_result_html(contract_name, playbook.name, findings, fmt,
                             len(playbook.rules))


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _letter_md_to_html(md: str) -> str:
    """Convert the letter's markdown (headings, quotes, bold) to an HTML fragment."""
    out = []
    for line in md.splitlines():
        esc = _BOLD_RE.sub(r"<b>\1</b>", html.escape(line))
        if line.startswith("# "):
            out.append(f"<h2>{esc[2:]}</h2>")
        elif line.startswith("## "):
            out.append(f"<h3>{esc[3:]}</h3>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{esc[2:]}</blockquote>")
        elif line == ">":
            continue
        elif line.strip() == "---":
            out.append("<hr>")
        elif esc.strip():
            out.append(f"<p>{esc}</p>")
    return "\n".join(out)


def letter_to_html(
    text: str,
    playbook_name: str,
    contract_name: str = "pasted contract",
    recipient: str | None = None,
    sender: str | None = None,
) -> str:
    """Run a review and render the draft negotiation letter as an HTML fragment.

    Raises ValueError on bad input.
    """
    pb_path = PLAYBOOKS_DIR / f"{playbook_name}.yaml"
    try:
        playbook = load_playbook(pb_path)
    except PlaybookError as exc:
        raise ValueError(f"bad playbook: {exc}") from exc
    if not text.strip():
        raise ValueError("paste some contract text or upload a file first")
    findings = review_contract(text, playbook)
    md = render_letter(
        contract_name,
        playbook.name,
        findings,
        recipient=recipient or None,
        sender=sender or None,
    )
    return _letter_md_to_html(md)


def letter_to_docx(
    text: str,
    playbook_name: str,
    contract_name: str = "pasted contract",
    recipient: str | None = None,
    sender: str | None = None,
) -> bytes:
    """Run a review and render the draft negotiation letter as a .docx.

    Raises ValueError on bad input.
    """
    pb_path = PLAYBOOKS_DIR / f"{playbook_name}.yaml"
    try:
        playbook = load_playbook(pb_path)
    except PlaybookError as exc:
        raise ValueError(f"bad playbook: {exc}") from exc
    if not text.strip():
        raise ValueError("paste some contract text or upload a file first")
    findings = review_contract(text, playbook)
    return render_letter_docx(
        contract_name,
        playbook.name,
        findings,
        recipient=recipient or None,
        sender=sender or None,
    )


def followup_to_html(
    old_text: str,
    new_text: str,
    playbook_name: str,
    old_name: str = "earlier draft",
    new_name: str = "pasted contract",
    recipient: str | None = None,
    sender: str | None = None,
) -> str:
    """Compare two drafts and render the round-2 follow-up letter as HTML.

    Raises ValueError on bad input.
    """
    cmp = _compare_or_raise(
        old_text, new_text, playbook_name, old_name, new_name, "follow-up"
    )
    md = render_followup(
        cmp,
        recipient=recipient or None,
        sender=sender or None,
    )
    return _letter_md_to_html(md)


def followup_to_docx(
    old_text: str,
    new_text: str,
    playbook_name: str,
    old_name: str = "earlier draft",
    new_name: str = "pasted contract",
    recipient: str | None = None,
    sender: str | None = None,
) -> bytes:
    """Compare two drafts and render the round-2 follow-up letter as a .docx.

    Raises ValueError on bad input.
    """
    cmp = _compare_or_raise(
        old_text, new_text, playbook_name, old_name, new_name, "follow-up"
    )
    return render_followup_docx(
        cmp,
        recipient=recipient or None,
        sender=sender or None,
    )


def _compare_or_raise(
    old_text: str,
    new_text: str,
    playbook_name: str,
    old_name: str,
    new_name: str,
    what: str,
):
    """Load the playbook and compare two drafts; ValueError on bad input."""
    pb_path = PLAYBOOKS_DIR / f"{playbook_name}.yaml"
    try:
        playbook = load_playbook(pb_path)
    except PlaybookError as exc:
        raise ValueError(f"bad playbook: {exc}") from exc
    if not old_text.strip():
        raise ValueError(
            f"paste the earlier draft too — the {what} needs both rounds"
        )
    if not new_text.strip():
        raise ValueError("paste some contract text or upload a file first")
    return compare_contracts(old_name, new_name, old_text, new_text, playbook)


def hygiene_to_html(
    text: str, contract_name: str = "pasted contract"
) -> str:
    """Run the drafting-hygiene checker and render the result fragment.

    Raises ValueError on bad input.
    """
    if not text.strip():
        raise ValueError("paste some contract text or upload a file first")
    findings = run_hygiene(text)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    breakdown = ", ".join(
        f"{n} {sev}" for sev, n in counts.items() if n
    ) or "no findings"
    blocks = [
        f"<h2>Drafting-hygiene report: {html.escape(contract_name)} "
        f"&mdash; {len(findings)} finding(s) ({html.escape(breakdown)})</h2>"
    ]
    if not findings:
        blocks.append('<div class="finding">✅ <b>No hygiene issues.</b></div>')
    else:
        sevs = list(dict.fromkeys(f.severity for f in findings))
        toggles = " ".join(
            f'<label><input type="checkbox" data-sev-toggle="{html.escape(s)}" checked> '
            f"{html.escape(s)}</label>"
            for s in sevs
        )
        blocks.append(f'<div class="sevfilter">Show: {toggles}</div>')
    for f in findings:
        badge = _SEV.get(f.severity, f.severity.upper())
        where = f" (line {f.line})" if f.line else ""
        blocks.append(
            f'<div class="finding" data-sev="{html.escape(f.severity)}">'
            f'<span class="badge">{badge}</span> '
            f"<b>{html.escape(f.title)}</b> "
            f'<span class="checkid">{html.escape(f.check_id)}{html.escape(where)}</span>'
            f"<p>{html.escape(f.detail)}</p>"
            "</div>"
        )
    blocks.append(_RESULT_JS)
    return "\n".join(blocks)


def review_to_docx(
    text: str, playbook_name: str, contract_name: str = "pasted contract"
) -> bytes:
    """Run a review and render the tracked-changes Word redline. Raises ValueError."""
    pb_path = PLAYBOOKS_DIR / f"{playbook_name}.yaml"
    try:
        playbook = load_playbook(pb_path)
    except PlaybookError as exc:
        raise ValueError(f"bad playbook: {exc}") from exc
    if not text.strip():
        raise ValueError("paste some contract text or upload a file first")
    findings = review_contract(text, playbook)
    return render_redline_docx(
        contract_name, text, playbook.name, findings, len(playbook.rules)
    )


def _download_filename(contract_name: str) -> str:
    stem = Path(contract_name).stem or "contract"
    safe = re.sub(r"[^\w\-. ]+", "_", stem).strip() or "contract"
    return f"{safe}.redline.docx"


def _letter_filename(contract_name: str) -> str:
    stem = Path(contract_name).stem or "contract"
    safe = re.sub(r"[^\w\-. ]+", "_", stem).strip() or "contract"
    return f"{safe}.letter.docx"


def _followup_filename(contract_name: str) -> str:
    stem = Path(contract_name).stem or "contract"
    safe = re.sub(r"[^\w\-. ]+", "_", stem).strip() or "contract"
    return f"{safe}.followup.docx"


def _text_from_upload(uploaded: tuple[str, bytes] | None, ocr: bool) -> tuple[str | None, str | None]:
    """Extract text from an uploaded file; (None, None) when no file was sent."""
    if not uploaded or not uploaded[1]:
        return None, None
    filename, data = uploaded
    suffix = Path(filename).suffix.lower()
    if suffix not in (".md", ".txt", ".docx", ".pdf"):
        raise ValueError(f"unsupported upload type {suffix!r}")
    import tempfile

    with tempfile.NamedTemporaryFile(
        suffix=suffix, prefix="redline-upload-", delete=False
    ) as tmp:
        tmp.write(data)
    try:
        text = extract_text(tmp.name, ocr=ocr)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return text, Path(filename).name


def _parse_multipart(body: bytes, content_type: str):
    """Minimal multipart/form-data parser.

    Returns (fields, files): fields maps names to str, files maps names to
    (filename, bytes). Only what the upload form needs — not a general parser.
    """
    import re

    m = re.search(r"boundary=([^;]+)", content_type)
    if not m:
        return {}, {}
    boundary = ("--" + m.group(1).strip().strip('"')).encode("ascii")
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in body.split(boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, data = part.split(b"\r\n\r\n", 1)
        data = data.removesuffix(b"\r\n")
        head_s = head.decode("latin-1", errors="replace")
        name_m = re.search(r'name="([^"]+)"', head_s)
        if not name_m:
            continue
        file_m = re.search(r'filename="([^"]*)"', head_s)
        if file_m and file_m.group(1):
            files[name_m.group(1)] = (file_m.group(1), data)
        else:
            fields[name_m.group(1)] = data.decode("utf-8", errors="replace")
    return fields, files


def page_html(result: str = "", selected: str = "saas-vendor") -> str:
    return PAGE.format(options=_playbook_options(selected), result=result)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, body: str, status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_docx(self, data: bytes, filename: str):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/download.docx":
            if not _last_review:
                return self._send("<h1>no review yet — review a contract first</h1>", 404)
            try:
                data = review_to_docx(
                    _last_review["text"],
                    _last_review["playbook"],
                    _last_review["name"],
                )
            except ValueError as exc:
                return self._send(f"<h1>error: {html.escape(str(exc))}</h1>", 400)
            return self._send_docx(data, _download_filename(_last_review["name"]))
        if self.path == "/letter.docx":
            if not _last_letter:
                return self._send(
                    "<h1>no letter yet — draft a negotiation letter first</h1>", 404
                )
            try:
                data = letter_to_docx(
                    _last_letter["text"],
                    _last_letter["playbook"],
                    _last_letter["name"],
                    _last_letter["recipient"],
                    _last_letter["sender"],
                )
            except ValueError as exc:
                return self._send(f"<h1>error: {html.escape(str(exc))}</h1>", 400)
            return self._send_docx(data, _letter_filename(_last_letter["name"]))
        if self.path == "/followup.docx":
            if not _last_followup:
                return self._send(
                    "<h1>no follow-up yet — draft a follow-up letter first</h1>", 404
                )
            try:
                data = followup_to_docx(
                    _last_followup["old_text"],
                    _last_followup["new_text"],
                    _last_followup["playbook"],
                    _last_followup["old_name"],
                    _last_followup["new_name"],
                    _last_followup["recipient"],
                    _last_followup["sender"],
                )
            except ValueError as exc:
                return self._send(f"<h1>error: {html.escape(str(exc))}</h1>", 400)
            return self._send_docx(data, _followup_filename(_last_followup["new_name"]))
        if self.path != "/":
            return self._send("<h1>not found</h1>", 404)
        self._send(page_html())

    def do_POST(self):
        if self.path != "/review":
            return self._send("<h1>not found</h1>", 404)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        fields: dict[str, str] = {}
        files: dict[str, tuple[str, bytes]] = {}
        if content_type.startswith("multipart/form-data"):
            fields, files = _parse_multipart(raw, content_type)
        else:
            fields = {
                k: v[0]
                for k, v in urllib.parse.parse_qs(
                    raw.decode("utf-8", errors="replace")
                ).items()
            }
        text = fields.get("text", "")
        playbook = fields.get("playbook", "saas-vendor") or "saas-vendor"
        fmt = fields.get("format", "memo") or "memo"
        ocr = fields.get("ocr") == "1"
        mode = fields.get("mode", "review") or "review"
        recipient = fields.get("recipient", "").strip() or None
        sender = fields.get("sender", "").strip() or None
        contract_name = "pasted contract"
        old_text = fields.get("text_old", "")
        old_name = "earlier draft"
        try:
            uploaded_text, uploaded_name = _text_from_upload(
                files.get("contract_file"), ocr
            )
            if uploaded_text is not None:
                text, contract_name = uploaded_text, uploaded_name
            old_uploaded_text, old_uploaded_name = _text_from_upload(
                files.get("contract_file_old"), ocr
            )
            if old_uploaded_text is not None:
                old_text, old_name = old_uploaded_text, old_uploaded_name
            if mode == "hygiene":
                result = hygiene_to_html(text, contract_name)
            elif mode == "letter":
                result = letter_to_html(
                    text, playbook, contract_name, recipient, sender
                )
                _last_letter.clear()
                _last_letter.update(
                    {
                        "text": text,
                        "playbook": playbook,
                        "name": contract_name,
                        "recipient": recipient,
                        "sender": sender,
                    }
                )
                result += (
                    '<p><a href="/letter.docx">⬇ Download Word letter '
                    "(.docx)</a></p>"
                )
            elif mode == "followup":
                result = followup_to_html(
                    old_text,
                    text,
                    playbook,
                    old_name,
                    contract_name,
                    recipient,
                    sender,
                )
                _last_followup.clear()
                _last_followup.update(
                    {
                        "old_text": old_text,
                        "new_text": text,
                        "playbook": playbook,
                        "old_name": old_name,
                        "new_name": contract_name,
                        "recipient": recipient,
                        "sender": sender,
                    }
                )
                result += (
                    '<p><a href="/followup.docx">⬇ Download Word follow-up '
                    "letter (.docx)</a></p>"
                )
            else:
                result = review_to_html(text, playbook, fmt, contract_name)
                _last_review.clear()
                _last_review.update(
                    {"text": text, "playbook": playbook, "name": contract_name}
                )
                result += (
                    '<p><a href="/download.docx">⬇ Download Word redline '
                    "(.docx, tracked changes)</a></p>"
                )
        except (ValueError, IngestionError) as exc:
            result = f'<div class="warn">⚠️ {html.escape(str(exc))}</div>'
        self._send(page_html(result, playbook))


def serve(port: int = 8000, host: str = "127.0.0.1") -> None:
    server = http.server.HTTPServer((host, port), Handler)
    print(f"redline-buddy serving at http://{host}:{server.server_port} (local only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_serve(args) -> int:
    serve(port=args.port, host=args.bind)
    return 0
