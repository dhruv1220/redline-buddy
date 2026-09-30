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


@dataclass(frozen=True)
class PlaybookMatch:
    name: str
    description: str
    score: int
    matched_terms: tuple[str, ...]


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

    Score is the sum over vocabulary hits of ``weight * idf``: tokens that
    appear in many playbooks (``termination``, ``payment``, ``notice``)
    contribute little, while distinctive tokens (``subprocessor``,
    ``disparagement``, ``deductible``) dominate. Each token counts once per
    playbook; ties break alphabetically for determinism.
    """
    doc_tokens = _tokens(text)
    vocabs: dict[str, dict[str, int]] = {}
    descriptions: dict[str, str] = {}
    for path in sorted(bundled_playbooks_dir().glob("*.yaml")):
        playbook = load_playbook(path)
        vocabs[playbook.name] = _playbook_vocab(playbook)
        descriptions[playbook.name] = playbook.description
    doc_freq: dict[str, int] = {}
    for vocab in vocabs.values():
        for t in vocab:
            doc_freq[t] = doc_freq.get(t, 0) + 1
    n = len(vocabs)
    idf = {t: math.log(n / df) + 1.0 for t, df in doc_freq.items()}
    matches: list[PlaybookMatch] = []
    for name, vocab in vocabs.items():
        hits = {t: w for t, w in vocab.items() if t in doc_tokens}
        score = sum(w * idf[t] for t, w in hits.items())
        matches.append(
            PlaybookMatch(
                name=name,
                description=descriptions[name],
                score=int(round(score)),
                matched_terms=tuple(sorted(hits, key=lambda t: (-hits[t] * idf[t], t))[:8]),
            )
        )
    matches.sort(key=lambda m: (-m.score, m.name))
    return matches[:limit]


def auto_select_playbook(text: str) -> tuple[str, str]:
    """Pick the playbook for a contract reviewed without ``--playbook``.

    Returns ``(playbook_name, note)``. A clear winner (top score at or above
    ``MIN_SCORE`` and the runner-up below ``AMBIGUITY_RATIO`` of it) is used
    directly; otherwise the historic ``saas-vendor`` default is kept and the
    note explains why, so an ambiguous document never gets a silently
    wrong playbook.
    """
    matches = suggest_playbooks(text)
    top = matches[0]
    note: str
    if top.score < MIN_SCORE:
        name = FALLBACK_PLAYBOOK
        note = (
            f"no confident playbook match (best: {top.name}, score {top.score}); "
            f"defaulting to {FALLBACK_PLAYBOOK}"
        )
    elif len(matches) > 1 and matches[1].score >= AMBIGUITY_RATIO * top.score:
        name = FALLBACK_PLAYBOOK
        note = (
            f"ambiguous match ({top.name} {top.score} vs "
            f"{matches[1].name} {matches[1].score}); defaulting to "
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
