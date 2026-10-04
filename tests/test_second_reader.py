"""Tests for the optional LLM second reader (--second-reader).

All model I/O goes through a fake provider — no network, no API keys.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from redline.memo import render_memo
from redline.playbook import bundled_playbook_path, load_playbook
from redline.review import Finding, review_contract
from redline.second_reader import (
    SecondReaderConfig,
    SecondReaderError,
    build_prompt,
    merge_findings,
    parse_findings,
    run_second_reader,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLAYBOOK = load_playbook(bundled_playbook_path("saas-vendor"))
RULE_IDS = [r.id for r in PLAYBOOK.rules]


class FakeProvider:
    """Canned model output; records the prompt it was given."""

    def __init__(self, raw: str):
        self.raw = raw
        self.seen_system = None
        self.seen_user = None

    def complete(self, system: str, user: str) -> str:
        self.seen_system = system
        self.seen_user = user
        return self.raw


def _payload(*items) -> str:
    return json.dumps({"findings": list(items)})


def _item(rule_id, quote="quoted clause text", reasoning="why", severity="high"):
    return {
        "rule_id": rule_id,
        "quote": quote,
        "reasoning": reasoning,
        "severity": severity,
    }


# --- prompt building ------------------------------------------------------


def test_build_prompt_lists_every_rule_and_truncates_contract():
    long_text = "x" * 5000
    system, user = build_prompt(long_text, PLAYBOOK, max_chars=1000)
    for rid in RULE_IDS:
        assert rid in user
    assert "…[truncated]" in user
    assert len(user) < len(long_text)
    assert "JSON" in system


def test_build_prompt_keeps_short_contract_whole():
    _, user = build_prompt("short contract", PLAYBOOK, max_chars=1000)
    assert "short contract" in user
    assert "[truncated]" not in user


# --- parsing --------------------------------------------------------------


def test_parse_findings_accepts_fenced_json():
    raw = "```json\n" + _payload(_item(RULE_IDS[0])) + "\n```"
    findings = parse_findings(raw, PLAYBOOK)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == RULE_IDS[0]
    assert f.origin == "second-reader"
    assert f.excerpt == "quoted clause text"
    assert f.why == "why"


def test_parse_findings_accepts_bare_list():
    raw = json.dumps([_item(RULE_IDS[0], severity="medium")])
    findings = parse_findings(raw, PLAYBOOK)
    assert len(findings) == 1
    assert findings[0].severity == "medium"


def test_parse_findings_rejects_garbage():
    with pytest.raises(SecondReaderError):
        parse_findings("not json at all ((((", PLAYBOOK)


def test_parse_findings_rejects_missing_findings_key():
    with pytest.raises(SecondReaderError):
        parse_findings('{"answer": 42}', PLAYBOOK)


def test_parse_findings_drops_unknown_rule_empty_quote_bad_severity():
    raw = _payload(
        _item("not-a-real-rule"),
        _item(RULE_IDS[0], quote="   "),
        _item(RULE_IDS[1], severity="extreme"),
        _item(RULE_IDS[2]),
    )
    findings = parse_findings(raw, PLAYBOOK)
    assert [f.rule_id for f in findings] == [RULE_IDS[2]]


def test_parse_findings_falls_back_to_rule_why_when_reasoning_empty():
    raw = _payload(_item(RULE_IDS[0], reasoning=""))
    findings = parse_findings(raw, PLAYBOOK)
    assert findings[0].why == PLAYBOOK.rules[0].why


# --- merging --------------------------------------------------------------


def test_merge_confirms_rule_hit_and_appends_novel():
    rule_hit = Finding(
        rule_id=RULE_IDS[0],
        title="T",
        severity="high",
        excerpt="e",
        why="w",
        suggestion="s",
    )
    confirm = Finding(
        rule_id=RULE_IDS[0],
        title="T",
        severity="high",
        excerpt="model quote",
        why="mw",
        suggestion="s",
        origin="second-reader",
    )
    novel = Finding(
        rule_id=RULE_IDS[1],
        title="T2",
        severity="low",
        excerpt="q",
        why="w",
        suggestion="s",
        origin="second-reader",
    )
    merged = merge_findings([rule_hit], [confirm, novel])
    assert len(merged) == 2
    # Rule finding keeps its own excerpt/guidance, just marked confirmed.
    assert merged[0].excerpt == "e"
    assert merged[0].llm_confirmed is True
    assert merged[0].origin == "rules"
    # Novel LLM finding appended after rule findings.
    assert merged[1].rule_id == RULE_IDS[1]
    assert merged[1].origin == "second-reader"


def test_merge_sorts_novel_findings_by_severity():
    base = Finding(
        rule_id=RULE_IDS[0],
        title="T",
        severity="high",
        excerpt="e",
        why="w",
        suggestion="s",
    )
    low = Finding(
        rule_id=RULE_IDS[1], title="T", severity="low", excerpt="q",
        why="w", suggestion="s", origin="second-reader",
    )
    critical = Finding(
        rule_id=RULE_IDS[2], title="T", severity="critical", excerpt="q",
        why="w", suggestion="s", origin="second-reader",
    )
    merged = merge_findings([base], [low, critical])
    assert [f.severity for f in merged] == ["high", "critical", "low"]


# --- end to end -----------------------------------------------------------


def test_run_second_reader_end_to_end_with_fake_provider():
    text = (ROOT / "examples" / "sample-msa.md").read_text()
    rule_findings = review_contract(text, PLAYBOOK)
    assert rule_findings, "sample MSA should fire deterministic rules"
    fired = {f.rule_id for f in rule_findings}
    novel_id = next(r for r in RULE_IDS if r not in fired)

    provider = FakeProvider(
        _payload(
            _item(next(iter(fired))),  # confirm one deterministic hit
            _item(novel_id, severity="medium"),  # one novel observation
        )
    )
    merged = run_second_reader(
        text, PLAYBOOK, provider, SecondReaderConfig(model="fake"),
        rule_findings=rule_findings,
    )
    confirmed = [f for f in merged if f.llm_confirmed]
    novel = [f for f in merged if f.origin == "second-reader"]
    assert len(confirmed) == 1
    assert len(novel) == 1 and novel[0].rule_id == novel_id
    # The prompt actually reached the provider.
    assert provider.seen_user and PLAYBOOK.name in provider.seen_user


def test_run_second_reader_empty_output_errors():
    with pytest.raises(SecondReaderError):
        run_second_reader("text", PLAYBOOK, FakeProvider("  "),
                          SecondReaderConfig(model="fake"))


# --- memo rendering -------------------------------------------------------


def test_memo_marks_second_reader_findings():
    rule_hit = Finding(
        rule_id="r1", title="Rule hit", severity="high", excerpt="e",
        why="w", suggestion="s", llm_confirmed=True,
    )
    novel = Finding(
        rule_id="r2", title="New observation", severity="medium", excerpt="q",
        why="w", suggestion="s", origin="second-reader",
    )
    memo = render_memo("c.md", "saas-vendor", [rule_hit, novel], 10,
                       second_reader_model="fake-model")
    assert "✓ confirmed by second reader" in memo
    assert "🤖 second-reader observation" in memo
    assert "Second reader: `fake-model`" in memo
    assert "1 rule hit(s) independently confirmed, 1 new observation(s)" in memo


def test_memo_without_second_reader_is_unchanged():
    f = Finding(
        rule_id="r1", title="Rule hit", severity="high", excerpt="e",
        why="w", suggestion="s",
    )
    memo = render_memo("c.md", "saas-vendor", [f], 10)
    assert "second reader" not in memo.lower()
    assert "🤖" not in memo


# --- CLI ------------------------------------------------------------------


def run_cli(*args: str) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "redline.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_cli_second_reader_without_litellm_fails_cleanly():
    # litellm is not a default dependency, so this exercises the real
    # missing-package path: exit 2 with install guidance, no traceback.
    try:
        import litellm  # noqa: F401
        pytest.skip("litellm installed; missing-package path not exercised")
    except ImportError:
        pass
    proc = run_cli(
        "review", str(ROOT / "examples" / "sample-msa.md"),
        "--second-reader", "gpt-4o-mini",
    )
    assert proc.returncode == 2
    assert 'pip install "redline-buddy[llm]"' in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_second_reader_warns_and_ignores_in_batch_mode(tmp_path):
    (tmp_path / "c.md").write_text("some contract text")
    proc = run_cli("review", str(tmp_path), "--second-reader", "gpt-4o-mini")
    assert proc.returncode == 0
    assert "single-file only" in proc.stderr
