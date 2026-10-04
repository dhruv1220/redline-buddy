"""Optional LLM second reader: a model re-reads the contract against the playbook.

The deterministic rule engine is the default and stays fully offline. Passing
``--second-reader <model>`` sends the contract text to a model provider (BYO
API key), so the second reader is strictly opt-in. Its job is to catch what
regex rules miss — paraphrased clauses, clever drafting, negations — and to
confirm deterministic hits. Findings the rules already caught are marked
confirmed; genuinely new observations are appended, clearly labeled.

Output is NOT legal advice: it is a first-pass draft for human attorney
review, same as every other redline-buddy output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from .playbook import Playbook
from .review import SEVERITY_RANK, Finding

SYSTEM_PROMPT = """\
You are a contract-review assistant working from a fixed playbook. You will be
given a list of playbook rules (id, title, severity, plain-language guidance)
and a contract. Your job is to act as a SECOND READER behind a deterministic
rule engine:

1. For each rule, decide whether the contract violates the rule's guidance,
   even when the wording is paraphrased or indirect. Pay special attention to
   negations ("shall NOT ...") and carve-outs that flip a clause's meaning.
2. Only use rule ids from the provided list. Never invent rules.
3. Quote the offending contract language verbatim in "quote".
4. Keep "reasoning" to one or two sentences, plain language, no legalese.
5. Output ONLY JSON — no markdown fences, no commentary — in exactly this shape:
   {"findings": [{"rule_id": "<id>", "quote": "<verbatim quote>",
                  "reasoning": "<why it violates the rule>",
                  "severity": "<critical|high|medium|low>"}]}
   An empty list is a valid answer: {"findings": []}.
6. This is a first-pass draft for human attorney review, not legal advice.
"""

USER_TEMPLATE = """\
Playbook: {playbook_name} — {playbook_description}

Rules:
{rules}

Contract (truncated to {max_chars} characters):
---
{contract}
---
"""


class SecondReaderError(Exception):
    """The second-reader pass could not run (setup, provider, or parse failure)."""


class LLMProvider(Protocol):
    """Minimal provider surface so tests can inject a fake without network."""

    def complete(self, system: str, user: str) -> str:
        ...


@dataclass
class SecondReaderConfig:
    model: str
    timeout: int = 120
    max_chars: int = 12000


def litellm_provider(config: SecondReaderConfig) -> LLMProvider:
    """Build a LiteLLM-backed provider. LiteLLM is an optional dependency."""
    try:
        import litellm
    except ImportError as exc:
        raise SecondReaderError(
            "the second reader needs the 'litellm' package: "
            'pip install "redline-buddy[llm]"'
        ) from exc

    class _LiteLLMProvider:
        def complete(self, system: str, user: str) -> str:
            try:
                resp = litellm.completion(
                    model=config.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    timeout=config.timeout,
                )
            except Exception as exc:  # auth, network, bad model name, ...
                raise SecondReaderError(
                    f"LLM call failed ({config.model}): {exc}. "
                    "Check the model name and provider API key "
                    "(e.g. OPENAI_API_KEY / ANTHROPIC_API_KEY)."
                ) from exc
            try:
                return resp.choices[0].message.content or ""
            except (AttributeError, IndexError, KeyError) as exc:
                raise SecondReaderError(
                    f"unexpected LLM response shape from {config.model}: {exc}"
                ) from exc

    return _LiteLLMProvider()


def build_prompt(
    text: str, playbook: Playbook, max_chars: int = 12000
) -> tuple[str, str]:
    """Render the (system, user) prompt, truncating the contract to max_chars."""
    rules_block = "\n".join(
        f"- {r.id} [{r.severity}] {r.title}: {r.why} Suggested fallback: {r.suggestion}"
        for r in playbook.rules
    )
    contract = text if len(text) <= max_chars else text[:max_chars] + "\n…[truncated]"
    user = USER_TEMPLATE.format(
        playbook_name=playbook.name,
        playbook_description=playbook.description,
        rules=rules_block,
        max_chars=max_chars,
        contract=contract,
    )
    return SYSTEM_PROMPT, user


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> object:
    """Pull a JSON document out of raw model output (fenced or bare)."""
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Last resort: try the largest {...} span in the output.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise SecondReaderError(
            f"could not parse second-reader output as JSON: {exc}"
        ) from exc


def parse_findings(raw: str, playbook: Playbook) -> list[Finding]:
    """Validate raw model output into Findings labeled origin='second-reader'.

    Drops anything that doesn't reference a real playbook rule, lacks a
    verbatim quote, or carries an invalid severity — a hallucinating model
    must not invent findings.
    """
    doc = _extract_json(raw)
    items = doc.get("findings") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        raise SecondReaderError(
            "second-reader output has no 'findings' list; refusing to guess"
        )
    by_id = {r.id: r for r in playbook.rules}
    findings: list[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rule = by_id.get(str(item.get("rule_id", "")))
        quote = str(item.get("quote", "")).strip()
        severity = str(item.get("severity", "")).lower()
        if rule is None or not quote or severity not in SEVERITY_RANK:
            continue
        findings.append(
            Finding(
                rule_id=rule.id,
                title=rule.title,
                severity=severity,
                excerpt=quote,
                why=str(item.get("reasoning", "")).strip() or rule.why,
                suggestion=rule.suggestion,
                fallback=rule.fallback,
                origin="second-reader",
            )
        )
    return findings


def merge_findings(
    rule_findings: list[Finding], llm_findings: list[Finding]
) -> list[Finding]:
    """Confirm rule hits the LLM independently flagged; append novel LLM hits.

    A novel LLM finding is one whose rule_id the deterministic engine did not
    fire. Confirmation is recorded on the rule finding (llm_confirmed=True);
    the rule engine's excerpt and guidance win over the model's paraphrase.
    """
    fired = {f.rule_id for f in rule_findings}
    merged = list(rule_findings)
    for lf in llm_findings:
        if lf.rule_id in fired:
            for rf in merged:
                if rf.rule_id == lf.rule_id:
                    rf.llm_confirmed = True
        else:
            merged.append(lf)
    rank = SEVERITY_RANK
    confirmed = [f for f in merged if f.origin == "rules"]
    novel = sorted(
        (f for f in merged if f.origin != "rules"),
        key=lambda f: rank.get(f.severity, 9),
    )
    return confirmed + novel


def run_second_reader(
    text: str,
    playbook: Playbook,
    provider: LLMProvider,
    config: SecondReaderConfig,
    rule_findings: list[Finding] | None = None,
) -> list[Finding]:
    """Full second-reader pass: prompt -> model -> parse -> merge."""
    from .review import review_contract

    base = rule_findings if rule_findings is not None else review_contract(text, playbook)
    system, user = build_prompt(text, playbook, config.max_chars)
    raw = provider.complete(system, user)
    if not raw or not raw.strip():
        raise SecondReaderError("second reader returned empty output")
    llm_findings = parse_findings(raw, playbook)
    return merge_findings(base, llm_findings)
