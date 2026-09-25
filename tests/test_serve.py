"""Tests for the minimal web UI (redline serve)."""
import http.client
import http.server
import threading
import urllib.parse
from pathlib import Path

import pytest

from redline.serve import Handler, page_html, review_to_html

ROOT = Path(__file__).resolve().parent.parent
OFFER = (ROOT / "examples" / "sample-offer.md").read_text(encoding="utf-8")


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
                 "client-sow", "consulting-msa"]:
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
