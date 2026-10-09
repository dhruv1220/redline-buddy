"""redline CLI: review a contract file against a playbook.

redline review contract.md --playbook saas-vendor
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compare import compare_contracts
from .html import render_batch_html_memo, render_compare_html, render_html_memo
from .hygiene import (
    SEVERITY_RANK as HYGIENE_SEVERITY_RANK,
    render_hygiene_json,
    render_hygiene_text,
    run_hygiene,
)
from .ingest import SUPPORTED_SUFFIXES, IngestionError, extract_text
from .letter import render_letter
from .memo import (
    render_batch_json,
    render_batch_memo,
    render_compare_json,
    render_compare_memo,
    render_diff,
    render_json,
    render_memo,
)
from .playbook import (
    PlaybookError,
    bundled_playbook_path,
    bundled_playbooks_dir,
    load_playbook,
)
from .redline_docx import render_compare_docx, render_redline_docx
from .review import SEVERITY_RANK, review_contract
from .scaffold import NEXT_STEPS, scaffold_playbook
from .score import grade_worse_than, risk_grade, risk_score
from .serve import cmd_serve
from .suggest import auto_select_playbook, suggest_playbooks

VERSION = "0.1.0"


def _contract_files(directory: Path) -> list[Path]:
    """Supported contract files under a directory, sorted, recursive."""
    return sorted(
        p
        for p in directory.rglob("*")
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


def _load_or_suggest_playbook(args: argparse.Namespace, text: str):
    """Resolve ``--playbook``, or auto-select when it was omitted.

    Returns ``(playbook, exit_code)``; exit_code is None on success.
    """
    if args.playbook:
        try:
            return load_playbook(_resolve_playbook(args.playbook)), None
        except PlaybookError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None, 2
    name, note = auto_select_playbook(text)
    print(f"note: {note}", file=sys.stderr)
    return load_playbook(bundled_playbook_path(name)), None


def _resolve_playbook(name_or_path: str) -> Path:
    """Accept a bundled playbook name (``offer-letter``) or any file path."""
    p = Path(name_or_path)
    if p.is_file():
        return p
    for candidate in (
        bundled_playbook_path(name_or_path),
        bundled_playbook_path(f"{name_or_path}.yaml"),
    ):
        if candidate.is_file():
            return candidate
    return p  # not found: load_playbook raises the clear error


def _unique_docx_path(stem: str) -> Path:
    out = Path.cwd() / f"{stem}.redline.docx"
    n = 2
    while out.exists():
        out = Path.cwd() / f"{stem}.redline-{n}.docx"
        n += 1
    return out


def _write_redline_docx(
    contract_path: Path,
    text: str,
    playbook_name: str | None,
    findings: list,
    rule_count: int | None,
) -> Path:
    """Render a tracked-changes Word redline and write it next to cwd.

    Returns the written path. ``.docx`` can't go to stdout, so unlike the
    other formats this one always writes a ``<stem>.redline.docx`` file.
    """
    data = render_redline_docx(
        contract_path.name, text, playbook_name or "unknown", findings, rule_count
    )
    out = _unique_docx_path(contract_path.stem)
    out.write_bytes(data)
    return out


def cmd_review(args: argparse.Namespace) -> int:
    contract_path = Path(args.contract)
    if contract_path.is_dir():
        if args.second_reader:
            print(
                "warning: --second-reader is single-file only; "
                "ignoring it for batch review",
                file=sys.stderr,
            )
        return _cmd_review_batch(contract_path, args)
    try:
        text = extract_text(contract_path, ocr=args.ocr)
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    playbook, err = _load_or_suggest_playbook(args, text)
    if err is not None:
        return err
    findings = review_contract(text, playbook)
    second_reader_model = args.second_reader
    if second_reader_model:
        # Lazy import: the default offline path must not require litellm.
        from .second_reader import (
            SecondReaderConfig,
            SecondReaderError,
            litellm_provider,
            run_second_reader,
        )

        config = SecondReaderConfig(
            model=second_reader_model, timeout=args.second_reader_timeout
        )
        try:
            provider = litellm_provider(config)
            findings = run_second_reader(
                text, playbook, provider, config, rule_findings=findings
            )
        except SecondReaderError as exc:
            print(f"error: second reader: {exc}", file=sys.stderr)
            return 2
    if args.format == "json":
        print(
            render_json(
                contract_path.name, playbook.name, findings, len(playbook.rules)
            )
        )
    elif args.format == "diff":
        print(
            render_diff(
                contract_path.name, playbook.name, findings, len(playbook.rules)
            )
        )
    elif args.format == "html":
        print(
            render_html_memo(
                contract_path.name, playbook.name, findings, len(playbook.rules)
            )
        )
    elif args.format == "docx":
        out = _write_redline_docx(
            contract_path, text, playbook.name, findings, len(playbook.rules)
        )
        print(f"wrote {out}")
    else:
        print(
            render_memo(
                contract_path.name,
                playbook.name,
                findings,
                len(playbook.rules),
                second_reader_model=second_reader_model,
            )
        )
    if args.fail_on:
        threshold = SEVERITY_RANK[args.fail_on]
        if any(SEVERITY_RANK.get(f.severity, 9) <= threshold for f in findings):
            return 1
    if args.fail_below:
        if grade_worse_than(risk_grade(risk_score(findings)), args.fail_below):
            return 1
    return 0


def _cmd_review_batch(contract_dir: Path, args: argparse.Namespace) -> int:
    files = _contract_files(contract_dir)
    if not files:
        print(
            f"error: no supported contract files under {contract_dir}", file=sys.stderr
        )
        return 2
    per_file_playbooks: dict[str, str] = {}
    rule_counts: dict[str, int] = {}
    if args.playbook:
        # One playbook for the whole batch (explicit --playbook).
        texts: list[str] = []
        for path in files:
            try:
                texts.append(extract_text(path, ocr=args.ocr))
            except IngestionError:
                continue
        playbook, err = _load_or_suggest_playbook(args, "\n".join(texts))
        if err is not None:
            return err
        results = _review_batch(contract_dir, playbook, ocr=args.ocr)
        header_playbook: str | None = playbook.name
        rule_count: int | None = len(playbook.rules)
        rule_counts = {path.name: len(playbook.rules) for path in files}
    else:
        # Per-file auto-detection: each contract gets its own playbook,
        # so a mixed folder (MSA + DPA + NDA) is reviewed correctly.
        from .suggest import auto_select_playbook

        results = []
        playbooks: dict[str, object] = {}
        for path in files:
            try:
                text = extract_text(path, ocr=args.ocr)
            except IngestionError as exc:
                results.append((path.name, [], str(exc)))
                continue
            name, note = auto_select_playbook(text)
            print(f"note: {path.name}: {note}", file=sys.stderr)
            per_file_playbooks[path.name] = name
            if name not in playbooks:
                playbooks[name] = load_playbook(bundled_playbook_path(name))
            results.append((path.name, review_contract(text, playbooks[name]), None))
            rule_counts[path.name] = len(playbooks[name].rules)
        header_playbook = None
        rule_count = None
    if args.format == "json":
        print(
            render_batch_json(
                results, header_playbook, per_file_playbooks=per_file_playbooks or None
            )
        )
    elif args.format == "html":
        print(
            render_batch_html_memo(
                results,
                header_playbook,
                rule_count,
                per_file_playbooks=per_file_playbooks or None,
            )
        )
    elif args.format == "diff":
        for name, findings, error in results:
            pb_name = per_file_playbooks.get(name, header_playbook)
            if error:
                print(f"# {name}\n\n⚠️ Skipped: {error}\n")
            else:
                print(render_diff(name, pb_name, findings))
    elif args.format == "docx":
        for path in files:
            try:
                text = extract_text(path, ocr=args.ocr)
            except IngestionError as exc:
                print(f"warning: skipped {path.name}: {exc}", file=sys.stderr)
                continue
            entry = next((r for r in results if r[0] == path.name), None)
            if entry is None or entry[2]:
                continue
            _, findings, _ = entry
            pb_name = per_file_playbooks.get(path.name, header_playbook)
            out = _write_redline_docx(
                path, text, pb_name, findings, rule_counts.get(path.name)
            )
            print(f"wrote {out}")
    else:
        print(
            render_batch_memo(
                results,
                header_playbook,
                rule_count,
                per_file_playbooks=per_file_playbooks or None,
            )
        )
    if args.fail_on:
        threshold = SEVERITY_RANK[args.fail_on]
        if any(
            SEVERITY_RANK.get(f.severity, 9) <= threshold
            for _, findings, _ in results
            for f in findings
        ):
            return 1
    if args.fail_below:
        if any(
            not error
            and grade_worse_than(risk_grade(risk_score(findings)), args.fail_below)
            for _, findings, error in results
        ):
            return 1
    return 0


def cmd_hygiene(args: argparse.Namespace) -> int:
    """Check a contract's drafting hygiene (defined terms, cross-references)."""
    contract_path = Path(args.contract)
    if contract_path.is_dir():
        print("error: hygiene is single-file only", file=sys.stderr)
        return 2
    try:
        text = extract_text(contract_path, ocr=args.ocr)
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = run_hygiene(text)
    if args.format == "json":
        print(render_hygiene_json(contract_path.name, findings))
    else:
        print(render_hygiene_text(contract_path.name, findings))
    if args.fail_on:
        threshold = HYGIENE_SEVERITY_RANK[args.fail_on]
        if any(
            HYGIENE_SEVERITY_RANK.get(f.severity, 9) <= threshold for f in findings
        ):
            return 1
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    """Rank bundled playbooks against a contract without reviewing.

    For a directory, each file is ranked independently.
    """
    contract_path = Path(args.contract)
    if contract_path.is_dir():
        files = _contract_files(contract_path)
        if not files:
            print(
                f"error: no supported contract files under {contract_path}",
                file=sys.stderr,
            )
            return 2
        targets = []
        for path in files:
            try:
                targets.append((path, extract_text(path, ocr=args.ocr)))
            except IngestionError:
                continue
        if not targets:
            print(
                f"error: no supported contract files under {contract_path}",
                file=sys.stderr,
            )
            return 2
    else:
        try:
            text = extract_text(contract_path, ocr=args.ocr)
        except IngestionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        targets = [(contract_path, text)]
    first = True
    for path, text in targets:
        matches = suggest_playbooks(text, limit=args.limit)
        if not first:
            print()
        first = False
        if len(targets) > 1:
            print(f"# {path.name}")
        for m in matches:
            print(f"{m.name}  (score {m.score})")
            if m.description:
                print(f"  {m.description}")
            print(f"  matched: {', '.join(m.matched_terms)}")
            print(f"  run: redline review {path} --playbook {m.name}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    old_path = Path(args.old)
    new_path = Path(args.new)
    if old_path.is_dir() or new_path.is_dir():
        print("error: compare takes two files, not directories", file=sys.stderr)
        return 2
    try:
        old_text = extract_text(old_path, ocr=args.ocr)
        new_text = extract_text(new_path, ocr=args.ocr)
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.playbook:
        try:
            playbook = load_playbook(_resolve_playbook(args.playbook))
        except PlaybookError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        name, note = auto_select_playbook(old_text)
        print(f"note: {note}", file=sys.stderr)
        playbook = load_playbook(bundled_playbook_path(name))
    cmp = compare_contracts(old_path.name, new_path.name, old_text, new_text, playbook)
    if args.format == "json":
        print(render_compare_json(cmp))
    elif args.format == "html":
        print(render_compare_html(cmp))
    elif args.format == "docx":
        out = _unique_docx_path(f"{old_path.stem}-vs-{new_path.stem}")
        out.write_bytes(render_compare_docx(cmp, new_text, len(playbook.rules)))
        print(f"wrote {out}")
    else:
        print(render_compare_memo(cmp))
    if args.fail_on_gain:
        threshold = SEVERITY_RANK[args.fail_on_gain]
        if any(SEVERITY_RANK.get(f.severity, 9) <= threshold for f in cmp.gained):
            return 1
    return 0


def cmd_letter(args: argparse.Namespace) -> int:
    contract_path = Path(args.contract)
    if contract_path.is_dir():
        print("error: letter takes a single contract file, not a directory", file=sys.stderr)
        return 2
    try:
        text = extract_text(contract_path, ocr=args.ocr)
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    playbook, err = _load_or_suggest_playbook(args, text)
    if err is not None:
        return err
    findings = review_contract(text, playbook)
    letter = render_letter(
        contract_path.name,
        playbook.name,
        findings,
        recipient=args.recipient,
        sender=args.sender,
        min_severity=args.min_severity,
        fmt=args.format,
    )
    if args.out:
        Path(args.out).write_text(letter, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(letter, end="")
    return 0


def cmd_playbooks(args: argparse.Namespace) -> int:
    """List bundled playbooks with rule counts and descriptions."""
    rows = []
    for path in sorted(bundled_playbooks_dir().glob("*.yaml")):
        pb = load_playbook(path)
        rows.append((pb.name, len(pb.rules), pb.description))
    if args.format == "json":
        print(
            json.dumps(
                [{"name": n, "rules": c, "description": d} for n, c, d in rows],
                indent=2,
            )
        )
    else:
        width = max(len(n) for n, _, _ in rows)
        print(f"{len(rows)} bundled playbooks:\n")
        for name, count, desc in rows:
            print(f"  {name:<{width}}  {count:>2} rules  {desc}")
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


def cmd_new_playbook(args: argparse.Namespace) -> int:
    from .scaffold import validate_name

    try:
        validate_name(args.name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    try:
        created = scaffold_playbook(root, args.name, args.description)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for path in created:
        print(f"created: {path.relative_to(root)}")
    print()
    print(
        NEXT_STEPS.format(
            playbook=f"src/redline/playbooks/{args.name}.yaml",
            sample=f"examples/sample-{args.name}.md",
            test=f"tests/test_{args.name.replace('-', '_')}.py",
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redline",
        description="Local-first contract red-flag checker. No API keys, no data leaves your machine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser(
        "review",
        help="review a contract file (or a directory of contracts) against a playbook",
    )
    review.add_argument(
        "contract",
        help="path to a contract file (markdown, text, .docx, or .pdf) or a directory of contracts for batch review",
    )
    review.add_argument(
        "--playbook",
        default=None,
        help="playbook YAML file or bundled playbook name "
        "(e.g. offer-letter; omit to auto-detect from the contract text — "
        "in batch mode each file is auto-detected independently)",
    )
    review.add_argument(
        "--ocr",
        action="store_true",
        help="run scanned/image-only PDF pages through Tesseract OCR "
        "(requires the tesseract and pdftoppm system binaries)",
    )
    review.add_argument(
        "--format",
        choices=("memo", "json", "diff", "html", "docx"),
        default="memo",
        help="output format: human-readable memo (default), machine-readable JSON, "
        "redline diff view (their language vs. your fallback), self-contained "
        "HTML memo for sharing with a human reviewer, or a Word redline with "
        "tracked changes (writes <contract>.redline.docx)",
    )
    review.add_argument(
        "--fail-on",
        choices=("critical", "high", "medium", "low"),
        default=None,
        help="exit 1 (fail) when any finding is at or above this severity — "
        "for CI gates (default: never fail)",
    )
    review.add_argument(
        "--fail-below",
        choices=("A", "B", "C", "D", "F"),
        default=None,
        help="exit 1 (fail) when the risk grade is worse than this letter — "
        "for CI gates on the headline score (default: never fail)",
    )
    review.add_argument(
        "--second-reader",
        metavar="MODEL",
        default=None,
        help="optional LLM second reader (e.g. gpt-4o-mini): a model re-reads "
        "the contract against the playbook to catch paraphrased clauses the "
        "rules miss and confirm rule hits. Sends contract text to the model "
        "provider — strictly opt-in, requires your own API key and "
        '\'pip install "redline-buddy[llm]"\' (single-file review only)',
    )
    review.add_argument(
        "--second-reader-timeout",
        type=int,
        default=120,
        metavar="SECS",
        help="timeout for the second-reader LLM call (default: 120)",
    )
    review.set_defaults(func=cmd_review)

    suggest = sub.add_parser(
        "suggest",
        help="rank bundled playbooks against a contract without reviewing it",
    )
    suggest.add_argument(
        "contract", help="path to a contract file or a directory of contracts"
    )
    suggest.add_argument(
        "--limit",
        type=int,
        default=3,
        help="how many playbooks to rank (default: 3)",
    )
    suggest.add_argument(
        "--ocr",
        action="store_true",
        help="run scanned/image-only PDF pages through Tesseract OCR",
    )
    suggest.set_defaults(func=cmd_suggest)

    compare = sub.add_parser(
        "compare",
        help="compare two drafts of a contract: text changes plus "
        "red flags gained, resolved, or reworded between rounds",
    )
    compare.add_argument(
        "old", help="path to the earlier draft (markdown, text, .docx, or .pdf)"
    )
    compare.add_argument("new", help="path to the newer draft")
    compare.add_argument(
        "--playbook",
        default=None,
        help="playbook YAML file or bundled playbook name "
        "(e.g. offer-letter; omit to auto-detect from the earlier draft)",
    )
    compare.add_argument(
        "--ocr",
        action="store_true",
        help="run scanned/image-only PDF pages through Tesseract OCR "
        "(requires the tesseract and pdftoppm system binaries)",
    )
    compare.add_argument(
        "--format",
        choices=("memo", "json", "html", "docx"),
        default="memo",
        help="output format: human-readable memo (default), machine-readable "
        "JSON, self-contained HTML for sharing with a human reviewer, or a "
        "Word redline with tracked changes (writes <old>-vs-<new>.redline.docx)",
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

    playbooks = sub.add_parser(
        "playbooks", help="list bundled playbooks with rule counts and descriptions"
    )
    playbooks.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    playbooks.set_defaults(func=cmd_playbooks)

    serve = sub.add_parser(
        "serve", help="start a minimal local web UI (127.0.0.1 only)"
    )
    serve.add_argument(
        "--port", type=int, default=8000, help="port to listen on (default: 8000)"
    )
    serve.add_argument(
        "--bind", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)"
    )
    serve.set_defaults(func=cmd_serve)

    new_playbook = sub.add_parser(
        "new-playbook", help="scaffold a new playbook (YAML + fixtures + test skeleton)"
    )
    new_playbook.add_argument("name", help="playbook slug, e.g. franchise-agreement")
    new_playbook.add_argument(
        "--description",
        default="Red-flag rules for reviewing contracts.",
        help="one-line playbook description",
    )
    new_playbook.add_argument(
        "--root",
        default=".",
        help="project root to scaffold into (default: current directory)",
    )
    new_playbook.set_defaults(func=cmd_new_playbook)

    hygiene = sub.add_parser(
        "hygiene",
        help="check drafting hygiene: defined terms, cross-references, consistency",
    )
    hygiene.add_argument(
        "contract",
        help="path to a contract file (markdown, text, .docx, or .pdf)",
    )
    hygiene.add_argument(
        "--ocr",
        action="store_true",
        help="run scanned/image-only PDF pages through Tesseract OCR "
        "(requires the tesseract and pdftoppm system binaries)",
    )
    hygiene.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format: human-readable report (default) or machine-readable JSON",
    )
    hygiene.add_argument(
        "--fail-on",
        choices=("high", "medium", "low"),
        default=None,
        help="exit 1 (fail) when any finding is at or above this severity — "
        "for CI gates (default: never fail)",
    )
    hygiene.set_defaults(func=cmd_hygiene)

    letter = sub.add_parser(
        "letter",
        help="draft a negotiation letter to the counterparty from review findings",
    )
    letter.add_argument(
        "contract",
        help="path to a contract file (markdown, text, .docx, or .pdf)",
    )
    letter.add_argument(
        "--playbook",
        default=None,
        help="playbook YAML file or bundled playbook name "
        "(e.g. offer-letter; omit to auto-detect from the contract text)",
    )
    letter.add_argument(
        "--ocr",
        action="store_true",
        help="run scanned/image-only PDF pages through Tesseract OCR "
        "(requires the tesseract and pdftoppm system binaries)",
    )
    letter.add_argument(
        "--to",
        dest="recipient",
        default=None,
        metavar="NAME",
        help="counterparty name for the salutation and signature line",
    )
    letter.add_argument(
        "--from",
        dest="sender",
        default=None,
        metavar="NAME",
        help="your name for the signature line",
    )
    letter.add_argument(
        "--min-severity",
        choices=("critical", "high", "medium", "low"),
        default="medium",
        help="include findings at or above this severity (default: medium)",
    )
    letter.add_argument(
        "--format",
        choices=("md", "txt"),
        default="md",
        help="markdown (default) or plain text for pasting into an email",
    )
    letter.add_argument(
        "-o",
        "--out",
        default=None,
        metavar="FILE",
        help="write the letter to FILE instead of printing it",
    )
    letter.set_defaults(func=cmd_letter)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
