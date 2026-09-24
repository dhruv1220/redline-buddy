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
    out = review_to_html("<script>alert(1)</script> " + OFFER, "offer-letter", "memo")
    assert "<script>" not in out


def test_review_to_html_rejects_empty_text():
    with pytest.raises(ValueError, match="paste some contract text"):
        review_to_html("   ", "offer-letter", "memo")


def test_review_to_html_rejects_bad_playbook():
    with pytest.raises(ValueError, match="bad playbook"):
        review_to_html(OFFER, "no-such-playbook", "memo")


def test_page_lists_all_bundled_playbooks():
    html_text = page_html()
    for name in ["saas-vendor", "nda-recipient", "contractor", "dpa", "offer-letter", "client-sow"]:
        assert f'value="{name}"' in html_text
    assert "<form" in html_text


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
