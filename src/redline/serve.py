"""Minimal local web UI: paste or upload a contract, pick a playbook, get the memo.

    redline serve [--port 8000]

Stdlib only (http.server) — no new dependencies. Binds to 127.0.0.1 by
default: everything still stays on your machine.
"""
from __future__ import annotations

import html
import http.server
import urllib.parse
from pathlib import Path

from .ingest import IngestionError, extract_text
from .memo import render_diff
from .playbook import PlaybookError, bundled_playbooks_dir, load_playbook
from .review import review_contract

PLAYBOOKS_DIR = bundled_playbooks_dir()

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>redline-buddy</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:70ch;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
textarea{{width:100%;height:14rem;font:0.85rem/1.4 monospace}}
pre.diff{{background:#f6f8fa;padding:1rem;overflow-x:auto;font-size:0.8rem}}
pre.diff .del{{color:#b42318}} pre.diff .add{{color:#067647}}
.finding{{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}}
.sevfilter{{margin:1rem 0}}.sevfilter label{{margin-right:1rem}}
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
<label>Playbook: <select name="playbook">{options}</select></label>
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


def _render_result_html(contract_name: str, playbook: str, findings, fmt: str) -> str:
    if fmt == "diff":
        md = render_diff(contract_name, playbook, findings)
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
    blocks = [(f"<h2>Red-flag memo: {html.escape(contract_name)} "
               f"— {len(findings)} finding(s) ({html.escape(playbook)})</h2>")]
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
    return _render_result_html(contract_name, playbook.name, findings, fmt)


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

    def do_GET(self):
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
        contract_name = "pasted contract"
        uploaded = files.get("contract_file")
        try:
            if uploaded and uploaded[1]:
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
                contract_name = Path(filename).name
            result = review_to_html(text, playbook, fmt, contract_name)
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
