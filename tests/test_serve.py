"""Tests for the minimal web UI (redline serve)."""
import http.client
import http.server
import threading
import urllib.parse
from pathlib import Path

import pytest

from redline.serve import Handler, hygiene_to_html, letter_to_html, page_html, review_to_html

ROOT = Path(__file__).resolve().parent.parent
OFFER = (ROOT / "examples" / "sample-offer.md").read_text(encoding="utf-8")
HYGIENE_SAMPLE = (ROOT / "examples" / "hygiene-sample.md").read_text(encoding="utf-8")


def test_review_to_html_memo_lists_findings():
    out = review_to_html(OFFER, "offer-letter", "memo")
    assert "Non-compete in the offer letter" in out
    assert "HIGH" in out


def test_review_to_html_diff_renders_hunks():
    out = review_to_html(OFFER, "offer-letter", "diff")
    assert 'class="del"' in out
    assert 'class="add"' in out
    assert "Strike the non-compete" in out


def test_review_to_html_escapes_input():
    # payload sits inside the excerpted sentence, so it must appear escaped
    evil = OFFER.replace(
        "intelligence industries.",
        "intelligence industries <script>alert(1)</script>.",
        1,
    )
    out = review_to_html(evil, "offer-letter", "memo")
    assert "<script>alert(1)" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_review_to_html_rejects_empty_text():
    with pytest.raises(ValueError, match="paste some contract text"):
        review_to_html("   ", "offer-letter", "memo")


def test_review_to_html_rejects_bad_playbook():
    with pytest.raises(ValueError, match="bad playbook"):
        review_to_html(OFFER, "no-such-playbook", "memo")


def test_page_lists_all_bundled_playbooks():
    html_text = page_html()
    for name in ["saas-vendor", "nda-recipient", "contractor", "dpa", "offer-letter",
                 "client-sow", "consulting-msa", "lease-tenant", "consulting-vendor",
                 "loan-borrower"]:
        assert f'value="{name}"' in html_text
    assert "<form" in html_text


def test_page_playbook_options_show_descriptions():
    html_text = page_html()
    # option labels carry the playbook description, not just the stem
    assert "consulting-msa — Red-flag rules for reviewing consulting" in html_text
    assert "saas-vendor — " in html_text


def test_memo_has_copy_fallback_buttons():
    out = review_to_html(OFFER, "offer-letter", "memo")
    assert "Copy fallback" in out
    assert "<textarea" in out
    # the fallback's apostrophe is escaped inside the textarea (XSS-safe),
    # and .value gives the raw clause back to the clipboard
    assert "Company&#x27;s employees" in out
    assert 'onclick="copyFb(' in out


def test_memo_has_severity_filter():
    out = review_to_html(OFFER, "offer-letter", "memo")
    assert 'data-sev="high"' in out
    assert 'data-sev-toggle="high"' in out
    assert "Show:" in out


def test_live_server_roundtrip():
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.status == 200
        assert "redline-buddy" in resp.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join()


