"""redline CLI: review a contract file against a playbook.

    redline review contract.md --playbook saas-vendor
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compare import compare_contracts
from .ingest import SUPPORTED_SUFFIXES, IngestionError, extract_text
from .memo import (
    render_batch_json,
    render_batch_memo,
    render_compare_json,
    render_compare_memo,
    render_diff,
    render_json,
    render_memo,
)
from .playbook import PlaybookError, bundled_playbook_path, load_playbook
from .review import SEVERITY_RANK, review_contract
from .serve import cmd_serve

VERSION = "0.1.0"


def _contract_files(directory: Path) -> list[Path]:
    """Supported contract files under a directory, sorted, recursive."""
    return sorted(
        p for p in directory.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _review_batch(
    directory: Path, playbook, *, ocr: bool
) -> list[tuple[str, list, str | None]]:
    results = []
    for path in _contract_files(directory):
        try:
            text = extract_text(path, ocr=ocr)
        except IngestionError as exc:
            results.append((path.name, [], str(exc)))
            continue
        results.append((path.name, review_contract(text, playbook), None))
    return results


def _default_playbook() -> Path:
    return bundled_playbook_path("saas-vendor")


def _resolve_playbook(name_or_path: str) -> Path:
    """Accept a bundled playbook name (``offer-letter``) or any file path."""
    p = Path(name_or_path)
    if p.is_file():
        return p
    for candidate in (bundled_playbook_path(name_or_path),
                      bundled_playbook_path(f"{name_or_path}.yaml")):
        if candidate.is_file():
            return candidate
    return p  # not found: load_playbook raises the clear error


def cmd_review(args: argparse.Namespace) -> int:
    contract_path = Path(args.contract)
    try:
        playbook = load_playbook(_resolve_playbook(args.playbook))
    except PlaybookError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if contract_path.is_dir():
        return _cmd_review_batch(contract_path, playbook, args)
    try:
        text = extract_text(contract_path, ocr=args.ocr)
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = review_contract(text, playbook)
    if args.format == "json":
        print(render_json(contract_path.name, playbook.name, findings))
    elif args.format == "diff":
        print(render_diff(contract_path.name, playbook.name, findings))
    else:
        print(render_memo(contract_path.name, playbook.name, findings))
    if args.fail_on:
        threshold = SEVERITY_RANK[args.fail_on]
        if any(SEVERITY_RANK.get(f.severity, 9) <= threshold for f in findings):
            return 1
    return 0


def _cmd_review_batch(contract_dir: Path, playbook, args: argparse.Namespace) -> int:
    results = _review_batch(contract_dir, playbook, ocr=args.ocr)
    if not results:
        print(f"error: no supported contract files under {contract_dir}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(render_batch_json(results, playbook.name))
    elif args.format == "diff":
        for name, findings, error in results:
            if error:
                print(f"# {name}\n\n⚠️ Skipped: {error}\n")
            else:
                print(render_diff(name, playbook.name, findings))
    else:
        print(render_batch_memo(results, playbook.name))
    if args.fail_on:
        threshold = SEVERITY_RANK[args.fail_on]
        if any(
            SEVERITY_RANK.get(f.severity, 9) <= threshold
            for _, findings, _ in results
            for f in findings
        ):
            return 1
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    old_path = Path(args.old)
    new_path = Path(args.new)
    if old_path.is_dir() or new_path.is_dir():
        print("error: compare takes two files, not directories", file=sys.stderr)
        return 2
    try:
        playbook = load_playbook(_resolve_playbook(args.playbook))
    except PlaybookError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        old_text = extract_text(old_path, ocr=args.ocr)
        new_text = extract_text(new_path, ocr=args.ocr)
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    cmp = compare_contracts(old_path.name, new_path.name, old_text, new_text, playbook)
    if args.format == "json":
        print(render_compare_json(cmp))
    else:
        print(render_compare_memo(cmp))
    if args.fail_on_gain:
        threshold = SEVERITY_RANK[args.fail_on_gain]
        if any(SEVERITY_RANK.get(f.severity, 9) <= threshold for f in cmp.gained):
            return 1
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        playbook = load_playbook(args.playbook)
    except PlaybookError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 2
    print(f"valid: {args.playbook}")
    print(f"name: {playbook.name} (version {playbook.version})")
    print(f"rules: {len(playbook.rules)}")
    fired: set[str] = set()
    if args.sample:
        try:
            text = extract_text(args.sample)
        except IngestionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        fired = {f.rule_id for f in review_contract(text, playbook)}
        print(f"sample: {args.sample} — {len(fired)}/{len(playbook.rules)} rules fired")
    for r in playbook.rules:
        fb = " +fallback" if r.fallback else ""
        hit = ""
        if args.sample:
            hit = " FIRED" if r.id in fired else " -"
        print(f"  - {r.id} [{r.severity}] {r.check.kind}{fb}{hit}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redline",
        description="Local-first contract red-flag checker. No API keys, no data leaves your machine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", help="review a contract file (or a directory of contracts) against a playbook")
    review.add_argument("contract", help="path to a contract file (markdown, text, .docx, or .pdf) or a directory of contracts for batch review")
    review.add_argument(
        "--playbook",
        default=str(_default_playbook()),
        help="playbook YAML file or bundled playbook name "
        "(e.g. offer-letter; default: bundled saas-vendor)",
    )
    review.add_argument(
        "--ocr",
        action="store_true",
        help="run scanned/image-only PDF pages through Tesseract OCR "
        "(requires the tesseract and pdftoppm system binaries)",
    )
    review.add_argument(
        "--format",
        choices=("memo", "json", "diff"),
        default="memo",
        help="output format: human-readable memo (default), machine-readable JSON, "
        "or redline diff view (their language vs. your fallback)",
    )
    review.add_argument(
        "--fail-on",
        choices=("critical", "high", "medium", "low"),
        default=None,
        help="exit 1 (fail) when any finding is at or above this severity — "
        "for CI gates (default: never fail)",
    )
    review.set_defaults(func=cmd_review)

    compare = sub.add_parser(
        "compare",
        help="compare two drafts of a contract: text changes plus "
        "red flags gained, resolved, or reworded between rounds",
    )
    compare.add_argument("old", help="path to the earlier draft (markdown, text, .docx, or .pdf)")
    compare.add_argument("new", help="path to the newer draft")
    compare.add_argument(
        "--playbook",
        default=str(_default_playbook()),
        help="playbook YAML file or bundled playbook name "
        "(e.g. offer-letter; default: bundled saas-vendor)",
    )
    compare.add_argument(
        "--ocr",
        action="store_true",
        help="run scanned/image-only PDF pages through Tesseract OCR "
        "(requires the tesseract and pdftoppm system binaries)",
    )
    compare.add_argument(
        "--format",
        choices=("memo", "json"),
        default="memo",
        help="output format: human-readable memo (default) or machine-readable JSON",
    )
    compare.add_argument(
        "--fail-on-gain",
        choices=("critical", "high", "medium", "low"),
        default=None,
        help="exit 1 (fail) when the new draft introduces any finding at or "
        "above this severity — for CI gates on negotiation rounds",
    )
    compare.set_defaults(func=cmd_compare)

    validate = sub.add_parser("validate", help="validate a playbook YAML file")
    validate.add_argument("playbook", help="playbook YAML file to validate")
    validate.add_argument(
        "--sample",
        default=None,
        help="sample contract to test the playbook against; reports per-rule hit/miss",
    )
    validate.set_defaults(func=cmd_validate)

    serve = sub.add_parser("serve", help="start a minimal local web UI (127.0.0.1 only)")
    serve.add_argument("--port", type=int, default=8000, help="port to listen on (default: 8000)")
    serve.add_argument("--bind", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
