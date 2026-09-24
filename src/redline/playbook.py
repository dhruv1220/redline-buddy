"""Playbook loading and validation.

A playbook is YAML:

    name: saas-vendor
    version: 1
    description: ...
    rules:
      - id: liability-cap
        title: No limitation of liability
        severity: high            # critical | high | medium | low
        description: ...
        why: ...
        suggestion: ...   # advice-style: what to ask for
        fallback: ...     # optional: quotable replacement/insertion clause language
        check:
          kind: requires_any      # requires_any | forbids_any | forbids_unless | max_value
          patterns: [...]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SEVERITIES = ("critical", "high", "medium", "low")
CHECK_KINDS = ("requires_any", "forbids_any", "forbids_unless", "max_value")


class PlaybookError(ValueError):
    pass


@dataclass
class Check:
    kind: str
    patterns: list[str] = field(default_factory=list)
    unless_any: list[str] = field(default_factory=list)
    group: str = "value"
    max: float | None = None


@dataclass
class Rule:
    id: str
    title: str
    severity: str
    description: str
    why: str
    suggestion: str
    check: Check
    fallback: str = ""


@dataclass
class Playbook:
    name: str
    version: int
    description: str
    rules: list[Rule]


def _req(mapping: dict, key: str, where: str):
    if key not in mapping:
        raise PlaybookError(f"{where}: missing required key {key!r}")
    return mapping[key]


def load_playbook(path: str | Path) -> Playbook:
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PlaybookError(f"playbook not found: {p}")
    except yaml.YAMLError as exc:
        raise PlaybookError(f"playbook is not valid YAML: {p}: {exc}")
    if not isinstance(data, dict):
        raise PlaybookError(f"playbook must be a YAML mapping: {p}")

    name = _req(data, "name", str(p))
    rules_raw = _req(data, "rules", str(p))
    if not isinstance(rules_raw, list) or not rules_raw:
        raise PlaybookError(f"{p}: 'rules' must be a non-empty list")

    rules: list[Rule] = []
    seen_ids: set[str] = set()
    for i, r in enumerate(rules_raw):
        where = f"{p} rule #{i}"
        if not isinstance(r, dict):
            raise PlaybookError(f"{where}: rule must be a mapping")
        rid = str(_req(r, "id", where))
        if rid in seen_ids:
            raise PlaybookError(f"{where}: duplicate rule id {rid!r}")
        seen_ids.add(rid)
        severity = str(_req(r, "severity", where))
        if severity not in SEVERITIES:
            raise PlaybookError(f"{where}: severity must be one of {SEVERITIES}")
        check_raw = _req(r, "check", where)
        if not isinstance(check_raw, dict):
            raise PlaybookError(f"{where}: check must be a mapping")
        kind = str(_req(check_raw, "kind", where))
        if kind not in CHECK_KINDS:
            raise PlaybookError(f"{where}: check kind must be one of {CHECK_KINDS}")
        patterns = check_raw.get("patterns", [])
        if not isinstance(patterns, list) or not patterns:
            raise PlaybookError(f"{where}: check.patterns must be a non-empty list")
        unless_any = check_raw.get("unless_any", [])
        if not isinstance(unless_any, list):
            raise PlaybookError(f"{where}: check.unless_any must be a list")
        max_val = check_raw.get("max")
        if max_val is not None and not isinstance(max_val, (int, float)):
            raise PlaybookError(f"{where}: check.max must be a number")
        rules.append(
            Rule(
                id=rid,
                title=str(_req(r, "title", where)),
                severity=severity,
                description=str(r.get("description", "")),
                why=str(r.get("why", "")),
                suggestion=str(r.get("suggestion", "")),
                fallback=str(r.get("fallback", "") or ""),
                check=Check(
                    kind=kind,
                    patterns=[str(x) for x in patterns],
                    unless_any=[str(x) for x in unless_any],
                    group=str(check_raw.get("group", "value")),
                    max=float(max_val) if max_val is not None else None,
                ),
            )
        )

    return Playbook(
        name=str(name),
        version=int(data.get("version", 1)),
        description=str(data.get("description", "")),
        rules=rules,
    )
