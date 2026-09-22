"""redline CLI: review a contract file against a playbook.

    redline review contract.md --playbook playbooks/saas-vendor.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .memo import render_memo
from .playbook import PlaybookError, load_playbook
from .review import review_contract

VERSION = "0.1.0"


def _default_playbook() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "playbooks" / "saas-vendor.yaml"


def cmd_review(args: argparse.Namespace) -> int:
    contract_path = Path(args.contract)
    if not contract_path.is_file():
        print(f"error: contract file not found: {contract_path}", file=sys.stderr)
        return 2
    try:
        playbook = load_playbook(args.playbook)
    except PlaybookError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = contract_path.read_text(encoding="utf-8")
    findings = review_contract(text, playbook)
    print(render_memo(contract_path.name, playbook.name, findings))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redline",
        description="Local-first contract red-flag checker. No API keys, no data leaves your machine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", help="review a contract file against a playbook")
    review.add_argument("contract", help="path to the contract file (markdown or text)")
    review.add_argument(
        "--playbook",
        default=str(_default_playbook()),
        help="playbook YAML file (default: bundled saas-vendor)",
    )
    review.set_defaults(func=cmd_review)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