def test_live_server_review_post():
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        body = urllib.parse.urlencode(
            {"text": OFFER, "playbook": "offer-letter", "format": "diff"}
        )
        conn.request(
            "POST", "/review", body,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = conn.getresponse()
        assert resp.status == 200
        page = resp.read().decode("utf-8")
        assert "Non-compete in the offer letter" in page
        assert 'class="add"' in page
    finally:
        server.shutdown()
        thread.join()


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = "testboundary123"
    buf = b""
    for name, value in fields.items():
        buf += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    for name, (filename, data) in files.items():
        buf += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + data + b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    return buf, f"multipart/form-data; boundary={boundary}"


def _post(path: str, body: bytes, content_type: str) -> tuple[int, str]:
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        conn.request("POST", path, body, {"Content-Type": content_type})
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join()


def test_upload_markdown_file_reviews_it():
    body, ctype = _multipart(
        {"playbook": "offer-letter", "format": "memo"},
        {"contract_file": ("offer.md", OFFER.encode("utf-8"))},
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "Non-compete in the offer letter" in page
    assert "offer.md" in page


def test_upload_unsupported_type_warns():
    body, ctype = _multipart(
        {"playbook": "offer-letter", "format": "memo"},
        {"contract_file": ("evil.exe", b"MZ...")},
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "unsupported upload type" in page


def test_empty_post_warns():
    body, ctype = _multipart({"playbook": "offer-letter", "format": "memo"}, {})
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "paste some contract text or upload a file" in page


# --- Word redline download -------------------------------------------------


def _get(path: str) -> tuple[int, dict, bytes]:
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        server.shutdown()
        thread.join()


def test_review_to_docx_returns_valid_docx():
    import io
    import zipfile

    from redline.serve import review_to_docx

    data = review_to_docx(OFFER, "offer-letter", "offer.md")
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "<w:del " in xml or "<w:ins " in xml


def test_review_to_docx_rejects_bad_input():
    from redline.serve import review_to_docx

    with pytest.raises(ValueError):
        review_to_docx("   ", "offer-letter")


def test_download_filename_sanitized():
    from redline.serve import _download_filename

    assert _download_filename("contract.md") == "contract.redline.docx"
    assert _download_filename("pasted contract") == "pasted contract.redline.docx"
    assert _download_filename("../../evil.md") == "evil.redline.docx"


def test_download_docx_without_review_404s():
    from redline.serve import _last_review

    _last_review.clear()
    status, _, _ = _get("/download.docx")
    assert status == 404


def test_download_docx_after_review():
    import io
    import zipfile

    body, ctype = _multipart(
        {"text": OFFER, "playbook": "offer-letter", "format": "memo"}, {}
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "/download.docx" in page
    status, headers, data = _get("/download.docx")
    assert status == 200
    assert headers.get("Content-Type", "").startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'attachment; filename="pasted contract.redline.docx"' in headers.get(
        "Content-Disposition", ""
    )
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "<w:del " in xml or "<w:ins " in xml


# --- Drafting-hygiene mode ---------------------------------------------------


def test_hygiene_to_html_lists_findings():
    out = hygiene_to_html(HYGIENE_SAMPLE, "hygiene-sample.md")
    assert "Drafting-hygiene report" in out
    assert "10 finding(s)" in out
    assert "undefined-term" in out
    assert "dangling-reference" in out
    assert "MEDIUM" in out
    assert 'data-sev="medium"' in out


def test_hygiene_to_html_clean():
    out = hygiene_to_html('"Services" means the work.\nThe Services are done.\n')
    assert "No hygiene issues" in out


def test_hygiene_to_html_escapes_input():
    # payload sits inside a defined term, so it lands in finding titles/details
    evil = HYGIENE_SAMPLE.replace(
        '"Dead Term"',
        '"Dead <script>alert(1)</script> Term"',
    )
    out = hygiene_to_html(evil)
    assert "<script>alert(1)" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_hygiene_to_html_rejects_empty_text():
    with pytest.raises(ValueError, match="paste some contract text"):
        hygiene_to_html("   ")


def test_page_has_hygiene_mode_select():
    html_text = page_html()
    assert 'name="mode"' in html_text
    assert 'value="hygiene"' in html_text
    assert "drafting hygiene" in html_text


def test_live_server_hygiene_post():
    body, ctype = _multipart(
        {"text": HYGIENE_SAMPLE, "mode": "hygiene", "playbook": "saas-vendor"},
        {},
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "Drafting-hygiene report" in page
    assert "undefined-term" in page
    # hygiene mode has no Word redline download
    assert "/download.docx" not in page


def test_live_server_hygiene_empty_warns():
    body, ctype = _multipart({"mode": "hygiene"}, {})
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "paste some contract text or upload a file" in page


SOLAR = (ROOT / "examples" / "sample-solar-installation.md").read_text(encoding="utf-8")
CLEAN_SOLAR = (ROOT / "examples" / "clean-solar-installation.md").read_text(encoding="utf-8")


def test_letter_to_html_renders_letter():
    out = letter_to_html(SOLAR, "solar-installation", "sample-solar-installation.md")
    assert "Draft negotiation letter" in out
    assert "<h3>1. " in out and "HIGH" in out
    assert "<blockquote>" in out  # quoted contract language
    assert "Proposed language:" in out
    assert "Not legal advice." in out


def test_letter_to_html_personalization():
    out = letter_to_html(
        SOLAR, "solar-installation", "c.md", recipient="BrightSun", sender="Alex"
    )
    assert "Dear BrightSun," in out
    assert "Alex</p>" in out or ">Alex<" in out or "Alex" in out
    assert "[Counterparty name]" not in out


def test_letter_to_html_clean_contract():
    out = letter_to_html(CLEAN_SOLAR, "solar-installation", "clean.md")
    assert "no material issues" in out
    assert "<h3>" not in out


def test_letter_to_html_escapes_input():
    evil = SOLAR.replace("$0.16/kWh", "$0.16/kWh <script>alert(1)</script>", 1)
    out = letter_to_html(evil, "solar-installation", "c.md")
    assert "<script>alert(1)" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_letter_to_html_rejects_empty_text():
    with pytest.raises(ValueError, match="paste some contract text"):
        letter_to_html("   ", "solar-installation")


def test_letter_to_html_rejects_bad_playbook():
    with pytest.raises(ValueError, match="bad playbook"):
        letter_to_html(SOLAR, "no-such-playbook")


def test_page_has_letter_mode_select():
    html_text = page_html()
    assert 'value="letter"' in html_text
    assert "negotiation letter" in html_text
    assert 'name="recipient"' in html_text
    assert 'name="sender"' in html_text


def test_live_server_letter_post():
    body, ctype = _multipart(
        {
            "text": SOLAR,
            "mode": "letter",
            "playbook": "solar-installation",
            "recipient": "BrightSun",
            "sender": "Alex",
        },
        {},
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "Draft negotiation letter" in page
    assert "Dear BrightSun," in page
    assert "Proposed language:" in page
    # letter mode has its own Word download, not the redline one
    assert "/letter.docx" in page
    assert "/download.docx" not in page


def test_live_server_letter_empty_warns():
    body, ctype = _multipart({"mode": "letter"}, {})
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "paste some contract text or upload a file" in page


# --- Word letter download --------------------------------------------------


def test_letter_to_docx_returns_valid_docx():
    import io
    import zipfile

    from redline.serve import letter_to_docx

    data = letter_to_docx(
        SOLAR, "solar-installation", "sample-solar-installation.md",
        recipient="BrightSun", sender="Alex",
    )
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "Draft negotiation letter" in xml
    assert "Dear BrightSun," in xml


def test_letter_to_docx_rejects_bad_input():
    from redline.serve import letter_to_docx

    with pytest.raises(ValueError, match="paste some contract text"):
        letter_to_docx("   ", "solar-installation")
    with pytest.raises(ValueError, match="bad playbook"):
        letter_to_docx(SOLAR, "no-such-playbook")


def test_letter_filename_sanitized():
    from redline.serve import _letter_filename

    assert _letter_filename("contract.md") == "contract.letter.docx"
    assert _letter_filename("pasted contract") == "pasted contract.letter.docx"
    assert _letter_filename("../../evil.md") == "evil.letter.docx"


def test_letter_docx_without_letter_404s():
    from redline.serve import _last_letter

    _last_letter.clear()
    status, _, _ = _get("/letter.docx")
    assert status == 404


def test_letter_docx_after_letter_post():
    import io
    import zipfile

    from redline.serve import _last_letter

    body, ctype = _multipart(
        {
            "text": SOLAR,
            "mode": "letter",
            "playbook": "solar-installation",
            "recipient": "BrightSun",
            "sender": "Alex",
        },
        {},
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "/letter.docx" in page
    assert _last_letter["recipient"] == "BrightSun"
    status, headers, data = _get("/letter.docx")
    assert status == 200
    assert headers.get("Content-Type", "").startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'attachment; filename="pasted contract.letter.docx"' in headers.get(
        "Content-Disposition", ""
    )
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "Dear BrightSun," in xml
    assert "Alex" in xml


# --- Round-2 follow-up mode --------------------------------------------------

ROUND1 = (ROOT / "examples" / "sample-solar-installation.md").read_text(encoding="utf-8")
ROUND2 = (ROOT / "examples" / "sample-solar-installation-round2.md").read_text(encoding="utf-8")


def test_followup_to_html_renders_sections():
    from redline.serve import followup_to_html

    out = followup_to_html(ROUND1, ROUND2, "solar-installation", "round1.md", "round2.md")
    assert "Follow-up letter" in out
    assert "What&#x27;s fixed" in out or "What's fixed" in out
    assert "Still open" in out
    assert "NOT ADDRESSED" in out
    assert "STILL FLAGGED AFTER REDRAFTING" in out
    assert "Not legal advice." in out


def test_followup_to_html_rejects_bad_input():
    from redline.serve import followup_to_html

    with pytest.raises(ValueError, match="earlier draft"):
        followup_to_html("   ", ROUND2, "solar-installation")
    with pytest.raises(ValueError, match="paste some contract text"):
        followup_to_html(ROUND1, "   ", "solar-installation")
    with pytest.raises(ValueError, match="bad playbook"):
        followup_to_html(ROUND1, ROUND2, "no-such-playbook")


def test_followup_to_docx_returns_valid_docx():
    import io
    import zipfile

    from redline.serve import followup_to_docx

    data = followup_to_docx(ROUND1, ROUND2, "solar-installation", "round1.md", "round2.md")
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "Follow-up letter" in xml
    assert "NOT ADDRESSED" in xml


def test_followup_filename_sanitized():
    from redline.serve import _followup_filename

    assert _followup_filename("round2.md") == "round2.followup.docx"
    assert _followup_filename("pasted contract") == "pasted contract.followup.docx"
    assert _followup_filename("../../evil.md") == "evil.followup.docx"


def test_page_has_followup_mode_select():
    html_text = page_html()
    assert 'value="followup"' in html_text
    assert "round-2 follow-up letter" in html_text
    assert 'name="text_old"' in html_text
    assert 'name="contract_file_old"' in html_text


def test_followup_docx_without_followup_404s():
    from redline.serve import _last_followup

    _last_followup.clear()
    status, _, _ = _get("/followup.docx")
    assert status == 404


def test_followup_post_missing_old_warns():
    body, ctype = _multipart(
        {"text": ROUND2, "mode": "followup", "playbook": "solar-installation"}, {}
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "earlier draft" in page
    assert "/followup.docx" not in page


def test_followup_post_then_download():
    import io
    import zipfile

    from redline.serve import _last_followup

    body, ctype = _multipart(
        {
            "text_old": ROUND1,
            "text": ROUND2,
            "mode": "followup",
            "playbook": "solar-installation",
            "recipient": "BrightSun",
            "sender": "Alex",
        },
        {},
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "Follow-up letter" in page
    assert "/followup.docx" in page
    assert _last_followup["old_name"] == "earlier draft"
    status, headers, data = _get("/followup.docx")
    assert status == 200
    assert headers.get("Content-Type", "").startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'attachment; filename="pasted contract.followup.docx"' in headers.get(
        "Content-Disposition", ""
    )
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "Follow-up letter" in xml
    assert "Dear BrightSun," in xml


def test_followup_post_with_old_file_upload():
    body, ctype = _multipart(
        {"mode": "followup", "playbook": "solar-installation"},
        {
            "contract_file_old": ("round1.md", ROUND1.encode("utf-8")),
            "contract_file": ("round2.md", ROUND2.encode("utf-8")),
        },
    )
    status, page = _post("/review", body, ctype)
    assert status == 200
    assert "Follow-up letter" in page
    assert "round2.md" in page
    assert "/followup.docx" in page
