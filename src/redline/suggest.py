"""Auto-suggest the best bundled playbook for a contract.

Deterministic, local-only keyword scoring: no LLM, no network calls — in
keeping with the project's privacy-first identity. Used when
``redline review`` is called without ``--playbook``.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .playbook import Playbook, bundled_playbooks_dir, load_playbook

_TOKEN = re.compile(r"[a-z0-9]+")
_PATTERN_WORD = re.compile(r"[a-z]{4,}")

_STOPWORDS = frozenset(
    "with that this from they have were your will shall each both such than "
    "into over under between through during their them then than also only "
    "other more most some made many much when where which while within "
    "after before there here what all any per are was has had its our you "
    "not but for and the are may upon must hereby thereof herein whereof "
    "party parties".split()
)

# A top match below this score is not confident enough to act on.
MIN_SCORE = 15
# If the runner-up scores at least this fraction of the winner, the match is
# ambiguous and the caller should keep the historic default instead of
# silently picking a possibly-wrong playbook.
AMBIGUITY_RATIO = 0.8
# Playbook used when auto-selection is not confident.
FALLBACK_PLAYBOOK = "saas-vendor"

_NAME_W = 6
_TITLE_W = 3
_ID_W = 2
_DESC_W = 1
_PATTERN_W = 2

# Findings signal: a playbook whose rules actually fire on the document is
# more likely the right perspective (e.g. dpa vs dpa-processor share almost
# all vocabulary, but only one side's rules fire). Capped so a broad
# playbook can't win on finding volume alone.
_FINDINGS_W = 10
_FINDINGS_CAP = 6


@dataclass(frozen=True)
class PlaybookMatch:
    name: str
    description: str
    score: int
    matched_terms: tuple[str, ...]
    findings: int = 0


def _tokens(text: str, min_len: int = 3) -> set[str]:
    return {
        t for t in _TOKEN.findall(text.lower())
        if len(t) >= min_len and t not in _STOPWORDS
    }


def _playbook_vocab(playbook: Playbook) -> dict[str, int]:
    """Weighted vocabulary for one playbook: token -> weight."""
    vocab: dict[str, int] = {}
    for t in _tokens(playbook.name.replace("-", " "), min_len=3):
        vocab[t] = max(vocab.get(t, 0), _NAME_W)
    for t in _tokens(playbook.description):
        vocab[t] = max(vocab.get(t, 0), _DESC_W)
    for rule in playbook.rules:
        for t in _tokens(rule.title):
            vocab[t] = max(vocab.get(t, 0), _TITLE_W)
        for t in _tokens(rule.id.replace("-", " "), min_len=3):
            vocab[t] = max(vocab.get(t, 0), _ID_W)
        for pattern in rule.check.patterns:
            for t in _PATTERN_WORD.findall(pattern.lower()):
                if t not in _STOPWORDS:
                    vocab[t] = max(vocab.get(t, 0), _PATTERN_W)
    return vocab


def suggest_playbooks(text: str, limit: int = 3) -> list[PlaybookMatch]:
    """Rank bundled playbooks against contract text, best first.

    Score = tf-idf keyword overlap + ``_FINDINGS_W`` per rule that fires
    (capped at ``_FINDINGS_CAP`` findings). The keyword part matches the
    document's domain; the findings part detects the document's
    perspective — mirror playbooks (``dpa`` vs ``dpa-processor``) share
    nearly all vocabulary, but only the right side's rules fire. Each
    token counts once per playbook; ties break alphabetically for
    determinism.
    """
    from .review import review_contract

    doc_tokens = _tokens(text)
    playbooks: list[Playbook] = []
    vocabs: dict[str, dict[str, int]] = {}
    for path in sorted(bundled_playbooks_dir().glob("*.yaml")):
        playbook = load_playbook(path)
        playbooks.append(playbook)
        vocabs[playbook.name] = _playbook_vocab(playbook)
    doc_freq: dict[str, int] = {}
    for vocab in vocabs.values():
        for t in vocab:
            doc_freq[t] = doc_freq.get(t, 0) + 1
    n = len(vocabs)
    idf = {t: math.log(n / df) + 1.0 for t, df in doc_freq.items()}
    matches: list[PlaybookMatch] = []
    for playbook in playbooks:
        vocab = vocabs[playbook.name]
        hits = {t: w for t, w in vocab.items() if t in doc_tokens}
        keyword_score = sum(w * idf[t] for t, w in hits.items())
        findings = len(review_contract(text, playbook))
        # The findings signal only refines playbooks that already match the
        # document's domain: without any keyword overlap, requires_any rules
        # would otherwise conjure confidence out of nothing.
        findings_bonus = _FINDINGS_W * min(findings, _FINDINGS_CAP) if keyword_score > 0 else 0
        score = keyword_score + findings_bonus
        matches.append(
            PlaybookMatch(
                name=playbook.name,
                description=playbook.description,
                score=int(round(score)),
                matched_terms=tuple(sorted(hits, key=lambda t: (-hits[t] * idf[t], t))[:8]),
                findings=findings,
            )
        )
    matches.sort(key=lambda m: (-m.score, m.name))
    return matches[:limit]


def auto_select_playbook(text: str) -> tuple[str, str]:
    """Pick the playbook for a contract reviewed without ``--playbook``.

    Returns ``(playbook_name, note)``. A clear winner (top score at or above
    ``MIN_SCORE`` and no serious rival) is used directly; otherwise the
    historic ``saas-vendor`` default is kept and the note explains why, so
    an ambiguous document never gets a silently wrong playbook. A rival
    only counts as serious if its own rules also fire on the document —
    a mirror playbook with vocabulary overlap but zero findings is not
    a real contender.
    """
    matches = suggest_playbooks(text)
    top = matches[0]
    note: str
    rival = matches[1] if len(matches) > 1 else None
    ambiguous = (
        rival is not None
        and rival.findings > 0
        and rival.score >= AMBIGUITY_RATIO * top.score
    )
    if top.score < MIN_SCORE:
        name = FALLBACK_PLAYBOOK
        note = (
            f"no confident playbook match (best: {top.name}, score {top.score}); "
            f"defaulting to {FALLBACK_PLAYBOOK}"
        )
    elif ambiguous:
        assert rival is not None
        name = FALLBACK_PLAYBOOK
        note = (
            f"ambiguous match ({top.name} {top.score} vs "
            f"{rival.name} {rival.score}); defaulting to "
            f"{FALLBACK_PLAYBOOK} — pass --playbook to choose, or run "
            f"`redline suggest` to see the ranking"
        )
    else:
        name = top.name
        note = (
            f"auto-selected playbook '{name}' (score {top.score}; "
            f"matched: {', '.join(top.matched_terms[:5])}) — "
            f"pass --playbook to override"
        )
    return name, note
